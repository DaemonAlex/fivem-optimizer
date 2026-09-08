"""
Merge GTA V audio .rel containers (dat151 game data, dat54 sound data, dat10 synth data).

Why: FiveM stops registering addon audio after roughly 190 banks, and everything past that is
silent. A merged file counts as one registration however many sounds it holds.

Container layout (CodeWalker RelFile.Load / Save, verified byte-for-byte on 634 real files):
    u32 type            151 / 54 / 10 / 4
    u32 data length
    bytes data          first 4 bytes are a per-file value; items follow, addressed by the index
    u32 name table length, u32 name count, u32 offsets[count], NUL-terminated names
    u32 index count,    (u32 name hash, u32 offset, u32 length) per item
    u32 hash count,     u32 offsets[]   -> positions (from the FILE start, i.e. data offset + 8) of hashes of other items
    u32 pack count,     u32 offsets[]   -> positions (file start) of hashes of "packfolder/wavename"

Items reference each other by hash, so concatenating data blocks is valid once every offset in the
index, hash table and pack table is shifted. Wave containers are referenced by the hash of
"dlc_pack/wave" at pack-table positions, so waves can move into one folder by rewriting those hashes
(and the matching name-table strings "DLC_pack\\wave").

Duplicates: identical items under the same hash are dropped; differing ones keep the first and are
reported, because the game would otherwise pick one at random.

The index must stay sorted by the rotated hash (see rotated()): the game finds items by binary search.
"""
import struct
from dataclasses import dataclass, field


HEADER = 8   # type + data length precede the data block; the two offset tables count from the file start


def joaat(s):
    h = 0
    for c in s.encode("latin1"):
        h = (h + c) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    h = (h + (h << 15)) & 0xFFFFFFFF
    return h


@dataclass
class Rel:
    type: int
    data: bytes
    names: list
    index: list            # [(hash, offset, length)]
    hash_offsets: list     # positions in data
    pack_offsets: list     # positions in data
    name: str = ""

    def hash_refs(self):
        return [struct.unpack_from("<I", self.data, o)[0] for o in self.hash_offsets]

    def pack_refs(self):
        return [struct.unpack_from("<I", self.data, o)[0] for o in self.pack_offsets]


def parse(raw, name=""):
    o = 0
    rtype, dlen = struct.unpack_from("<II", raw, o)
    o += 8
    data = raw[o:o + dlen]
    o += dlen
    ntl, ntc = struct.unpack_from("<II", raw, o)
    o += 8
    o += 4 * ntc                                   # offsets are implied by the strings
    names = []
    for _ in range(ntc):
        end = raw.index(b"\0", o)
        names.append(raw[o:end].decode("latin1"))
        o = end + 1
    ic = struct.unpack_from("<I", raw, o)[0]
    o += 4
    index = [struct.unpack_from("<III", raw, o + 12 * i) for i in range(ic)]
    o += 12 * ic
    hc = struct.unpack_from("<I", raw, o)[0]
    o += 4
    hashes = [x - HEADER for x in struct.unpack_from("<%dI" % hc, raw, o)]   # kept data-relative in memory
    o += 4 * hc
    pc = struct.unpack_from("<I", raw, o)[0]
    o += 4
    packs = [x - HEADER for x in struct.unpack_from("<%dI" % pc, raw, o)]
    o += 4 * pc
    if o != len(raw):
        raise ValueError(f"{name or 'rel'}: {len(raw) - o} trailing bytes after the pack table")
    return Rel(rtype, bytes(data), names, [tuple(x) for x in index], hashes, packs, name)


def write(rel):
    out = bytearray(struct.pack("<II", rel.type, len(rel.data)))
    out += rel.data
    encoded = [n.encode("latin1") + b"\0" for n in rel.names]
    strings = b"".join(encoded)
    ntl = 4 + 4 * len(encoded) + len(strings)          # count field + offsets + strings
    out += struct.pack("<II", ntl, len(encoded))
    pos = 0
    for e in encoded:
        out += struct.pack("<I", pos)
        pos += len(e)
    out += strings
    out += struct.pack("<I", len(rel.index))
    for h, off, ln in rel.index:
        out += struct.pack("<III", h, off, ln)
    out += struct.pack("<I", len(rel.hash_offsets)) + struct.pack("<%dI" % len(rel.hash_offsets), *[x + HEADER for x in rel.hash_offsets])
    out += struct.pack("<I", len(rel.pack_offsets)) + struct.pack("<%dI" % len(rel.pack_offsets), *[x + HEADER for x in rel.pack_offsets])
    return bytes(out)


