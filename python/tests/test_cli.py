"""ytdshrink: the command-line tool for a server box (no app, no clicking)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture, FIXTURES

CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ytdshrink.py")


@pytest.fixture
def folder(tmp_path):
    fixture("fer49p2025.ytd")
    for name in ("fer49p2025.ytd", "formula.ytd", "fer49p2025.yft"):
        shutil.copy(os.path.join(FIXTURES, name), tmp_path / name)
    (tmp_path / "locked.ytd").write_bytes(b"FXAP" + b"\0" * 100)
    return tmp_path


def run(*argv):
    out = subprocess.run([sys.executable, CLI, *argv], capture_output=True, text=True, timeout=900)
    return out.returncode, out.stdout, out.stderr


def test_dry_run_reports_and_changes_nothing(folder):
    before = hashlib.md5((folder / "fer49p2025.ytd").read_bytes()).hexdigest()
    code, out, err = run(str(folder), "--max", "1024")
    assert code == 0, err
    assert "fer49p2025.ytd" in out and "86.0" in out            # memory before
    assert "formula.ytd" in out and "0.5" in out
    assert "locked.ytd" in out and "FXAP" in out
    assert "DRY RUN" in out
    assert hashlib.md5((folder / "fer49p2025.ytd").read_bytes()).hexdigest() == before
    assert not any(p.name.startswith("ytdshrink") for p in folder.iterdir())


def test_apply_rewrites_with_backup_and_prints_after_numbers(folder, tmp_path):
    backup = tmp_path / "bk"
    before = hashlib.md5((folder / "fer49p2025.ytd").read_bytes()).hexdigest()
    code, out, err = run(str(folder), "--max", "1024", "--apply", "--backup", str(backup))
    assert code == 0, err
    assert hashlib.md5((folder / "fer49p2025.ytd").read_bytes()).hexdigest() != before
    assert hashlib.md5((backup / "fer49p2025.ytd").read_bytes()).hexdigest() == before
    assert "optimized" in out and "->" in out
    assert (backup / "fivem-optimizer-log.txt").exists()
    assert "formula.ytd" in out and "unchanged" in out.lower()


def test_only_filter_limits_files(folder, tmp_path):
    code, out, err = run(str(folder), "--only", "formula", "--apply", "--backup", str(tmp_path / "bk"))
    assert code == 0, err
    assert "fer49p2025" not in out


def test_apply_without_backup_refuses(folder):
    code, out, err = run(str(folder), "--apply")
    assert code != 0
    assert "backup" in (out + err).lower()


def test_json_output(folder):
    code, out, err = run(str(folder), "--json")
    assert code == 0, err
    data = json.loads(out)
    assert data["status"] == "ready" and any(f["rel_path"] == "fer49p2025.ytd" for f in data["files"])


def test_apply_across_several_top_level_folders(tmp_path):
    fixture("fer49p2025.ytd")
    a = tmp_path / "[a]" / "car" / "stream"; b = tmp_path / "[b]" / "map" / "stream"
    a.mkdir(parents=True); b.mkdir(parents=True)
    shutil.copy(os.path.join(FIXTURES, "fer49p2025.ytd"), a / "one.ytd")
    shutil.copy(os.path.join(FIXTURES, "servicevan.ytd"), b / "two.ytd")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code, out, err = run("[a]", "[b]", "--apply", "--backup", str(tmp_path / "bk"))
    finally:
        os.chdir(cwd)
    assert code == 0, err + out
    assert out.count("optimized ") == 2, out
    assert "outside the scanned folder" not in out
    assert (tmp_path / "bk" / "[a]" / "car" / "stream" / "one.ytd").exists()
