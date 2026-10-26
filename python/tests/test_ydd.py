"""Textures embedded in drawable dictionaries (.ydd): find every drawable's dictionary, guard, shrink, rewrite."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import optimize_textures as engine
import rsc7
import ydd
import yft
import ytd

V, P = ytd.VIRTUAL_TAG, ytd.PHYSICAL_TAG
DXT5 = 0x35545844


def _record(v, rec, name_at, name, width, levels, data_offset):
    struct.pack_into("<Q", v, rec + 0x28, V | name_at)
    v[name_at:name_at + len(name) + 1] = name.encode() + b"\0"
    chain = ytd.chain_size(width, width, DXT5, levels)
    struct.pack_into("<I", v, rec + 0x40, 0x20000000 | (-(-chain // 4096) << 12) | 0x2)
    struct.pack_into("<HHHH", v, rec + 0x50, width, width, 1, ytd.stride_for(width, DXT5))
    struct.pack_into("<I", v, rec + 0x58, DXT5)
    v[rec + 0x5D] = levels
    struct.pack_into("<Q", v, rec + 0x70, P | data_offset)
    return chain


def build(width=2048, levels=12, drawables=2, extra_physical=False, bogus_unaligned=False, with_dictionary=True):
    """
    A minimal .ydd: dictionary -> `drawables` drawables, each -> shader group -> texture dictionary
    with one DXT5 texture. Textures are laid out one after another in the physical segment.
    """
    v = bytearray(0x4000)
    struct.pack_into("<Q", v, 0x30, V | 0x100)                       # dictionary: drawable array
    struct.pack_into("<H", v, 0x38, drawables)
    physical = bytearray()
    sizes = []
    for i in range(drawables):
        base = 0x1000 * (i + 1)
        struct.pack_into("<Q", v, 0x100 + 8 * i, V | base)           # array[i]: drawable
        struct.pack_into("<Q", v, base + 0x10, V | (base + 0x100))   # drawable: shader group
        if with_dictionary:
            struct.pack_into("<Q", v, base + 0x108, V | (base + 0x200))   # shader group: texture dictionary
        struct.pack_into("<Q", v, base + 0x230, V | (base + 0x300)) # dictionary: texture array
        struct.pack_into("<H", v, base + 0x238, 1)
        struct.pack_into("<Q", v, base + 0x300, V | (base + 0x400)) # array[0]: record
        chain = ytd.chain_size(width, width, DXT5, levels)
        sizes.append(chain)
    flags, offsets = rsc7.pack(sizes, align=ytd.DATA_ALIGN)
    physical = bytearray(rsc7.flags_to_size(flags))
    for i in range(drawables):
        base = 0x1000 * (i + 1)
        chain = _record(v, base + 0x400, base + 0x500, f"part{i}", width, levels, offsets[i])
        physical[offsets[i]:offsets[i] + chain] = bytes(range(256))[i:] * (chain // 256 + 2)
        physical = physical[:rsc7.flags_to_size(flags)]
    if extra_physical:
        struct.pack_into("<Q", v, 0x800, P | 0x40)                   # a vertex buffer pointer into the same memory
    if bogus_unaligned:
        struct.pack_into("<Q", v, 0x808, P | 0x1234567)              # a hash that only looks like a pointer
    return bytes(v), bytes(physical), flags


def write(tmp_path, name="clothes.ydd", **kw):
    """Write the dictionary with real .ydd version nibbles in the flag words (165 = 0xA5: 0xA virtual, 0x5 physical)."""
    v, p, flags = build(**kw)
    path = str(tmp_path / name)
    rsc7.write(path, ydd.VERSION_YDD, v, p, virtual_flags=rsc7.size_to_flags(len(v)) | 0xA0000000,
               physical_flags=flags | 0x50000000)
    return path


def test_finds_every_drawables_dictionary():
    v, p, _ = build(drawables=2)
    assert ydd.texture_dictionary_offsets(v) == [0x1200, 0x2200]
    d, why = ydd.parse(v, p)
    assert why is None
    assert [(t.name, t.width, t.format, t.levels) for t in d.textures] == [("part0", 2048, "DXT5", 12), ("part1", 2048, "DXT5", 12)]
    assert all(t.data for t in d.textures)


def test_dictionary_without_textures_is_reported():
    v, p, _ = build(with_dictionary=False)
    d, why = ydd.parse(v, p)
    assert d is None and why == "no embedded textures"


def test_model_data_in_texture_memory_is_refused():
    v, p, _ = build(extra_physical=True)
    d, why = ydd.parse(v, p)
    assert why.startswith("model data shares the texture memory")


def test_a_value_that_only_looks_like_a_pointer_does_not_refuse():
    v, p, _ = build(bogus_unaligned=True)
    assert yft.physical_refs(v, len(p)) == {t.data_offset for t in ydd.parse(v, p)[0].textures}
    d, why = ydd.parse(v, p)
    assert why is None


def test_shrink_rewrites_the_file_and_keeps_the_pixels(tmp_path):
    path = write(tmp_path)
    before = rsc7.read(path)
    old = ydd.parse(before.virtual, before.physical)[0].textures
    old_mip1 = [t.mip_bytes(1) for t in old]
    mem_before, mem_after, report = engine.optimize_file(path, 1024, lambda t: False, None)
    assert report["resized"] == 2 and mem_after < mem_before
    after = rsc7.read(path)
    assert after.version == ydd.VERSION_YDD and after.virtual_flags == before.virtual_flags
    assert after.physical_flags & rsc7.VERSION_BITS == 0x50000000     # version nibble kept
    assert after.physical_flags != before.physical_flags                # but the size did change
    d, why = ydd.parse(after.virtual, after.physical)
    assert why is None
    assert [(t.width, t.height, t.levels) for t in d.textures] == [(1024, 1024, 11)] * 2
    assert [t.mip_bytes(0) for t in d.textures] == old_mip1            # old mip 1 is the new mip 0
    for t in d.textures:
        assert ytd.size_field(d, t) >> 12 & 0xFFFF == -(-len(t.data) // 4096)
    # everything outside the two texture records is byte-for-byte the original model
    for base in (0x1000, 0x2000):
        rec = slice(base + 0x440, base + 0x478)
        assert after.virtual[rec.start - 0x40:rec.start] == before.virtual[rec.start - 0x40:rec.start]
        assert after.virtual[rec.stop:rec.stop + 0x80] == before.virtual[rec.stop:rec.stop + 0x80]
    assert after.virtual[:0x1000] == before.virtual[:0x1000]


def test_refused_dictionary_is_left_untouched(tmp_path):
    path = write(tmp_path, extra_physical=True)
    raw = open(path, "rb").read()
    plan = engine.plan_file(path, "clothes.ydd", len(raw), 1024, lambda t: False, None)
    assert not plan["should_optimize"] and plan["skip_reason"].startswith("Model data shares")
    try:
        engine.optimize_file(path, 1024, lambda t: False, None)
        assert False, "should refuse"
    except engine.Unsupported:
        pass
    assert open(path, "rb").read() == raw


def test_scan_only_includes_ydd_when_asked(tmp_path):
    write(tmp_path)
    (tmp_path / "skin.ytd").write_bytes(b"")
    (tmp_path / "part.yft").write_bytes(b"")
    names = lambda yft_, ydd_: sorted(os.path.basename(f[0]) for f in engine.scan_ytd_files(str(tmp_path), yft_, ydd_))
    assert names(False, False) == ["skin.ytd"]
    assert names(True, False) == ["part.yft", "skin.ytd"]
    assert names(False, True) == ["clothes.ydd", "skin.ytd"]
    assert names(True, True) == ["clothes.ydd", "part.yft", "skin.ytd"]
