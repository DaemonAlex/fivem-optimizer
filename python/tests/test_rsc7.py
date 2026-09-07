"""RSC7 container: header flag maths and the deflate-packed segments."""
import os
import sys
import struct
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture
import rsc7

MIB = 1024 * 1024


def test_decode_flags_matches_engine_allocation():
    # fer49p2025.ytd header: FXServer reports this asset at 86 MiB physical
    assert rsc7.flags_to_size(0xDD04000C) == 86 * MIB
    assert rsc7.flags_to_size(0x00040000) == 16384
    # brown_prison_col.ybn virtual flags
    assert rsc7.flags_to_size(0x2C060005) > 0


def test_encode_flags_covers_size_without_waste():
    for size in (1, 0x200, 16384, 22372352, 86 * MIB, 90177536, 1234567):
        flags = rsc7.size_to_flags(size)
        got = rsc7.flags_to_size(flags)
        assert got >= size
        assert got - size < max(0x200, size // 8), (size, got)


def test_encode_is_stable_for_real_headers():
    for flags in (0xDD04000C, 0x00040000, 0xD0000A41, 0x00020000):
        size = rsc7.flags_to_size(flags)
        assert rsc7.flags_to_size(rsc7.size_to_flags(size)) == size


def test_read_fixture_splits_segments():
    f = rsc7.read(fixture("fer49p2025.ytd"))
    assert f.version == 13
    assert len(f.virtual) == 16384
    assert len(f.physical) == 86 * MIB
    assert f.virtual_size == 16384 and f.physical_size == 86 * MIB


def test_read_rejects_encrypted_and_foreign_files(tmp_path):
    p = tmp_path / "x.ydr"
    p.write_bytes(b"FXAP" + b"\0" * 60)
    try:
        rsc7.read(str(p))
        assert False, "expected NotRsc7"
    except rsc7.NotRsc7 as e:
        assert "FXAP" in str(e)


def test_write_then_read_roundtrip(tmp_path):
    src = rsc7.read(fixture("fer49p2025.ytd"))
    out = tmp_path / "rt.ytd"
    rsc7.write(str(out), src.version, src.virtual, src.physical)
    back = rsc7.read(str(out))
    assert back.version == 13
    assert back.virtual == src.virtual
    assert back.physical == src.physical
    raw = out.read_bytes()
    assert raw[:4] == b"RSC7"
    # header flags must describe the segments the game will allocate
    vf, pf = struct.unpack_from("<II", raw, 8)
    assert rsc7.flags_to_size(vf) == len(src.virtual)
    assert rsc7.flags_to_size(pf) == len(src.physical)
    # payload is a raw deflate stream exactly the size of the two segments
    assert len(zlib.decompress(raw[16:], -15)) == len(src.virtual) + len(src.physical)


def test_write_pads_segments_to_page_size(tmp_path):
    out = tmp_path / "pad.ytd"
    rsc7.write(str(out), 13, b"\x01" * 100, b"\x02" * 5000)
    back = rsc7.read(str(out))
    assert back.virtual[:100] == b"\x01" * 100 and len(back.virtual) == back.virtual_size
    assert back.physical[:5000] == b"\x02" * 5000 and len(back.physical) == back.physical_size


def test_pages_from_flags_lists_pages_largest_first():
    assert rsc7.pages_from_flags(0xDD04000C) == [32 * MIB, 32 * MIB, 16 * MIB, 4 * MIB, 2 * MIB]
    assert rsc7.pages_from_flags(0x00040000) == [8192, 8192]   # two 16-page blocks of the 512-byte base


def test_original_file_never_straddles_a_page():
    import ytd
    f = rsc7.read(fixture("fer49p2025.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    pages = rsc7.pages_from_flags(f.physical_flags)
    for t in d.textures:
        assert rsc7.page_index(pages, t.data_offset) == rsc7.page_index(pages, t.data_offset + len(t.data) - 1), t.name


def test_pack_places_every_block_inside_one_page():
    sizes = [22369616] + [5592400] * 5 + [4362240] * 3 + [2097152] * 2 + [100] * 40
    flags, offsets = rsc7.pack(sizes, align=4096)
    pages = rsc7.pages_from_flags(flags)
    total = rsc7.flags_to_size(flags)
    for size, off in zip(sizes, offsets):
        assert off % 4096 == 0
        assert off + size <= total
        assert rsc7.page_index(pages, off) == rsc7.page_index(pages, off + size - 1)
    # blocks do not overlap
    spans = sorted(zip(offsets, sizes))
    for (a, sa), (b, sb) in zip(spans, spans[1:]):
        assert a + sa <= b


def test_pack_does_not_waste_pages():
    sizes = [22369616] + [5592400] * 5 + [4362240] * 3 + [2097152] * 2 + [100] * 40
    flags, _ = rsc7.pack(sizes, align=4096)
    assert rsc7.flags_to_size(flags) <= sum(sizes) * 1.15
    flags, _ = rsc7.pack([100], align=16)
    assert rsc7.flags_to_size(flags) <= 0x200


def test_write_accepts_explicit_flags(tmp_path):
    out = tmp_path / "flags.ytd"
    pflags = rsc7.size_to_flags(8192)
    rsc7.write(str(out), 13, b"\x01" * 100, b"\x02" * 5000, physical_flags=pflags)
    back = rsc7.read(str(out))
    assert back.physical_flags == pflags and len(back.physical) == rsc7.flags_to_size(pflags)


def test_read_virtual_gives_records_without_inflating_pixels():
    import ytd
    r = rsc7.read_virtual(fixture("fer49p2025.ytd"))
    assert len(r.virtual) == 16384 and r.physical == b"" and r.physical_size == 86 * MIB
    d = ytd.parse(r.virtual)
    assert len(d.textures) == 51 and d.by_name()["ext_skin"].width == 4096


def test_pack_many_third_size_blocks_stays_tight():
    sizes = [1398128] * 24 + [349552] * 20 + [5000] * 7
    flags, _ = rsc7.pack(sizes, align=4096)
    assert rsc7.flags_to_size(flags) <= sum(sizes) * 1.06 + 2 * MIB