def _split_container(name):
    """'DLC_gb811s2\\gb811s2' -> ('dlc_gb811s2', 'gb811s2'); None when not a pack path."""
    if "\\" in name:
        pack, wave = name.split("\\", 1)
        return pack.lower(), wave.lower()
    return None


def _rename(pack_rename, pack, wave):
    """pack_rename may take (pack) or (pack, wave); returns the new folder or None."""
    try:
        return pack_rename(pack, wave)
    except TypeError:
        return pack_rename(pack)


def merge(rels, pack_rename=None):
    """
    -> (merged Rel, report). `pack_rename(pack_folder[, wave]) -> new_folder` moves each wave
    reference into the returned folder; return the same folder for every wave for a single pack,
    or spread waves across several folders (the game copes better with smaller wave packs).
    """
    types = {r.type for r in rels}
    if len(types) != 1:
        raise ValueError(f"cannot merge different rel types {sorted(types)}")
    rtype = rels[0].type
    data = bytearray(rels[0].data[:4])
    index, hash_offsets, pack_offsets = [], [], []
    names = []
    seen = {}
    report = {"items": 0, "dropped_identical": 0, "conflicts": [], "packs": {}, "sources": len(rels)}

    # container-hash rewrite map, built from every source's name table
    rewrite = {}
    for r in rels:
        for n in r.names:
            split = _split_container(n)
            if split and pack_rename:
                pack, wave = split
                new = _rename(pack_rename, pack, wave)
                if new and new != pack:
                    rewrite[joaat(f"{pack}/{wave}")] = joaat(f"{new}/{wave}")
                    report["packs"][pack] = new

    for r in rels:
        blob = bytearray(r.data[4:])
        base = len(data) - 4                       # item offset shift: old offset o -> o + base
        keep = {}
        for h, off, ln in r.index:
            item = bytes(r.data[off:off + ln])
            if h in seen:
                if seen[h][0] == item:
                    report["dropped_identical"] += 1
                else:
                    report["conflicts"].append({"hash": h, "kept": seen[h][1], "dropped": r.name or "?", "length": [len(seen[h][0]), ln]})
                continue
            seen[h] = (item, r.name or "?")
            keep[(off, ln)] = h
        if not keep:
            continue
        # keep the whole block (simplest, offsets stay valid); mark dropped items' spans as dead space
        data += blob
        for (off, ln), h in keep.items():
            index.append((h, off + base, ln))
        kept_spans = sorted(keep)
        def inside(pos):
            return any(a <= pos < a + b for a, b in kept_spans)
        for o in r.hash_offsets:
            if inside(o):
                hash_offsets.append(o + base)
        for o in r.pack_offsets:
            if inside(o):
                pack_offsets.append(o + base)
                v = struct.unpack_from("<I", r.data, o)[0]
                if v in rewrite:
                    struct.pack_into("<I", data, o + base, rewrite[v])
        while len(data) % 4:
            data.append(0)
        for n in r.names:
            split = _split_container(n)
            if split and pack_rename:
                new = _rename(pack_rename, split[0], split[1])
                if new and new != split[0]:
                    folder = "DLC_" + new[4:] if new.startswith("dlc_") else new
                    n = folder + "\\" + n.split("\\", 1)[1]
            if n not in names:
                names.append(n)
    # The game binary-searches the index by a byte-rotated hash (CodeWalker RelFile.BuildIndex sorts the
    # same way; every shipped file checked, 634 of 634, is in this order). An appended, unsorted index
    # makes every lookup past the first source miss: the bank loads, the car stays silent.
    index.sort(key=lambda e: rotated(e[0]))
    report["items"] = len(index)
    return Rel(rtype, bytes(data), names, index, hash_offsets, pack_offsets, "merged"), report


def rotated(h):
    """Index sort key: hash rotated right by 8 bits, as the game orders its lookup table."""
    return ((h >> 8) | ((h << 24) & 0xFFFFFFFF)) & 0xFFFFFFFF


def index_sorted(rel):
    """True when the index is in the game's lookup order."""
    keys = [rotated(h) for h, _o, _l in rel.index]
    return keys == sorted(keys)
