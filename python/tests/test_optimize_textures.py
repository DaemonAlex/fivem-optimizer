"""The optimizer entry point the Electron app spawns: plan a folder, then execute on selected files."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture, FIXTURES
import rsc7
import ytd

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "optimize_textures.py")
MIB = 1024 * 1024


def run(*argv):
    out = subprocess.run([sys.executable, SCRIPT, *argv], capture_output=True, text=True, timeout=900)
    assert out.returncode == 0, out.stderr
    body = "\n".join(l for l in out.stdout.splitlines() if not l.startswith("PROGRESS:"))
    return json.loads(body)


@pytest.fixture
def folder(tmp_path):
    fixture("fer49p2025.ytd")
    for name in ("fer49p2025.ytd", "formula.ytd", "crane_outrigger.ydr"):
        shutil.copy(os.path.join(FIXTURES, name), tmp_path / name)
    (tmp_path / "broken.ytd").write_bytes(b"FXAP" + b"\0" * 100)
    return tmp_path


def test_plan_reports_real_texture_facts(folder):
    plan = run(str(folder), json.dumps({"optimizerTargetResolution": 1024}))
    assert plan["status"] == "ready"
    files = {f["rel_path"]: f for f in plan["files"]}
    fer = files["fer49p2025.ytd"]
    assert fer["texture_count"] == 51 and fer["max_dimension"] == 4096
    assert fer["memory_mib"] == 86.0 and fer["size"] == 86 * MIB
    assert fer["disk_size"] == 9874244
    assert fer["should_optimize"] is True and fer["skip_reason"] is None
    assert fer["has_script_rt"] is True
    assert 30 * MIB < fer["estimated_savings"] < 60 * MIB
    assert fer["estimated_savings_pct"] == round(fer["estimated_savings"] / fer["size"] * 100)
    assert fer["oversized"][0]["name"] == "ext_skin" and fer["oversized"][0]["size"] == "4096x4096"
    formula = files["formula.ytd"]
    assert formula["should_optimize"] is False and "already" in formula["skip_reason"]
    assert formula["texture_count"] == 11 and formula["max_dimension"] == 512
    broken = files["broken.ytd"]
    assert broken["should_optimize"] is False and "FXAP" in broken["skip_reason"]
    assert plan["total_files"] == 3 and plan["optimizable_files"] == 1
    assert plan["total_size"] == fer["size"] + formula["size"]
    assert plan["converter"] in ("magick", "texconv", None)


def test_execute_rewrites_file_with_backup_and_reports_memory(folder, tmp_path):
    backup = tmp_path / "bak"
    before = hashlib.md5((folder / "fer49p2025.ytd").read_bytes()).hexdigest()
    res = run("--execute", json.dumps({"folder_path": str(folder), "selected_files": ["fer49p2025.ytd", "formula.ytd"],
                                       "backup_folder": str(backup), "target_resolution": 1024}))
    assert res["status"] == "completed"
    assert res["files_succeeded"] == 1 and res["files_skipped"] == 1 and res["files_failed"] == 0
    after = hashlib.md5((folder / "fer49p2025.ytd").read_bytes()).hexdigest()
    assert after != before
    assert hashlib.md5((backup / "fer49p2025.ytd").read_bytes()).hexdigest() == before
    f = rsc7.read(str(folder / "fer49p2025.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    assert len(d.textures) == 51
    assert max(max(t.width, t.height) for t in d.textures if not t.name.startswith("script_rt")) <= 1024
    assert f.physical_size < 0.6 * 86 * MIB
    per = {r["file"]: r for r in res["results"]}
    assert per["fer49p2025.ytd"]["memory_before_mib"] == 86.0
    assert per["fer49p2025.ytd"]["memory_after_mib"] == round(f.physical_size / MIB, 1)
    assert per["fer49p2025.ytd"]["textures_resized"] >= 6
    assert res["memory_before_mib"] >= 86.0 and res["memory_after_mib"] < res["memory_before_mib"]
    assert per["formula.ytd"]["status"] == "skipped"


def test_execute_refuses_paths_outside_folder_and_missing_files(folder, tmp_path):
    res = run("--execute", json.dumps({"folder_path": str(folder), "selected_files": ["../x.ytd", "nope.ytd"],
                                       "backup_folder": str(tmp_path / "bak"), "target_resolution": 1024}))
    assert res["files_failed"] == 2
    assert {e["file"] for e in res["errors"]} == {"../x.ytd", "nope.ytd"}


def test_execute_without_backup_folder_is_refused(folder):
    res = run("--execute", json.dumps({"folder_path": str(folder), "selected_files": ["fer49p2025.ytd"],
                                       "backup_folder": None, "target_resolution": 1024}))
    assert res["status"] == "no_backup" and res["files_succeeded"] == 0
