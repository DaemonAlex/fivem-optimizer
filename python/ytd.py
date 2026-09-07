"""
Texture dictionary (.ytd) parsing and in-place shrinking on top of the RSC7 container.

A .ytd's virtual segment holds a pgDictionary<grcTexture>: a pointer array to 0x90-byte texture
records plus a sorted name-hash array. Each record points at its pixel data in the physical
segment, where every texture's full mip chain is stored contiguously (mip 0 first), and each
texture starts on a 4 KiB boundary.

Record fields used here (offsets inside the 0x90-byte record):
    0x28  name pointer      (u64, virtual segment, NUL-terminated string)
    0x40  size/usage word   (u32) 0x20000000 | (pixel data bytes in 4 KiB pages) << 12 | usage bits (low 12)
                            - must follow the data: a stale (larger) value makes the engine read past the
                            mip chain into the next texture, which shows as flickering on the model
    0x50  width  (u16)      0x52 height (u16)     0x54 depth (u16)     0x56 stride (u16, bytes per pixel row of mip 0)
    0x58  format (u32)      FourCC ("DXT1", "DXT5", "ATI2"...) or a D3DFMT number for uncompressed formats
    0x5D  mip levels (u8)
    0x70  data pointer      (u64, physical segment)

Shrinking to a target resolution = dropping the top mip levels: the pixel data for the lower level
already exists, so the result keeps the same compression, the same mip chain below it, and needs no
image library. A texture with a single mip level cannot be shrunk this way.

Pointers are tagged: 0x50000000 | offset for the virtual segment, 0x60000000 | offset for physical.
"""
import struct
from dataclasses import dataclass, field

VIRTUAL_TAG = 0x50000000
PHYSICAL_TAG = 0x60000000
OFFSET_MASK = 0x0FFFFFFF
RECORD_SIZE = 0x90
DATA_ALIGN = 0x1000

# format code -> (name, bytes per 4x4 block) for block-compressed formats
_BLOCK = {
    0x31545844: ("DXT1", 8),
    0x33545844: ("DXT3", 16),
    0x35545844: ("DXT5", 16),
    0x31495441: ("ATI1", 8),
    0x32495441: ("ATI2", 16),
}
# D3DFMT number -> (name, bytes per pixel) for uncompressed formats
_PIXEL = {
    21: ("A8R8G8B8", 4),
    22: ("X8R8G8B8", 4),
    32: ("A8B8G8R8", 4),
    28: ("A8", 1),
    50: ("L8", 1),
    52: ("A8L8", 2),
    23: ("R5G6B5", 2),
    25: ("A1R5G5B5", 2),
    26: ("X1R5G5B5", 2),
    36: ("A16B16G16R16", 8),
    113: ("A16B16G16R16F", 8),
    111: ("R16F", 2),
    114: ("R32F", 4),
}


def format_name(code):
    if code in _BLOCK:
        return _BLOCK[code][0]
    if code in _PIXEL:
        return _PIXEL[code][0]
    return "0x%08X" % code


def _by_name(name):
    for code, (n, size) in _BLOCK.items():
        if n == name:
            return code
    for code, (n, size) in _PIXEL.items():
        if n == name:
            return code
    return None


