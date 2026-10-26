"""
Textures embedded in a drawable dictionary (.ydd): clothing, props and map objects.

A .ydd is an RSC7 resource (version 165) whose virtual segment starts with a pgDictionary of
drawables. Each drawable can carry its own texture dictionary, the same pgDictionary<grcTexture>
layout a .ytd holds. Clothing packs ship their diffuse, normal and specular maps that way, and the
sizes get out of hand (8192 x 4096 for a set of teeth).

    Dictionary  +0x30  drawable array pointer   (u64, virtual)   +0x38 count (u16)
    Drawable    +0x10  shader group pointer     (u64, virtual)
    ShaderGroup +0x08  texture dictionary       (u64, virtual, 0 when the drawable has no embedded textures)

The physical segment can also hold model data (vertex and index buffers) next to the pixels. As
with a .yft, a .ydd is only rewritten when every physical pointer in its virtual segment is a
texture data pointer from one of its dictionaries: the physical segment is then pixel data and
nothing else, and ytd.serialize rebuilds it exactly as it does for a .ytd. Anything else is
reported and left alone. The textures of all drawables are handled as one dictionary: their
records live in the same virtual segment and their pixels share the same physical segment.
"""
import struct

import yft
import ytd

VERSION_YDD = 165
_M = ytd.OFFSET_MASK


def _u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0] if 0 <= off <= len(buf) - 2 else 0


def _u64(buf, off):
    return struct.unpack_from("<Q", buf, off)[0] if 0 <= off <= len(buf) - 8 else 0


def texture_dictionary_offsets(virtual):
    """Virtual offsets of every drawable's embedded texture dictionary, in drawable order."""
    array = yft._virtual(_u64(virtual, 0x30))
    count = _u16(virtual, 0x38)
    if array is None or count == 0:
        return []
    found = []
    for i in range(count):
        drawable = yft._virtual(_u64(virtual, array + 8 * i))
        if drawable is None:
            continue
        shader_group = yft._virtual(_u64(virtual, drawable + 0x10))
        if shader_group is None:
            continue
        txd = yft._virtual(_u64(virtual, shader_group + 0x08))
        if txd is not None and txd not in found:
            found.append(txd)
    return found


def parse(virtual, physical=None, physical_size=None):
    """
    (dictionary, None) when the embedded textures can be shrunk, or (dictionary_or_None, reason)
    when they cannot. Pass `physical` to load pixel data, or only `physical_size` for a plan.
    """
    bases = texture_dictionary_offsets(virtual)
    if not bases:
        return None, "no embedded textures"
    v = bytearray(virtual)
    textures = []
    for base in bases:
        part = ytd.parse(v, None, base=base)
        textures += part.textures
    d = ytd.Dictionary(v, textures)
    if not textures:
        return d, "no embedded textures"
    if len({t.record_offset for t in textures}) != len(textures):
        return d, "drawables share a texture record: not supported yet"
    size = len(physical) if physical is not None else physical_size
    starts = {t.data_offset for t in textures}
    other = yft.physical_refs(virtual, size) - starts
    if other:
        return d, f"model data shares the texture memory ({len(other)} other pointer(s)): not supported yet"
    if physical is not None:
        # slice pixel data across all dictionaries: known formats by exact chain size, unknown ones up to the next texture
        order = sorted(textures, key=lambda t: t.data_offset)
        for i, t in enumerate(order):
            end = order[i + 1].data_offset if i + 1 < len(order) else len(physical)
            size = ytd.chain_size(t.width, t.height, t.format_code, t.levels) if t.known_format else end - t.data_offset
            if t.data_offset + size > len(physical):
                raise ValueError(f"texture {t.name}: data runs past the physical segment")
            t.data = bytes(physical[t.data_offset:t.data_offset + size])
    return d, None
