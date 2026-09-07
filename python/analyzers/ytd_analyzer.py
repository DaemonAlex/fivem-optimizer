"""
YTD (texture dictionary) analyzer.

Reads the real texture records (rsc7.py + ytd.py): names, dimensions, formats, mip counts, and
the memory the game allocates for the file. Only the virtual segment is inflated, so a scan stays
fast. Encrypted (FXAP) files are reported as such rather than guessed at.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rsc7
import ytd

MIB = 1024 * 1024

SCRIPT_RT_PREFIXES = ("script_rt", "scr_")
EMISSIVE_PATTERNS = ("emis", "emissive", "glow", "neon")
DIFFUSE_SUFFIXES = ("_d", "_diff", "_diffuse", "_albedo", "_base", "_color", "_difuse")
NORMAL_SUFFIXES = ("_n", "_normal", "_nrm", "_bump", "_nm")
SPECULAR_SUFFIXES = ("_s", "_spec", "_specular", "_rough", "_roughness", "_gloss")
UNCOMPRESSED = {"A8R8G8B8", "X8R8G8B8", "A8B8G8R8", "A16B16G16R16", "A16B16G16R16F"}


def classify_texture_name(name):
    """-> (type, safe_to_resize)."""
    n = name.lower()
    if n.startswith(SCRIPT_RT_PREFIXES):
        return "script_rt", False
    if any(p in n for p in EMISSIVE_PATTERNS) or n.endswith("_em"):
        return "emissive", False
    if n.endswith(DIFFUSE_SUFFIXES):
        return "diffuse", True
    if n.endswith(NORMAL_SUFFIXES):
        return "normal", True
    if n.endswith(SPECULAR_SUFFIXES):
        return "specular", True
    return "unknown", True


class YtdAnalyzer:
    def __init__(self, settings):
        self.max_res = settings.get("maxTextureResolution", 4096)
        self.rec_res = settings.get("recommendedMaxResolution", 2048)
        self.critical_mib = settings.get("maxYtdMemoryMiB", 32)
        self.warn_mib = settings.get("warnYtdMemoryMiB", 16)

    def analyze(self, filepath, rel_path, file_size):
        return self.analyze_buffer(None, filepath, rel_path, file_size)

    def analyze_buffer(self, data, filepath, rel_path, file_size):
        """The buffer argument is ignored: the file is inflated from disk (only its record segment)."""
        issues = []
        metadata = {"vram_estimate": 0, "memory_mib": 0.0, "textures": [], "texture_count": 0, "max_dimension": 0}

        def issue(severity, category, message, recommendation, details=None, fixable=False, fix_type=None):
            entry = {"file": rel_path, "file_type": ".ytd", "severity": severity, "category": category,
                     "message": message, "recommendation": recommendation, "details": details or {}}
            if fixable:
                entry["fixable"] = True
                entry["fix_type"] = fix_type
            issues.append(entry)

        try:
            r = rsc7.read_virtual(filepath)
            d = ytd.parse(r.virtual)
        except rsc7.NotRsc7 as e:
            if "FXAP" in str(e):
                issue("info", "encrypted", "Encrypted (FXAP escrow) texture dictionary: cannot be inspected",
                      "Memory and texture sizes are unknown for escrowed files. Check FXServer's boot log for its 'uses N MiB' warning.")
            else:
                issue("info", "unreadable", f"Not a readable RSC7 file ({e})", "The file may be corrupt or not a GTA V texture dictionary.")
            return issues, metadata
        except Exception as e:
            issue("info", "unreadable", f"Could not parse the texture dictionary: {type(e).__name__}",
                  "The file may be corrupt or use an unexpected layout.", {"error": str(e)})
            return issues, metadata

        memory = r.physical_size
        metadata["vram_estimate"] = memory
        metadata["memory_mib"] = round(memory / MIB, 1)
        metadata["texture_count"] = len(d.textures)
        for t in d.textures:
            tex_type, safe = classify_texture_name(t.name)
            metadata["textures"].append({"name": t.name, "width": t.width, "height": t.height, "format": t.format,
                                         "mipmaps": t.levels, "type": tex_type, "safe_to_resize": safe,
                                         "memory_mib": round(t.chain_size() / MIB, 2)})
            longest = max(t.width, t.height)
            metadata["max_dimension"] = max(metadata["max_dimension"], longest)
            if longest > self.max_res:
                issue("critical", "texture_quality", f"Oversized texture: {t.width}x{t.height} ({t.name})",
                      f"Reduce to {self.rec_res}px or smaller.", {"name": t.name, "width": t.width, "height": t.height,
                      "format": t.format, "type": tex_type}, fixable=safe, fix_type="resize_texture")
            elif longest > self.rec_res:
                issue("warning", "texture_quality", f"Large texture: {t.width}x{t.height} ({t.name})",
                      f"Consider reducing to {self.rec_res}px.", {"name": t.name, "width": t.width, "height": t.height,
                      "format": t.format, "type": tex_type}, fixable=safe, fix_type="resize_texture")
            if t.levels <= 1 and longest > 64:
                issue("info", "texture_quality", f"No mipmaps: {t.name} {t.width}x{t.height}",
                      "Without a mip chain the full texture is sampled at every distance; the optimizer can only shrink it with a converter.",
                      {"name": t.name, "width": t.width, "height": t.height, "mipmap_levels": t.levels})
            if t.format in UNCOMPRESSED and tex_type != "script_rt":
                issue("warning", "texture_quality", f"Uncompressed texture: {t.name} ({t.format})",
                      "DXT1 (no alpha) or DXT5 (alpha) uses 4-8x less memory.", {"name": t.name, "format": t.format},
                      fixable=True, fix_type="recompress_texture")
            if longest > 0 and ((t.width & (t.width - 1)) or (t.height & (t.height - 1))) and longest > 64:
                issue("info", "texture_quality", f"Non-power-of-two texture: {t.name} {t.width}x{t.height}",
                      "Power-of-two sizes pack and mip more efficiently.", {"name": t.name})

        mib = metadata["memory_mib"]
        if mib > self.critical_mib:
            issue("critical", "memory", f"Uses {mib} MiB of memory in game (target {self.critical_mib} MiB or less)",
                  "This is the number FXServer warns about at boot. Shrink the largest textures with the Textures tab.",
                  {"memory_mib": mib, "target_mib": self.critical_mib}, fixable=True, fix_type="resize_textures")
        elif mib > self.warn_mib:
            issue("warning", "memory", f"Uses {mib} MiB of memory in game",
                  "Consider shrinking the largest textures.", {"memory_mib": mib}, fixable=True, fix_type="resize_textures")
        return issues, metadata
