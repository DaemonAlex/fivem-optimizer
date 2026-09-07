"""The .ytd analyzer feeding the scan results screen."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture
from analyzers.ytd_analyzer import YtdAnalyzer

MIB = 1024 * 1024


def analyze(name, settings=None):
    path = fixture(name)
    a = YtdAnalyzer(settings or {})
    return a.analyze(path, name, os.path.getsize(path))


def test_metadata_is_the_real_texture_list_and_engine_memory():
    issues, meta = analyze("fer49p2025.ytd")
    assert meta["vram_estimate"] == 86 * MIB
    assert meta["memory_mib"] == 86.0
    assert len(meta["textures"]) == 51
    skin = next(t for t in meta["textures"] if t["name"] == "ext_skin")
    assert (skin["width"], skin["height"], skin["format"], skin["mipmaps"]) == (4096, 4096, "DXT5", 11)
    assert skin["type"] == "diffuse" or skin["type"] == "unknown"


def test_issues_name_the_right_texture_and_drop_the_fake_size_limit():
    issues, _ = analyze("fer49p2025.ytd", {"recommendedMaxResolution": 2048, "maxTextureResolution": 4096})
    messages = [i["message"] for i in issues]
    assert not any("16MB" in m or "16 MB" in m for m in messages)
    big = [i for i in issues if i["category"] == "texture_quality" and "4096x4096" in i["message"]]
    assert len(big) == 1 and "ext_skin" in big[0]["message"]
    mem = [i for i in issues if i["category"] == "memory"]
    assert len(mem) == 1 and "86" in mem[0]["message"] and mem[0]["severity"] == "critical"
    nomip = [i for i in issues if "mipmap" in i["message"].lower()]
    assert {i["details"]["name"] for i in nomip} >= {"ff", "mat", "vrc-car-body", "green", "basic"}


def test_small_file_has_no_issues():
    issues, meta = analyze("formula.ytd")
    assert issues == []
    assert meta["memory_mib"] == 0.5


def test_encrypted_file_is_reported_not_guessed(tmp_path):
    p = tmp_path / "x.ytd"
    p.write_bytes(b"FXAP" + b"\0" * 100)
    issues, meta = YtdAnalyzer({}).analyze(str(p), "x.ytd", 104)
    assert len(issues) == 1 and issues[0]["severity"] == "info" and "encrypted" in issues[0]["message"].lower()
    assert meta["textures"] == [] and meta["vram_estimate"] == 0
