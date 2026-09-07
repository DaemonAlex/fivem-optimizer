"""
Minimal DDS container for handing block-compressed textures to an external converter and back.

Only what the optimizer needs: a 128-byte legacy header with a FourCC (DXT1/DXT3/DXT5/ATI1/ATI2),
reading the DX10 extension header that texconv may emit, and the raw mip chain that follows.
"""
import struct

_FLAGS = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000   # caps, height, width, pixelformat, mipmapcount, linearsize
_CAPS_TEXTURE = 0x1000
_CAPS_MIPMAP = 0x400000
_CAPS_COMPLEX = 0x8

FOURCC = {"DXT1": b"DXT1", "DXT3": b"DXT3", "DXT5": b"DXT5", "ATI1": b"ATI1", "ATI2": b"ATI2"}
_BY_FOURCC = {v: k for k, v in FOURCC.items()}
_BY_FOURCC.update({b"BC4U": "ATI1", b"BC5U": "ATI2"})
# DXGI_FORMAT -> name (UNORM and SRGB variants)
_DXGI = {71: "DXT1", 72: "DXT1", 74: "DXT3", 75: "DXT3", 77: "DXT5", 78: "DXT5", 80: "ATI1", 83: "ATI2"}
_BLOCK_BYTES = {"DXT1": 8, "DXT3": 16, "DXT5": 16, "ATI1": 8, "ATI2": 16}


# uncompressed formats: (bit count, R, G, B, A masks); pixel format flags = RGB | ALPHAPIXELS
_RGB = {"A8R8G8B8": (32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000),
        "X8R8G8B8": (32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0),
        "A8B8G8R8": (32, 0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000)}


def write(width, height, fmt, levels, data):
    """Legacy-header DDS for a block-compressed or 32-bit uncompressed mip chain."""
    if fmt in FOURCC:
        linear = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * _BLOCK_BYTES[fmt]
        pixel = struct.pack("<II4sIIIII", 32, 0x4, FOURCC[fmt], 0, 0, 0, 0, 0)
        flags = _FLAGS
    elif fmt in _RGB:
        bits, r, g, b, a = _RGB[fmt]
        linear = width * bits // 8                                             # pitch
        pixel = struct.pack("<II4sIIIII", 32, 0x40 | (0x1 if a else 0), b"\0\0\0\0", bits, r, g, b, a)
        flags = (_FLAGS & ~0x80000) | 0x8                                      # pitch instead of linearsize
    else:
        raise ValueError(f"DDS export does not support {fmt}")
    caps = _CAPS_TEXTURE | (_CAPS_MIPMAP | _CAPS_COMPLEX if levels > 1 else 0)
    header = struct.pack("<4sIIIIIII", b"DDS ", 124, flags, height, width, linear, 0, levels)
    header += b"\0" * 44                                                       # reserved1[11]
    header += pixel                                                            # pixel format
    header += struct.pack("<IIIII", caps, 0, 0, 0, 0)                          # caps1-4 + reserved2
    assert len(header) == 128
    return header + bytes(data)


def read(blob):
    """-> (width, height, format name, levels, mip chain bytes)."""
    if len(blob) < 128 or blob[:4] != b"DDS ":
        raise ValueError("not a DDS file")
    height, width = struct.unpack_from("<II", blob, 12)
    levels = struct.unpack_from("<I", blob, 28)[0] or 1
    pf_flags = struct.unpack_from("<I", blob, 80)[0]
    fourcc = blob[84:88]
    offset = 128
    if fourcc == b"DX10":
        dxgi = struct.unpack_from("<I", blob, 128)[0]
        if dxgi not in _DXGI:
            raise ValueError(f"unsupported DXGI format {dxgi}")
        fmt = _DXGI[dxgi]
        offset = 148
    elif pf_flags & 0x4 and fourcc in _BY_FOURCC:
        fmt = _BY_FOURCC[fourcc]
    elif pf_flags & 0x40:
        bits, r, g, b, a = struct.unpack_from("<IIIII", blob, 88)
        match = [k for k, v in _RGB.items() if v == (bits, r, g, b, a)]
        if not match:
            raise ValueError(f"unsupported uncompressed DDS layout {bits} bpp masks {r:#x} {g:#x} {b:#x} {a:#x}")
        fmt = match[0]
    else:
        raise ValueError(f"unsupported DDS pixel format {fourcc!r}")
    return width, height, fmt, levels, blob[offset:]
