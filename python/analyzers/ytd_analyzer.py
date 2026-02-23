"""
YTD (Texture Dictionary) Analyzer

Analyzes .ytd files for FiveM optimization issues.
Parses binary headers to extract texture metadata with robust validation.
Detects texture types (script_rt, emissive, diffuse, normal) from naming patterns.
Detects alpha channel usage for compression format recommendations.
"""
import struct
import os
from .model_parser import extract_texture_names as _extract_names_shared

# RAGE RSC7 magic number
RSC7_MAGIC = 0x37435352  # "RSC7" little-endian

# DXGI format IDs used in GTA V textures
TEXTURE_FORMATS = {
    0: "Unknown",
    28: "R8G8B8A8_UNORM",
    71: "BC1/DXT1",
    74: "BC2/DXT3",
    77: "BC3/DXT5",
    80: "BC4/ATI1",
    83: "BC5/ATI2",
    87: "B8G8R8A8_UNORM",
    98: "BC7",
}

# Formats that use block compression (lower VRAM)
COMPRESSED_FORMATS = {71, 74, 77, 80, 83, 98}

# Formats with alpha channel support
ALPHA_FORMATS = {28, 74, 77, 87, 98}  # DXT3, DXT5, BC7, RGBA uncompressed

# Formats WITHOUT alpha (opaque only)
OPAQUE_FORMATS = {71, 80, 83}  # DXT1, BC4, BC5

# VRAM bytes-per-pixel for each format
FORMAT_BPP = {
    71: 0.5,   # BC1/DXT1: 4 bits per pixel
    74: 1.0,   # BC2/DXT3: 8 bits per pixel
    77: 1.0,   # BC3/DXT5: 8 bits per pixel
    80: 0.5,   # BC4/ATI1: 4 bits per pixel
    83: 1.0,   # BC5/ATI2: 8 bits per pixel
    98: 1.0,   # BC7: 8 bits per pixel
    28: 4.0,   # R8G8B8A8: 32 bits per pixel
    87: 4.0,   # B8G8R8A8: 32 bits per pixel
}

# Texture type detection patterns
# script_rt textures MUST remain uncompressed - FiveM warns/crashes if compressed
SCRIPT_RT_PREFIXES = ('scr', 'script_rt')
# Emissive/light textures should not be resized - causes visual artifacts
EMISSIVE_PATTERNS = ('emis', 'emissive', 'light', 'glow', 'neon', '_em')
# Texture type suffixes for classification
DIFFUSE_SUFFIXES = ('_d', '_diff', '_diffuse', '_albedo', '_base', '_color')
NORMAL_SUFFIXES = ('_n', '_normal', '_nrm', '_bump')
SPECULAR_SUFFIXES = ('_s', '_spec', '_specular', '_rough', '_roughness', '_gloss')


def classify_texture_name(name):
    """Classify a texture name by type. Returns (type_str, safe_to_resize)."""
    name_lower = name.lower()

    # script_rt textures - NEVER resize or compress
    for prefix in SCRIPT_RT_PREFIXES:
        if name_lower.startswith(prefix):
            return "script_rt", False

    # Emissive/light textures - risky to resize
    for pat in EMISSIVE_PATTERNS:
        if pat in name_lower:
            return "emissive", False

    # Classify by suffix
    for suffix in DIFFUSE_SUFFIXES:
        if name_lower.endswith(suffix):
            return "diffuse", True

    for suffix in NORMAL_SUFFIXES:
        if name_lower.endswith(suffix):
            return "normal", True

    for suffix in SPECULAR_SUFFIXES:
        if name_lower.endswith(suffix):
            return "specular", True

    # Default: assume diffuse-like, safe to resize
    return "unknown", True


