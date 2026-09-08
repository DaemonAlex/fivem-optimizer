"""Audio .rel container merge: many dat151/dat54/dat10 files -> one, so the game counts one registration."""
import glob
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import relmerge

CORPUS = os.environ.get("AUDIO_FIXTURES", "")
needs_corpus = pytest.mark.skipif(not CORPUS or not glob.glob(os.path.join(CORPUS, "*/audioconfig/*.rel")), reason="set AUDIO_FIXTURES")


def corpus(kind):
    return sorted(glob.glob(os.path.join(CORPUS, "gb_vehicles_audio", "audioconfig", f"*_{kind}")))


def test_joaat_matches_known_value():
    assert relmerge.joaat("dlc_gb811s2/gb811s2") == 0x72F4DAC1


@needs_corpus
def test_every_corpus_file_round_trips_byte_for_byte():
    files = glob.glob(os.path.join(CORPUS, "*/audioconfig/*.rel"))
    assert len(files) > 100
    for f in files:
        raw = open(f, "rb").read()
        assert relmerge.write(relmerge.parse(raw)) == raw, f


@needs_corpus
def test_parse_exposes_items_names_and_references():
    r = relmerge.parse(open(corpus("sounds.dat54.rel")[0], "rb").read())
    assert r.type == 54
    assert r.names[2].lower().startswith("dlc_gb") and "\\" in r.names[2]
    assert all(r.data[off:off + ln] for _h, off, ln in r.index)
    assert all(off >= 4 for _h, off, ln in r.index)
    assert r.pack_refs() and all(isinstance(h, int) for h in r.pack_refs())


@needs_corpus
def test_merge_keeps_every_item_and_reference():
    srcs = [relmerge.parse(open(f, "rb").read()) for f in corpus("sounds.dat54.rel")[:12]]
    merged, report = relmerge.merge(srcs)
    assert merged.type == 54
    back = relmerge.parse(relmerge.write(merged))
    items = {h: back.data[off:off + ln] for h, off, ln in back.index}
    seen = {}
    for s in srcs:
        for h, off, ln in s.index:
            blob = s.data[off:off + ln]
            if h in seen and seen[h] != blob:
                continue                      # conflicting duplicate: first one wins, reported
            seen[h] = blob
            assert items[h] == blob
    assert len(back.index) == len(seen)
    assert report["items"] == len(seen) and report["dropped_identical"] >= 0
    # hash/pack table entries still point at the same hash values as in the sources
    src_hashes = sorted(h for s in srcs for h in s.hash_refs())
    assert sorted(back.hash_refs()) == src_hashes
    src_packs = sorted(h for s in srcs for h in s.pack_refs())
    assert sorted(back.pack_refs()) == src_packs
    assert set(back.names) == set(n for s in srcs for n in s.names)
    assert all(off % 4 == 0 for _h, off, _ln in back.index) or merged.type == 54


@needs_corpus
def test_merge_rewrites_wave_pack_references():
    srcs = [relmerge.parse(open(f, "rb").read()) for f in corpus("sounds.dat54.rel")[:3]]
    merged, report = relmerge.merge(srcs, pack_rename=lambda pack: "dlc_gbaudio")
    back = relmerge.parse(relmerge.write(merged))
    assert relmerge.joaat("dlc_gb811s2/gb811s2") not in back.pack_refs()
    assert relmerge.joaat("dlc_gbaudio/gb811s2") in back.pack_refs()
    assert any(n.lower() == "dlc_gbaudio\\gb811s2" for n in back.names)
    assert not any(n.lower().startswith("dlc_gb811s2") for n in back.names)
    assert report["packs"] and all(v == "dlc_gbaudio" for v in report["packs"].values())


@needs_corpus
def test_merge_reports_conflicting_duplicates():
    files = corpus("sounds.dat54.rel")
    srcs = [relmerge.parse(open(f, "rb").read(), name=os.path.basename(f)) for f in files]
    merged, report = relmerge.merge(srcs)
    assert isinstance(report["conflicts"], list)
    for c in report["conflicts"]:
        assert set(c) >= {"hash", "kept", "dropped"}


def test_refuses_to_merge_different_types():
    a = relmerge.Rel(151, b"\0\0\0\0", [], [], [], [])
    b = relmerge.Rel(54, b"\0\0\0\0", [], [], [], [])
    with pytest.raises(ValueError):
        relmerge.merge([a, b])


@needs_corpus
def test_every_shipped_file_keeps_its_index_in_lookup_order():
    # the game binary-searches the index by the byte-rotated hash; every shipped file is in that order
    files = corpus("game.dat151.rel") + corpus("sounds.dat54.rel")
    assert files
    for f in files:
        assert relmerge.index_sorted(relmerge.parse(open(f, "rb").read())), f


@needs_corpus
def test_merge_keeps_index_in_lookup_order():
    # appended, unsorted indexes load without error and play nothing: the lookup misses past the first source
    srcs = [relmerge.parse(open(f, "rb").read()) for f in corpus("sounds.dat54.rel")[:12]]
    assert len(srcs) > 1
    merged, _ = relmerge.merge(srcs)
    assert relmerge.index_sorted(merged)
    assert relmerge.index_sorted(relmerge.parse(relmerge.write(merged)))


def test_rotated_key_is_the_hash_rotated_right_by_a_byte():
    assert relmerge.rotated(0x12345678) == 0x78123456
    assert relmerge.rotated(0x000000FF) == 0xFF000000
