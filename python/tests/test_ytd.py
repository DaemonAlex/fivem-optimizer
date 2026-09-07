"""Texture dictionary parse / shrink / serialize on a real vehicle .ytd."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import fixture
import rsc7
import ytd

MIB = 1024 * 1024


def load():
    f = rsc7.read(fixture("fer49p2025.ytd"))
    return f, ytd.parse(f.virtual, f.physical)


def test_parse_finds_every_texture_with_real_fields():
    _, d = load()
    assert len(d.textures) == 51
    by = {t.name: t for t in d.textures}
    skin = by["ext_skin"]
    assert (skin.width, skin.height, skin.depth, skin.stride) == (4096, 4096, 1, 4096)
    assert skin.format == "DXT5" and skin.levels == 11
    rt = by["script_rt_dials_race"]
    assert (rt.width, rt.height, rt.format, rt.levels) == (1024, 512, "DXT1", 1)


def test_mip_chain_size_is_exact_for_block_compression():
    assert ytd.mip_size(4096, 4096, "DXT5") == 16 * MIB
    assert ytd.mip_size(1024, 512, "DXT1") == 256 * 1024
    assert ytd.mip_size(2, 2, "DXT5") == 16
    assert ytd.chain_size(4096, 4096, "DXT5", 11) == 22369616
    assert ytd.mip_size(256, 256, "A8R8G8B8") == 256 * 256 * 4


def test_texture_data_regions_fit_and_do_not_overlap():
    f, d = load()
    regions = sorted((t.data_offset, t.data_offset + t.chain_size()) for t in d.textures)
    for (a0, a1), (b0, b1) in zip(regions, regions[1:]):
        assert a1 <= b0
    assert regions[-1][1] <= len(f.physical)


def test_serialize_without_changes_keeps_every_texture_and_pixel():
    f, d = load()
    v, p, pflags = ytd.serialize(d)
    d2 = ytd.parse(v, p)
    assert [(t.name, t.width, t.height, t.format, t.levels) for t in d2.textures] == \
           [(t.name, t.width, t.height, t.format, t.levels) for t in d.textures]
    assert all(a.data == b.data for a, b in zip(d.textures, d2.textures))
    data = sum(len(t.data) for t in d.textures)
    assert data <= rsc7.flags_to_size(pflags) <= data * 1.06 + 2 * MIB   # page rounding only
    pages = rsc7.pages_from_flags(pflags)
    for t in d2.textures:
        assert rsc7.page_index(pages, t.data_offset) == rsc7.page_index(pages, t.data_offset + len(t.data) - 1)


def test_shrink_drops_top_mips_and_keeps_pixels():
    f, d = load()
    orig = {t.name: (t.width, t.height, t.levels, t.mip_bytes(2)) for t in d.textures}
    report = ytd.shrink(d, 1024, skip=lambda t: t.name.startswith("script_rt"))
    by = {t.name: t for t in d.textures}
    skin = by["ext_skin"]
    assert (skin.width, skin.height, skin.levels, skin.stride) == (1024, 1024, 9, 1024)
    assert skin.mip_bytes(0) == orig["ext_skin"][3]          # old mip 2 is the new mip 0
    assert by["script_rt_dials_race"].width == 1024           # skipped by predicate
    small = [t for t in d.textures if max(orig[t.name][0], orig[t.name][1]) <= 1024]
    assert all((t.width, t.height) == orig[t.name][:2] for t in small)
    assert report["resized"] == sum(1 for n, o in orig.items() if max(o[0], o[1]) > 1024 and o[2] > 1 and not n.startswith("script_rt"))
    assert set(report["skipped"]) == {"ff", "mat", "vrc-car-body", "green", "basic"}
    assert all(x["reason"] == "no mip chain to promote" for x in report["details"] if x.get("reason"))


def test_shrunk_dictionary_reparses_and_is_smaller():
    f, d = load()
    ytd.shrink(d, 1024)
    v, p, pflags = ytd.serialize(d)
    assert len(v) == len(f.virtual)
    assert rsc7.flags_to_size(pflags) < 50 * MIB   # mip-drop alone; five big textures have no mip chain
    d2 = ytd.parse(v, p)
    assert [t.name for t in d2.textures] == [t.name for t in d.textures]
    skin = {t.name: t for t in d2.textures}["ext_skin"]
    assert (skin.width, skin.height, skin.levels) == (1024, 1024, 9)
    regions = sorted((t.data_offset, t.data_offset + t.chain_size()) for t in d2.textures)
    for (a0, a1), (b0, b1) in zip(regions, regions[1:]):
        assert a1 <= b0 and a0 % 4096 == 0
    assert regions[-1][1] <= len(p)


def test_physical_mib_is_the_engine_number():
    f, d = load()
    assert ytd.physical_mib(f) == 86.0


def test_record_size_field_matches_data_pages_in_original():
    # offset 0x40: 0x20000000 | (ceil(chain bytes / 4096) << 12) | usage bits
    f, d = load()
    for t in d.textures:
        assert ytd.size_field(d, t) >> 12 & 0xFFFF == -(-len(t.data) // 4096), t.name
        assert ytd.size_field(d, t) & 0xF0000000 == 0x20000000


def test_serialize_updates_record_size_field_after_shrink():
    f, d = load()
    usage = {t.name: ytd.size_field(d, t) & 0xFFF for t in d.textures}
    ytd.shrink(d, 1024)
    v, p, pflags = ytd.serialize(d)
    d2 = ytd.parse(v, p)
    for t in d2.textures:
        field = ytd.size_field(d2, t)
        assert field >> 12 & 0xFFFF == -(-len(t.data) // 4096), t.name
        assert field & 0xFFF == usage[t.name]
        assert field & 0xF0000000 == 0x20000000


def test_empty_dictionary_parses_to_no_textures():
    f = rsc7.read(fixture("polbufsx2.ytd"))
    d = ytd.parse(f.virtual, f.physical)
    assert d.textures == []