class YtdAnalyzer:
    def __init__(self, settings):
        self.max_res = settings.get("maxTextureResolution", 4096)
        self.rec_res = settings.get("recommendedMaxResolution", 2048)
        self.max_size_mb = settings.get("maxYtdSizeMB", 14)

    def analyze(self, filepath, rel_path, file_size):
        """Returns (issues, metadata) tuple. Reads file from disk and delegates to analyze_buffer."""
        try:
            with open(filepath, 'rb') as f:
                data = f.read(min(file_size, 64 * 1024))
        except (OSError, PermissionError):
            data = b''
        return self.analyze_buffer(data, filepath, rel_path, file_size)

    def analyze_buffer(self, data, filepath, rel_path, file_size):
        """Returns (issues, metadata) tuple. Operates on pre-read bytes, no file I/O."""
        issues = []
        metadata = {"vram_estimate": 0, "textures": []}
        size_mb = file_size / (1024 * 1024)

        # FiveM 16MB hard streaming limit
        if file_size > 16 * 1024 * 1024:
            issues.append({
                "file": rel_path,
                "file_type": ".ytd",
                "severity": "critical",
                "category": "file_size",
                "message": f"EXCEEDS FiveM 16MB streaming limit ({size_mb:.1f} MB)",
                "recommendation": "FiveM cannot stream files above 16MB. This file WILL fail to load. Split into smaller dictionaries or reduce texture resolutions immediately.",
                "details": {"size_mb": round(size_mb, 2), "hard_limit": 16},
                "fixable": True,
                "fix_type": "resize_textures",
            })
        elif size_mb > self.max_size_mb:
            issues.append({
                "file": rel_path,
                "file_type": ".ytd",
                "severity": "critical",
                "category": "file_size",
                "message": f"Texture dictionary is very large ({size_mb:.1f} MB)",
                "recommendation": f"Split this YTD or reduce texture resolutions. Target under {self.max_size_mb} MB.",
                "details": {"size_mb": round(size_mb, 2)},
                "fixable": True,
                "fix_type": "resize_textures",
            })

        # Extract texture names from binary data for type detection
        texture_names = self._extract_texture_names(data)

        textures = self._parse_textures_from_buffer(data, file_size)
        if textures:
            for i, tex in enumerate(textures):
                width = tex.get("width", 0)
                height = tex.get("height", 0)
                fmt = tex.get("format", 0)
                mipmaps = tex.get("mipmaps", 0)
                has_alpha = fmt in ALPHA_FORMATS

                # Try to classify this texture by name
                tex_name = texture_names[i] if i < len(texture_names) else ""
                tex_type, safe_to_resize = classify_texture_name(tex_name) if tex_name else ("unknown", True)
                tex["type"] = tex_type
                tex["safe_to_resize"] = safe_to_resize
                tex["has_alpha"] = has_alpha
                if tex_name:
                    tex["name"] = tex_name

                max_dim = max(width, height)

                # script_rt detection
                if tex_type == "script_rt":
                    if fmt in COMPRESSED_FORMATS:
                        issues.append({
                            "file": rel_path,
                            "file_type": ".ytd",
                            "severity": "critical",
                            "category": "texture_quality",
                            "message": f"script_rt texture is compressed ({TEXTURE_FORMATS.get(fmt, f'ID:{fmt}')})",
                            "recommendation": "script_rt textures MUST be uncompressed (R8G8B8A8). FiveM will display warnings and the texture will render incorrectly.",
                            "details": {"texture_name": tex_name, "format": TEXTURE_FORMATS.get(fmt, f"ID:{fmt}")},
                        })

                # Size checks
                if max_dim > self.max_res:
                    issues.append({
                        "file": rel_path,
                        "file_type": ".ytd",
                        "severity": "critical",
                        "category": "texture_quality",
                        "message": f"Oversized texture: {width}x{height}" + (f" ({tex_name})" if tex_name else ""),
                        "recommendation": f"Reduce to {self.rec_res}x{self.rec_res} or smaller. Textures above {self.max_res}px cause significant streaming overhead.",
                        "details": {
                            "width": width, "height": height,
                            "format": TEXTURE_FORMATS.get(fmt, f"ID:{fmt}"),
                            "type": tex_type,
                        },
                        "fixable": safe_to_resize,
                        "fix_type": "resize_texture",
                    })
                elif max_dim > self.rec_res:
                    issues.append({
                        "file": rel_path,
                        "file_type": ".ytd",
                        "severity": "warning",
                        "category": "texture_quality",
                        "message": f"Large texture: {width}x{height}" + (f" ({tex_name})" if tex_name else ""),
                        "recommendation": f"Consider reducing to {self.rec_res}x{self.rec_res} for better streaming performance.",
                        "details": {
                            "width": width, "height": height,
                            "format": TEXTURE_FORMATS.get(fmt, f"ID:{fmt}"),
                            "type": tex_type,
                        },
                        "fixable": safe_to_resize,
                        "fix_type": "resize_texture",
                    })

                # Non-power-of-two
                if width > 0 and height > 0:
                    if (width & (width - 1)) != 0 or (height & (height - 1)) != 0:
                        issues.append({
                            "file": rel_path,
                            "file_type": ".ytd",
                            "severity": "warning",
                            "category": "texture_quality",
                            "message": f"Non-power-of-two texture: {width}x{height}",
                            "recommendation": "Use power-of-two dimensions (256, 512, 1024, 2048) for optimal GPU performance and compression.",
                            "details": {"width": width, "height": height},
                        })

                # Uncompressed format (except script_rt which requires it)
                if fmt not in COMPRESSED_FORMATS and fmt != 0 and tex_type != "script_rt":
                    rec_fmt = "DXT5/BC3" if has_alpha else "DXT1/BC1"
                    issues.append({
                        "file": rel_path,
                        "file_type": ".ytd",
                        "severity": "warning",
                        "category": "texture_quality",
                        "message": f"Uncompressed texture format: {TEXTURE_FORMATS.get(fmt, f'ID:{fmt}')}",
                        "recommendation": f"Use {rec_fmt} compression. Compressed formats reduce VRAM usage by 4-8x.",
                        "details": {
                            "format": TEXTURE_FORMATS.get(fmt, f"ID:{fmt}"),
                            "has_alpha": has_alpha,
                            "recommended_format": rec_fmt,
                        },
                        "fixable": True,
                        "fix_type": "recompress_texture",
                    })

                # Alpha format mismatch - using DXT5 when DXT1 would work (no alpha needed)
                if fmt in ALPHA_FORMATS and fmt in COMPRESSED_FORMATS and not has_alpha:
                    # This would need deeper inspection; skip for now as we can't be 100% sure
                    pass

                # Missing mipmaps
                if mipmaps <= 1 and max_dim > 64:
                    issues.append({
                        "file": rel_path,
                        "file_type": ".ytd",
                        "severity": "info",
                        "category": "texture_quality",
                        "message": "Texture may be missing mipmaps",
                        "recommendation": "Generate mipmaps for textures larger than 64px. Mipmaps improve rendering at distance and reduce GPU aliasing.",
                        "details": {"mipmap_levels": mipmaps, "width": width, "height": height},
                    })

            # VRAM estimate
            metadata["vram_estimate"] = self._estimate_vram(textures)
            metadata["textures"] = textures

        return issues, metadata

    def _extract_texture_names(self, data):
        """Extract texture name strings from binary data using shared parser."""
        return _extract_names_shared(data)

    def _estimate_vram(self, textures):
        """Estimate VRAM usage in bytes using validated format BPP values."""
        total = 0
        for tex in textures:
            w = tex.get("width", 0)
            h = tex.get("height", 0)
            fmt = tex.get("format", 0)
            mips = max(tex.get("mipmaps", 1), 1)
            if w <= 0 or h <= 0:
                continue
            bpp = FORMAT_BPP.get(fmt, 4.0)  # Default to uncompressed if unknown
            base = w * h * bpp
            # Mipmaps add ~33% to VRAM (geometric series sum for halving dimensions)
            total += int(base * (1.333 if mips > 1 else 1.0))
        return total

    def _parse_textures(self, filepath):
        """Extract texture metadata from YTD binary. Reads from disk, delegates to buffer parser."""
        try:
            file_size = os.path.getsize(filepath)
            if file_size < 16:
                return []
            with open(filepath, 'rb') as f:
                data = f.read(min(file_size, 64 * 1024))
            return self._parse_textures_from_buffer(data, file_size)
        except (OSError, PermissionError):
            return []

    def _parse_textures_from_buffer(self, data, file_size):
        """Extract texture metadata from YTD binary buffer with robust validation. No file I/O."""
        textures = []
        try:
            if len(data) < 16:
                return textures

            # Validate RSC7 magic if present
            magic = struct.unpack_from('<I', data, 0)[0]
            # RSC7 or raw data - both valid, just different offsets
            scan_start = 12 if magic == RSC7_MAGIC else 0

            pos = scan_start
            seen_dims = set()
            while pos < len(data) - 8:
                if len(textures) >= 32:
                    break
                try:
                    w = struct.unpack_from('<H', data, pos)[0]
                    h = struct.unpack_from('<H', data, pos + 2)[0]

                    if (self._is_valid_dimension(w) and
                            self._is_valid_dimension(h) and
                            w >= 4 and h >= 4):

                        dim_key = (w, h, pos // 64)  # Dedupe by region
                        if dim_key not in seen_dims:
                            seen_dims.add(dim_key)

                            fmt = 0
                            mips = 1
                            if pos >= 4:
                                potential_fmt = struct.unpack_from('<B', data, pos - 4)[0]
                                if potential_fmt in TEXTURE_FORMATS:
                                    fmt = potential_fmt

                            if pos + 4 < len(data):
                                potential_mips = struct.unpack_from('<B', data, pos + 4)[0]
                                if 1 <= potential_mips <= 14:
                                    mips = potential_mips

                            textures.append({
                                "width": w,
                                "height": h,
                                "format": fmt,
                                "mipmaps": mips,
                            })
                            pos += 16
                            continue
                except struct.error:
                    pass
                pos += 2

        except Exception:
            pass

        return textures

    def _is_valid_dimension(self, val):
        if val < 4 or val > 8192:
            return False
        return (val & (val - 1)) == 0
