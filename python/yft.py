"""
Textures embedded in a fragment model (.yft): find them, and decide whether they can be shrunk safely.

A .yft is an RSC7 resource (version 162) whose virtual segment starts with a FragType. Its main
drawable can carry its own texture dictionary, the same pgDictionary<grcTexture> layout a .ytd
holds, and vehicle livery and sticker parts often ship one huge texture that way (4096 or 6000 px).

    FragType    +0x30  drawable pointer      (u64, virtual)
    Drawable    +0x10  shader group pointer  (u64, virtual)
    ShaderGroup +0x08  texture dictionary    (u64, virtual, 0 when the model has no embedded textures)

The physical segment of a .yft can also hold model data (vertex and index buffers) next to the
pixels. Rebuilding that segment means moving every block in it, and a missed pointer to model data
would corrupt the model. So a .yft is only rewritten when every physical pointer in its virtual
segment is a texture data pointer from the dictionary: the physical segment is then pixel data and
nothing else, and ytd.serialize rebuilds it exactly as it does for a .ytd. Anything else is
reported and left alone.
"""
import struct

import ytd

VERSION_YFT = 162
_M = ytd.OFFSET_MASK


def _virtual(p):
    """Offset of a virtual pointer, or None for null or anything that is not one."""
    return (p & _M) if p >> 32 == 0 and (p & 0xF0000000) == ytd.VIRTUAL_TAG else None


def _u64(buf, off):
    return struct.unpack_from("<Q", buf, off)[0] if 0 <= off <= len(buf) - 8 else 0


def texture_dictionary_offset(virtual):
    """Virtual offset of the main drawable's embedded texture dictionary, or None when it has none."""
    drawable = _virtual(_u64(virtual, 0x30))
    if drawable is None:
        return None
    shader_group = _virtual(_u64(virtual, drawable + 0x10))
    if shader_group is None:
        return None
    return _virtual(_u64(virtual, shader_group + 0x08))


BLOCK_ALIGN = 16   # every block in the physical segment (pixels, vertex and index buffers) starts on a 16-byte boundary


def physical_refs(virtual, physical_size, align=BLOCK_ALIGN):
    """
    Every 8-byte-aligned value in the virtual segment that is a pointer into the physical segment.
    A value whose target is not block-aligned is not a pointer (a hash or a float that happens to
    carry the tag) and is left out, so it cannot refuse a file that is in fact safe to rewrite.
    """
    refs = set()
    for off in range(0, len(virtual) - 7, 8):
        q = struct.unpack_from("<Q", virtual, off)[0]
        if q >> 32 == 0 and (q & 0xF0000000) == ytd.PHYSICAL_TAG and (q & _M) < physical_size and (q & _M) % align == 0:
            refs.add(q & _M)
    return refs


def parse(virtual, physical=None, physical_size=None):
    """
    (dictionary, None) when the embedded textures can be shrunk, or (dictionary_or_None, reason)
    when they cannot. Pass `physical` to load pixel data, or only `physical_size` for a plan.
    """
    base = texture_dictionary_offset(virtual)
    if base is None:
        return None, "no embedded textures"
    d = ytd.parse(virtual, physical, base=base)
    if not d.textures:
        return d, "no embedded textures"
    size = len(physical) if physical is not None else physical_size
    starts = {t.data_offset for t in d.textures}
    other = physical_refs(virtual, size) - starts
    if other:
        return d, f"model data shares the texture memory ({len(other)} other pointer(s)): not supported yet"
    return d, None
