"""External resampler (ImageMagick on Linux/macOS, texconv on Windows) and shrink-with-converter."""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture
import converter
import dds
import rsc7
import ytd

needs_magick = pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")


def test_target_dimensions_keep_aspect_and_snap_to_4():
    assert converter.fit(2560, 1704, 1024) == (1024, 680)
    assert converter.fit(4096, 4096, 1024) == (1024, 1024)
    assert converter.fit(1920, 1080, 1024) == (1024, 576)
    assert converter.fit(100, 20, 16) == (16, 4)


def test_full_mip_count():
    assert converter.mip_count(1024, 680) == 11
    assert converter.mip_count(4, 4) == 3


def test_texconv_command_uses_bc_names_and_full_chain(tmp_path):
    c = converter.Converter("texconv", "C:/tools/texconv.exe")
    argv = c.command(str(tmp_path / "in.dds"), str(tmp_path), 1024, 680, "DXT5", 11)
    assert argv[0] == "C:/tools/texconv.exe"
    assert "BC3_UNORM" in argv and "-m" in argv and "11" in argv and "-w" in argv and "1024" in argv


def test_magick_command_writes_one_file_per_level(tmp_path):
    c = converter.Converter("magick", "/usr/bin/magick")
    argv = c.command(str(tmp_path / "in.dds"), str(tmp_path), 1024, 680, "DXT5", 11)
    assert argv.count("-write") == 11 and "dds:compression=dxt5" in argv
    assert "512x340!" in argv and "4x4!" in argv


@needs_magick
def test_magick_resizes_a_real_no_mip_texture_and_keeps_format():
    f = rsc7.read(fixture("fer49p2025.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    t = d.by_name()["ff"]                       # 2560x1704 DXT5, 1 mip
    c = converter.find()
    assert c is not None
    w, h, levels, data, fmt = c.resize(t.mip_bytes(0), t.width, t.height, t.format, 1024)
    assert (w, h, levels, fmt) == (1024, 680, 11, "DXT5")
    assert len(data) == ytd.chain_size(1024, 680, "DXT5", 11)
    w, h, levels, data, fmt = c.resize(t.mip_bytes(0), t.width, t.height, t.format, 1024, levels=1)
    assert levels == 1 and len(data) == ytd.mip_size(1024, 680, "DXT5")


@needs_magick
def test_shrink_with_converter_reaches_target_on_every_texture():
    f = rsc7.read(fixture("fer49p2025.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    report = ytd.shrink(d, 1024, skip=lambda t: t.name.startswith("script_rt"), converter=converter.find())
    assert report["skipped"] == []
    assert report["resized"] == 11
    assert all(max(t.width, t.height) <= 1024 for t in d.textures)
    by = d.by_name()
    # ff shipped without a mip chain: it is resized but stays mipless (dirt/decal/normal overlays haze at distance otherwise)
    assert (by["ff"].width, by["ff"].height, by["ff"].levels, by["ff"].format) == (1024, 680, 1, "DXT5")
    d3 = ytd.parse(rsc7.read(fixture("fer49p2025.ytd")).virtual, rsc7.read(fixture("fer49p2025.ytd")).physical)
    ytd.shrink(d3, 1024, skip=lambda t: t.name.startswith("script_rt"), converter=converter.find(), keep_mipless=False)
    assert d3.by_name()["ff"].levels == 11
    assert by["ff"].stride == 1024
    v, p, pflags = ytd.serialize(d)
    data = sum(len(t.data) for t in d.textures)
    assert data <= rsc7.flags_to_size(pflags) <= data * 1.06 + 2 * 1024 * 1024
    assert rsc7.flags_to_size(pflags) < 0.5 * f.physical_size
    assert any(x.get("method") == "resample" for x in report["details"])


@needs_magick
def test_uncompressed_texture_is_resampled_and_compressed():
    f = rsc7.read(fixture("servicevan.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    t = d.by_name()["servicevan_sign_2"]           # 4096x4096 A8R8G8B8, no mips, 64 MiB
    assert (t.format, t.levels) == ("A8R8G8B8", 1)
    c = converter.find()
    assert c.supports("A8R8G8B8")
    w, h, levels, data, fmt = c.resize(t.mip_bytes(0), t.width, t.height, t.format, 1024)
    assert (w, h, levels, fmt) == (1024, 1024, 11, "DXT5")
    assert len(data) == ytd.chain_size(1024, 1024, "DXT5", 11)


@needs_magick
def test_shrink_converts_uncompressed_and_updates_format():
    f = rsc7.read(fixture("servicevan.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    report = ytd.shrink(d, 1024, converter=converter.find())
    t = d.by_name()["servicevan_sign_2"]
    assert (t.width, t.format, t.levels, t.stride) == (1024, "DXT5", 1, 1024)   # shipped mipless, stays mipless
    assert report["skipped"] == []
    v, p, pflags = ytd.serialize(d)
    assert rsc7.flags_to_size(pflags) < 20 * 1024 * 1024
    back = ytd.parse(v, p).by_name()["servicevan_sign_2"]        # the written record must carry the new format
    assert (back.format, back.levels, back.width) == ("DXT5", 1, 1024)
    assert back.data == t.data


@needs_magick
def test_recompress_converts_small_uncompressed_textures_too():
    f = rsc7.read(fixture("servicevan.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    before = sum(1 for t in d.textures if t.format.startswith(("A8R8", "X8R8", "A8B8")))
    assert before >= 10
    report = ytd.shrink(d, 1024, converter=converter.find(), recompress=True)
    after = [t for t in d.textures if t.format.startswith(("A8R8", "X8R8", "A8B8"))]
    assert all(max(t.width, t.height) < 16 for t in after)        # only tiny ones (under one block row) are left
    env = d.by_name()["env"]
    assert (env.width, env.height, env.format) == (512, 512, "DXT5") and env.levels == 10   # shipped with 10 mips, keeps a chain
    assert any(x.get("method") == "recompress" for x in report["details"])
    v, p, pflags = ytd.serialize(d)
    assert rsc7.flags_to_size(pflags) < 8 * 1024 * 1024
