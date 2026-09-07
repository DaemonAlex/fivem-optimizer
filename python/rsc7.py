"""
RSC7 container: the on-disk format of GTA V / FiveM stream files (.ytd, .yft, .ydr, .ybn, ...).

Layout on disk:
    0x00  "RSC7"
    0x04  version (u32)           13 = texture dictionary, 162 = fragment, 165 = drawable, 43 = bounds ...
    0x08  virtual page flags (u32)
    0x0C  physical page flags (u32)
    0x10  raw DEFLATE stream (no zlib header) of: virtual segment ++ physical segment

The game does not look at the file size. It allocates exactly what the two flag words say and
inflates the stream into that memory. So:
  * the streaming cost of a .ytd is its physical segment (pixel data), of a .yft it is both segments;
  * anything that shrinks a file must rewrite the flags, or the game keeps allocating the old size.

Flag word -> byte count (CodeWalker's RpfResourceFileEntry.GetSizeFromFlags, validated against
FXServer's "Asset X uses N MiB of physical memory" boot warnings):
    base page = 0x200 << (flags & 0xF)
    pages     = 256*bit4 + 128*(bits5-6) + 64*(bits7-10) + 32*(bits11-16) + 16*(bits17-23)
                + 8*bit24 + 4*bit25 + 2*bit26 + 1*bit27
    size      = pages * base page

Files whose magic is "FXAP" are FiveM-encrypted (escrow) and cannot be read or rewritten here.
"""
import struct
import zlib
from dataclasses import dataclass

MAGIC = b"RSC7"
VERSION_YTD = 13

# (count bit width, shift, page multiple) for each field in a flag word, largest pages first.
_FIELDS = (
    (1, 4, 256),
    (2, 5, 128),
    (4, 7, 64),
    (6, 11, 32),
    (7, 17, 16),
    (1, 24, 8),
    (1, 25, 4),
    (1, 26, 2),
    (1, 27, 1),
)


class NotRsc7(ValueError):
    """The file is not a readable RSC7 resource (wrong magic, or FXAP-encrypted)."""


@dataclass
class Resource:
    version: int
    virtual_flags: int
    physical_flags: int
    virtual: bytes
    physical: bytes

    @property
    def virtual_size(self):
        return flags_to_size(self.virtual_flags)

    @property
    def physical_size(self):
        return flags_to_size(self.physical_flags)


def flags_to_size(flags):
    """Bytes the game allocates for a segment described by one flag word."""
    base = 0x200 << (flags & 0xF)
    pages = 0
    for width, shift, mult in _FIELDS:
        pages += ((flags >> shift) & ((1 << width) - 1)) * mult
    return pages * base


def size_to_flags(size):
    """Smallest flag word whose allocation covers `size` bytes (greedy fill, smallest base page first)."""
    size = max(1, int(size))
    for shift in range(16):
        base = 0x200 << shift
        pages_needed = -(-size // base)  # ceil
        flags = shift
        remaining = pages_needed
        for width, fshift, mult in _FIELDS:
            cap = (1 << width) - 1
            n = min(cap, remaining // mult)
            flags |= n << fshift
            remaining -= n * mult
        if remaining == 0:
            return flags
        # the largest bucket is full: try to absorb the remainder by rounding up one page size
        for width, fshift, mult in reversed(_FIELDS):
            cap = (1 << width) - 1
            n = (flags >> fshift) & cap
            if n < cap and remaining <= mult:
                flags = (flags & ~(cap << fshift)) | ((n + 1) << fshift)
                return flags
    raise ValueError(f"segment of {size} bytes does not fit any RSC7 page layout")


def pages_from_flags(flags):
    """The separate memory pages a flag word describes, in the order the game lays them out (largest first)."""
    base = 0x200 << (flags & 0xF)
    pages = []
    for width, shift, mult in _FIELDS:
        pages += [mult * base] * ((flags >> shift) & ((1 << width) - 1))
    return pages


def page_index(pages, offset):
    """Which page a segment offset falls in (pages are concatenated largest first)."""
    start = 0
    for i, size in enumerate(pages):
        if offset < start + size:
            return i
        start += size
    return len(pages)


def _pack_with(sizes, order, align, shift, strategy):
    """One packing attempt. strategy 'block': open the smallest page that fits the block;
    'bulk': open the smallest page that fits everything still unplaced, else the largest page available."""
    base = 0x200 << shift
    caps = [[(1 << width) - 1, mult * base] for width, _, mult in _FIELDS]   # [remaining count, page size], largest first
    pages, placed = [], {}
    remaining_total = sum(sizes)
    for i in order:
        need = sizes[i]
        slot = None
        for pg in pages:
            start = (pg[1] + align - 1) // align * align
            if start + need <= pg[0]:
                slot = (pg, start)
                break
        if slot is None:
            want = need if strategy == "block" else remaining_total
            chosen = None
            for cap in reversed(caps):                      # smallest page first
                if cap[0] > 0 and cap[1] >= want:
                    chosen = cap
                    break
            if chosen is None and strategy == "bulk":
                for cap in caps:                            # largest available page
                    if cap[0] > 0 and cap[1] >= need:
                        chosen = cap
                        break
            if chosen is None:
                return None
            chosen[0] -= 1
            pg = [chosen[1], 0]
            pages.append(pg)
            slot = (pg, 0)
        pg, start = slot
        placed[i] = (pg, start)
        pg[1] = start + need
        remaining_total -= need
    return sum(pg[0] for pg in pages), pages, placed


def pack(sizes, align=16):
    """
    Lay blocks out so no block crosses a page boundary, using the page layout with the least waste.
    Returns (flags, offsets): the flag word describing the pages and each block's segment offset.
    """
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i])
    best = None
    for shift in range(16):
        for strategy in ("block", "bulk"):
            got = _pack_with(sizes, order, align, shift, strategy)
            if got and (best is None or got[0] < best[0]):
                best = (got[0], shift, got[1], got[2])
        if best and best[0] <= sum(sizes) + (0x200 << shift):
            break
    if best is None:
        raise ValueError("blocks do not fit any RSC7 page layout")
    total, shift, pages, placed = best
    page_start, pos = {}, 0
    for pg in sorted(pages, key=lambda pg: -pg[0]):
        page_start[id(pg)] = pos
        pos += pg[0]
    base = 0x200 << shift
    counts = {}
    for pg in pages:
        counts[pg[0]] = counts.get(pg[0], 0) + 1
    flags = shift
    for width, fshift, mult in _FIELDS:
        flags |= counts.get(mult * base, 0) << fshift
    offsets = [page_start[id(placed[i][0])] + placed[i][1] for i in range(len(sizes))]
    return flags, offsets


