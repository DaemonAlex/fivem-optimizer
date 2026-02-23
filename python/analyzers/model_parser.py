"""
Shared binary parsing utilities for RAGE model files (YFT/YDR).

Extracts vertex/index counts, bone counts, and LOD levels from
RSC7 binary buffers using heuristic scanning.
"""
import struct

RSC7_MAGIC = 0x37435352


def parse_model_geometry(data, vertex_range=(100, 200000), max_index_entries=8):
    """
    Scan binary data for vertex/index count pairs and bone references.

    Args:
        data: Raw bytes from the model file.
        vertex_range: (min, max) tuple for plausible vertex counts.
        max_index_entries: Max index count entries to sum for poly estimate.

    Returns:
        dict with estimated_polys, estimated_bones, estimated_lods.
    """
    info = {}
    if len(data) < 32:
        return info

    magic = struct.unpack_from('<I', data, 0)[0]
    scan_start = 16 if magic == RSC7_MAGIC else 0

    min_verts, max_verts = vertex_range
    vertex_counts = []
    index_counts = []
    bone_refs = 0

    pos = scan_start
    data_len = len(data) - 8
    while pos < data_len:
        try:
            val = struct.unpack_from('<I', data, pos)[0]

            if min_verts <= val <= max_verts:
                next_val = struct.unpack_from('<I', data, pos + 4)[0]
                if val < next_val <= val * 6 and next_val % 3 == 0:
                    vertex_counts.append(val)
                    index_counts.append(next_val)
                    pos += 8
                    continue

            if 1 <= val <= 256 and val > bone_refs:
                bone_refs = val

        except struct.error:
            break
        pos += 4

    if index_counts:
        info["estimated_polys"] = sum(c // 3 for c in index_counts[:max_index_entries])
    if bone_refs > 0 and bone_refs <= 256:
        info["estimated_bones"] = bone_refs
    info["estimated_lods"] = min(len(vertex_counts), 5)

    return info


def extract_texture_names(data):
    """
    Extract texture/asset name strings from binary data using null-terminated string scanning.
    Shared between YTD analyzer and optimize_textures.py.
    """
    names = []
    try:
        text = data.decode('utf-8', errors='ignore')
        for token in text.split('\x00'):
            token = token.strip()
            if 3 <= len(token) <= 64 and token.isascii():
                if any(c.isalpha() for c in token) and not token.startswith(('-', '.', '/')):
                    if '_' in token or token.startswith('scr'):
                        names.append(token)
    except Exception:
        pass
    return names
