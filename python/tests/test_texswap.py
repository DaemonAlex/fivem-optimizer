"""Replacing one named texture in a real .ytd, and refusing the cases that would ship a broken file."""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture
import converter as converter_mod
import rsc7
import texswap
import ytd


def load(path):
    r = rsc7.read(path)
    return r, ytd.parse(r.virtual, r.physical)


def biggest(d):
    return max(d.textures, key=lambda t: t.width * t.height)


def test_list_reads_every_texture():
    _, d = load(fixture("fer49p2025.ytd"))
    assert d.textures
    assert all(t.name and t.width and t.height for t in d.textures)


def test_refuses_a_name_that_is_not_in_the_dictionary():
    with pytest.raises(texswap.Refused) as e:
        texswap.swap(fixture("fer49p2025.ytd"), "no_such_texture", fixture("fer49p2025.ytd"))
    assert "no texture named" in str(e.value)


def test_refuses_anything_that_is_not_a_ytd():
    with pytest.raises(texswap.Refused) as e:
        texswap.swap("vehicle.yft", "whatever", "image.png")
    assert "only .ytd" in str(e.value)


def test_dry_run_reports_the_target_shape_and_writes_nothing(tmp_path):
    src = fixture("fer49p2025.ytd")
    copy = str(tmp_path / "subject.ytd")
    shutil.copy2(src, copy)
    before = open(copy, "rb").read()
    _, d = load(copy)
    target = biggest(d)
    if converter_mod.find() is None:
        pytest.skip("no converter installed")
    report = texswap.swap(copy, target.name, _png(tmp_path, target.width, target.height))
    assert report["applied"] is False
    assert (report["width"], report["height"]) == (target.width, target.height)
    assert report["levels"] == target.levels
    assert open(copy, "rb").read() == before


def test_apply_replaces_only_that_texture_and_keeps_the_rest(tmp_path):
    if converter_mod.find() is None:
        pytest.skip("no converter installed")
    src = fixture("fer49p2025.ytd")
    copy = str(tmp_path / "subject.ytd")
    shutil.copy2(src, copy)
    _, before = load(copy)
    target = biggest(before)
    others = {t.name: t.data for t in before.textures if t.name != target.name}

    report = texswap.swap(copy, target.name, _png(tmp_path, target.width, target.height),
                          apply=True, backup=str(tmp_path / "bak"))
    assert report["applied"] is True
    assert os.path.isfile(report["backup"])

    _, after = load(copy)
    assert [t.name for t in after.textures] == [t.name for t in before.textures]
    swapped = [t for t in after.textures if t.name == target.name][0]
    assert (swapped.width, swapped.height, swapped.format, swapped.levels) == \
           (target.width, target.height, target.format, target.levels)
    assert len(swapped.data) == ytd.chain_size(target.width, target.height, target.format, target.levels)
    assert swapped.data != target.data
    for t in after.textures:
        if t.name != target.name:
            assert t.data == others[t.name]


def _png(tmp_path, width, height):
    """A solid image at the target size, written with the converter that is installed."""
    import subprocess
    conv = converter_mod.find()
    out = str(tmp_path / "flat.png")
    exe = "magick" if conv.name != "texconv" else conv.exe
    try:
        subprocess.run([exe, "-size", f"{width}x{height}", "xc:#2244aa", out],
                       check=True, capture_output=True, timeout=600)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("cannot author a test image without imagemagick")
    return out
