"""Textures embedded in fragment models (.yft): find, guard, shrink, rewrite."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture
import optimize_textures as engine
import rsc7
import yft
import ytd

MIB = 1024 * 1024
V, P = ytd.VIRTUAL_TAG, ytd.PHYSICAL_TAG
DXT5 = 0x35545844


def build(width=2048, levels=12, extra_physical=False, with_dictionary=True):
    """A minimal .yft: FragType -> drawable -> shader group -> texture dictionary with one DXT5 texture."""
    v = bytearray(0x2000)
    struct.pack_into("<Q", v, 0x30, V | 0x100)                       # FragType: drawable
    struct.pack_into("<Q", v, 0x110, V | 0x200)                      # drawable: shader group
    if with_dictionary:
        struct.pack_into("<Q", v, 0x208, V | 0x300)                  # shader group: texture dictionary
    struct.pack_into("<Q", v, 0x330, V | 0x400)                      # dictionary: texture array
    struct.pack_into("<H", v, 0x338, 1)                              # dictionary: count
    struct.pack_into("<Q", v, 0x400, V | 0x500)                      # array[0]: record
    struct.pack_into("<Q", v, 0x528, V | 0x600)                      # record: name
    v[0x600:0x605] = b"skin\0"
    chain = ytd.chain_size(width, width, DXT5, levels)
    struct.pack_into("<I", v, 0x540, 0x20000000 | (-(-chain // 4096) << 12) | 0x2)
    struct.pack_into("<HHHH", v, 0x550, width, width, 1, ytd.stride_for(width, DXT5))
    struct.pack_into("<I", v, 0x558, DXT5)
    v[0x55D] = levels
    struct.pack_into("<Q", v, 0x570, P | 0)                          # record: pixel data at physical 0
    physical = bytearray(bytes(range(256)) * (chain // 256 + 1))[:chain]
    if extra_physical:
        struct.pack_into("<Q", v, 0x800, P | 0x40)                   # a vertex buffer pointer into the same memory
    flags, _ = rsc7.pack([len(physical)], align=ytd.DATA_ALIGN)
    physical += b"\0" * (rsc7.flags_to_size(flags) - len(physical))
    return bytes(v), bytes(physical), flags


def write(tmp_path, name="part.yft", **kw):
    v, p, flags = build(**kw)
    path = str(tmp_path / name)
    rsc7.write(path, yft.VERSION_YFT, v, p, physical_flags=flags)
    return path


def test_finds_the_embedded_dictionary():
    v, p, _ = build()
    assert yft.texture_dictionary_offset(v) == 0x300
    d, why = yft.parse(v, p)
    assert why is None
    t, = d.textures
    assert (t.name, t.width, t.height, t.format, t.levels) == ("skin", 2048, 2048, "DXT5", 12)


def test_model_without_textures_is_reported():
    v, p, _ = build(with_dictionary=False)
    d, why = yft.parse(v, p)
    assert d is None and why == "no embedded textures"


def test_model_data_in_texture_memory_is_refused():
    v, p, _ = build(extra_physical=True)
    d, why = yft.parse(v, p)
    assert why.startswith("model data shares the texture memory")


def test_shrink_rewrites_the_file_and_keeps_the_pixels(tmp_path):
    path = write(tmp_path)
    before = rsc7.read(path)
    old = yft.parse(before.virtual, before.physical)[0].textures[0]
    old_mip1 = old.mip_bytes(1)
    mem_before, mem_after, report = engine.optimize_file(path, 1024, lambda t: False, None)
    assert report["resized"] == 1 and mem_after < mem_before
    after = rsc7.read(path)
    assert after.version == yft.VERSION_YFT and after.virtual_flags == before.virtual_flags
    d, why = yft.parse(after.virtual, after.physical)
    assert why is None
    t, = d.textures
    assert (t.width, t.height, t.levels) == (1024, 1024, 11)
    assert t.mip_bytes(0) == old_mip1                                # old mip 1 is the new mip 0
    assert ytd.size_field(d, t) >> 12 & 0xFFFF == -(-len(t.data) // 4096)
    # everything outside the texture record is byte-for-byte the original model
    rec = slice(0x540, 0x578)
    assert after.virtual[:rec.start] == before.virtual[:rec.start]
    assert after.virtual[rec.stop:] == before.virtual[rec.stop:]


def test_refused_model_is_left_untouched(tmp_path):
    path = write(tmp_path, extra_physical=True)
    raw = open(path, "rb").read()
    plan = engine.plan_file(path, "part.yft", len(raw), 1024, lambda t: False, None)
    assert not plan["should_optimize"] and plan["skip_reason"].startswith("Model data shares")
    try:
        engine.optimize_file(path, 1024, lambda t: False, None)
        assert False, "should refuse"
    except engine.Unsupported:
        pass
    assert open(path, "rb").read() == raw


def test_scan_only_includes_yft_when_asked(tmp_path):
    write(tmp_path)
    (tmp_path / "skin.ytd").write_bytes(b"")
    names = lambda inc: sorted(os.path.basename(f[0]) for f in engine.scan_ytd_files(str(tmp_path), inc))
    assert names(False) == ["skin.ytd"]
    assert names(True) == ["part.yft", "skin.ytd"]


def test_real_livery_part_shrinks():
    # a 64 MiB livery part: one 6000x6000 DXT5 texture with 13 mips, nothing else in physical memory
    f = rsc7.read(fixture("tfremus_livery9.yft"))
    d, why = yft.parse(f.virtual, f.physical)
    assert why is None and len(d.textures) == 1
    ytd.shrink(d, 2048)
    v, p, pflags = ytd.serialize(d)
    assert rsc7.flags_to_size(pflags) < 8 * MIB
    d2, why2 = yft.parse(v, p)
    assert why2 is None and (d2.textures[0].width, d2.textures[0].height) == (1500, 1500)