def mip_size(width, height, fmt):
    """Bytes of one mip level. `fmt` is a format name or code."""
    code = fmt if isinstance(fmt, int) else _by_name(fmt)
    if code in _BLOCK:
        bw = max(1, (width + 3) // 4)
        bh = max(1, (height + 3) // 4)
        return bw * bh * _BLOCK[code][1]
    if code in _PIXEL:
        return max(1, width) * max(1, height) * _PIXEL[code][1]
    raise ValueError(f"unknown texture format {fmt!r}")


def chain_size(width, height, fmt, levels):
    total = 0
    for i in range(levels):
        total += mip_size(max(1, width >> i), max(1, height >> i), fmt)
    return total


def stride_for(width, fmt):
    """Bytes per pixel row of mip 0, as the record stores it."""
    code = fmt if isinstance(fmt, int) else _by_name(fmt)
    if code in _BLOCK:
        return max(1, (width * _BLOCK[code][1]) // 16)  # 8 or 16 bytes per 4-pixel-wide block row / 4 rows
    if code in _PIXEL:
        return width * _PIXEL[code][1]
    raise ValueError(f"unknown texture format {fmt!r}")


@dataclass
class Texture:
    record_offset: int
    name: str
    width: int
    height: int
    depth: int
    stride: int
    format_code: int
    levels: int
    data_offset: int
    data: bytes = field(repr=False)

    @property
    def format(self):
        return format_name(self.format_code)

    @property
    def known_format(self):
        return self.format_code in _BLOCK or self.format_code in _PIXEL

    def chain_size(self):
        if self.known_format:
            return chain_size(self.width, self.height, self.format_code, self.levels)
        return len(self.data)

    def mip_offset(self, level):
        return chain_size(self.width, self.height, self.format_code, level)

    def mip_bytes(self, level):
        start = self.mip_offset(level)
        size = mip_size(max(1, self.width >> level), max(1, self.height >> level), self.format_code)
        return self.data[start:start + size]


@dataclass
class Dictionary:
    virtual: bytearray
    textures: list

    def by_name(self):
        return {t.name: t for t in self.textures}


SIZE_FIELD = 0x40


def size_field(d, t):
    return struct.unpack_from("<I", d.virtual, t.record_offset + SIZE_FIELD)[0]


def _cstring(buf, offset):
    end = buf.find(b"\0", offset)
    return buf[offset:end if end >= 0 else len(buf)].decode("latin1")


def parse(virtual, physical=None):
    """Read every texture record. Pixel data is sliced out of the physical segment when one is given."""
    v = bytearray(virtual)
    tex_ptr = struct.unpack_from("<Q", v, 0x30)[0]
    count = struct.unpack_from("<H", v, 0x38)[0]
    if count == 0 or tex_ptr == 0:
        return Dictionary(v, [])                     # an empty dictionary (some packs ship one)
    if (tex_ptr & 0xF0000000) != VIRTUAL_TAG:
        raise ValueError("not a texture dictionary: texture array pointer is not virtual")
    array = tex_ptr & OFFSET_MASK
    records = []
    for i in range(count):
        ptr = struct.unpack_from("<Q", v, array + 8 * i)[0]
        records.append(ptr & OFFSET_MASK)

    textures = []
    for rec in records:
        name_ptr = struct.unpack_from("<Q", v, rec + 0x28)[0]
        width, height, depth, stride = struct.unpack_from("<HHHH", v, rec + 0x50)
        fmt = struct.unpack_from("<I", v, rec + 0x58)[0]
        levels = v[rec + 0x5D]
        data_ptr = struct.unpack_from("<Q", v, rec + 0x70)[0]
        textures.append(Texture(rec, _cstring(v, name_ptr & OFFSET_MASK), width, height, depth, stride,
                                fmt, levels, data_ptr & OFFSET_MASK, b""))

    if physical is None:
        return Dictionary(v, textures)
    # slice pixel data: known formats by exact chain size, unknown ones up to the next texture
    order = sorted(textures, key=lambda t: t.data_offset)
    for i, t in enumerate(order):
        end = order[i + 1].data_offset if i + 1 < len(order) else len(physical)
        size = chain_size(t.width, t.height, t.format_code, t.levels) if t.known_format else end - t.data_offset
        if t.data_offset + size > len(physical):
            raise ValueError(f"texture {t.name}: data runs past the physical segment")
        t.data = bytes(physical[t.data_offset:t.data_offset + size])
    return Dictionary(v, textures)


UNCOMPRESSED = {21, 22, 32}   # A8R8G8B8, X8R8G8B8, A8B8G8R8: 4 bytes per pixel, 4-8x the memory of DXT


def shrink(d, target, skip=None, converter=None, recompress=False):
    """
    Bring every texture down to max(width, height) <= target.
    Mip levels are dropped first (exact, no image processing). A texture that has no mip chain to
    promote is resampled through `converter` when one is given, otherwise it is skipped.
    With `recompress`, 32-bit uncompressed textures of 16 px or more are also re-encoded as DXT at
    their current size (DXT5 when they carry alpha, DXT1 otherwise), with a full mip chain.
    Returns a report dict.
    """
    report = {"resized": 0, "unchanged": 0, "skipped": [], "details": []}

    def skipped(t, reason):
        report["skipped"].append(t.name)
        report["details"].append({"name": t.name, "reason": reason})

    for t in d.textures:
        if max(t.width, t.height) <= target:
            if recompress and converter is not None and t.format_code in UNCOMPRESSED and min(t.width, t.height) >= 16 \
                    and not (skip and skip(t)) and converter.supports(t.format):
                before = (t.width, t.height, t.levels, t.format)
                try:
                    w, h, levels, data, fmt = converter.resize(t.mip_bytes(0), t.width, t.height, t.format, max(t.width, t.height))
                except Exception as e:
                    skipped(t, f"{converter.name}: {e}")
                    continue
                t.width, t.height, t.levels, t.data = w, h, levels, data
                t.format_code = _by_name(fmt)
                t.stride = stride_for(w, t.format_code)
                report["resized"] += 1
                report["details"].append({"name": t.name, "from": "%dx%d %s" % (before[0], before[1], before[3]), "to": "%dx%d %s" % (w, h, fmt),
                                          "levels": [before[2], t.levels], "format": t.format, "method": "recompress"})
                continue
            report["unchanged"] += 1
            continue
        if skip and skip(t):
            skipped(t, "skipped by rule")
            continue
        if not t.known_format:
            skipped(t, f"unknown format {t.format}")
            continue
        before = (t.width, t.height, t.levels)
        drop = 0
        w, h = t.width, t.height
        while max(w, h) > target and drop < t.levels - 1:
            w, h = max(1, w >> 1), max(1, h >> 1)
            drop += 1
        if max(w, h) > target and converter is None:
            skipped(t, "no mip chain to promote")
            continue
        if drop:
            t.data = t.data[t.mip_offset(drop):]
            t.width, t.height, t.levels = w, h, t.levels - drop
            t.stride = stride_for(w, t.format_code)
        method = "mipdrop"
        if max(t.width, t.height) > target:
            try:
                w, h, levels, data, fmt = converter.resize(t.mip_bytes(0), t.width, t.height, t.format, target)
            except Exception as e:  # converter missing a format, or failed
                skipped(t, f"{converter.name}: {e}")
                continue
            t.width, t.height, t.levels, t.data = w, h, levels, data
            t.format_code = _by_name(fmt)
            t.stride = stride_for(w, t.format_code)
            method = "resample"
        report["resized"] += 1
        report["details"].append({"name": t.name, "from": "%dx%d" % before[:2], "to": "%dx%d" % (t.width, t.height),
                                  "levels": [before[2], t.levels], "format": t.format, "method": method})
    return report


def serialize(d):
    """
    Rebuild the dictionary: records patched, pixel data packed into RSC7 pages so no texture
    straddles a page. Returns (virtual, physical, physical_flags).
    """
    import rsc7
    v = bytearray(d.virtual)
    flags, offsets = rsc7.pack([len(t.data) for t in d.textures], align=DATA_ALIGN)
    physical = bytearray(rsc7.flags_to_size(flags))
    for t, offset in zip(d.textures, offsets):
        physical[offset:offset + len(t.data)] = t.data
        struct.pack_into("<HHHH", v, t.record_offset + 0x50, t.width, t.height, t.depth, t.stride)
        struct.pack_into("<I", v, t.record_offset + 0x58, t.format_code)
        v[t.record_offset + 0x5D] = t.levels
        struct.pack_into("<Q", v, t.record_offset + 0x70, PHYSICAL_TAG | offset)
        usage = struct.unpack_from("<I", v, t.record_offset + SIZE_FIELD)[0] & 0xFFF
        pages = -(-len(t.data) // DATA_ALIGN)
        struct.pack_into("<I", v, t.record_offset + SIZE_FIELD, 0x20000000 | (pages << 12) | usage)
        t.data_offset = offset
    return bytes(v), bytes(physical), flags


def physical_mib(resource):
    return round(resource.physical_size / 1048576, 1)