def read_header(path):
    """(version, virtual_flags, physical_flags) from the first 16 bytes. Raises NotRsc7."""
    with open(path, "rb") as fh:
        head = fh.read(16)
    if len(head) < 16 or head[:4] != MAGIC:
        tag = head[:4].decode("latin1", "replace") if head else ""
        if tag == "FXAP":
            raise NotRsc7(f"{path}: FXAP-encrypted (FiveM escrow) resource, cannot be read")
        raise NotRsc7(f"{path}: not an RSC7 resource (magic {tag!r})")
    version, vflags, pflags = struct.unpack_from("<III", head, 4)
    return version, vflags, pflags


def read_virtual(path):
    """Inflate only the virtual segment (texture records, no pixel data) - cheap for a scan."""
    version, vflags, pflags = read_header(path)
    vsize = flags_to_size(vflags)
    d = zlib.decompressobj(-15)
    out = bytearray()
    with open(path, "rb") as fh:
        fh.seek(16)
        while len(out) < vsize:
            chunk = fh.read(65536)
            if not chunk:
                break
            out += d.decompress(chunk, vsize - len(out))
            while len(out) < vsize and d.unconsumed_tail:
                out += d.decompress(d.unconsumed_tail, vsize - len(out))
    return Resource(version, vflags, pflags, bytes(out[:vsize]), b"")


def read(path):
    """Inflate the file into its virtual and physical segments."""
    version, vflags, pflags = read_header(path)
    with open(path, "rb") as fh:
        fh.seek(16)
        payload = fh.read()
    raw = zlib.decompress(payload, -15)
    vsize = flags_to_size(vflags)
    psize = flags_to_size(pflags)
    if len(raw) < vsize + psize:
        raw = raw + b"\0" * (vsize + psize - len(raw))
    return Resource(version, vflags, pflags, raw[:vsize], raw[vsize:vsize + psize])


def write(path, version, virtual, physical, virtual_flags=None, physical_flags=None, level=9):
    """Write a resource, padding each segment to the page size its flags describe."""
    vflags = virtual_flags if virtual_flags is not None else (size_to_flags(len(virtual)) if virtual else 0)
    pflags = physical_flags if physical_flags is not None else (size_to_flags(len(physical)) if physical else 0)
    if len(virtual) > flags_to_size(vflags) or len(physical) > flags_to_size(pflags):
        raise ValueError("segment larger than its page flags allow")
    v = bytes(virtual) + b"\0" * (flags_to_size(vflags) - len(virtual)) if virtual else b""
    p = bytes(physical) + b"\0" * (flags_to_size(pflags) - len(physical)) if physical else b""
    comp = zlib.compressobj(level, zlib.DEFLATED, -15)
    payload = comp.compress(v + p) + comp.flush()
    with open(path, "wb") as fh:
        fh.write(MAGIC + struct.pack("<III", version, vflags, pflags) + payload)
    return vflags, pflags
