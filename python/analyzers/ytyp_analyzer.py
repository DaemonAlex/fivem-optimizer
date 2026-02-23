"""
YTYP (Archetype Definitions) Analyzer

Analyzes .ytyp files for archetype count, LOD definitions,
and potential issues with type definitions.
"""
import struct
import os

RSC7_MAGIC = 0x37435352

MAX_ARCHETYPES_PER_YTYP = 500
WARN_ARCHETYPES_PER_YTYP = 200


class YtypAnalyzer:
    def __init__(self, settings):
        self.settings = settings

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
        metadata = {}
        size_mb = file_size / (1024 * 1024)

        if size_mb > 2:
            issues.append({
                "file": rel_path,
                "file_type": ".ytyp",
                "severity": "warning",
                "category": "file_size",
                "message": f"Large archetype file ({size_mb:.1f} MB)",
                "recommendation": "Consider splitting archetype definitions into smaller groups by category.",
                "details": {"size_mb": round(size_mb, 2)},
            })

        info = self._parse_ytyp_from_buffer(data, file_size)
        metadata["ytyp_info"] = info

        if info:
            archetype_count = info.get("estimated_archetypes", 0)

            if archetype_count > MAX_ARCHETYPES_PER_YTYP:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ytyp",
                    "severity": "warning",
                    "category": "streaming_bounds",
                    "message": f"High archetype count (~{archetype_count:,})",
                    "recommendation": f"Consider splitting. Large ytyp files with over {MAX_ARCHETYPES_PER_YTYP} archetypes are harder to manage and slower to parse.",
                    "details": {"estimated_archetypes": archetype_count},
                })
            elif archetype_count > WARN_ARCHETYPES_PER_YTYP:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ytyp",
                    "severity": "info",
                    "category": "streaming_bounds",
                    "message": f"Many archetypes (~{archetype_count:,})",
                    "recommendation": "Consider organizing into multiple smaller ytyp files by category.",
                    "details": {"estimated_archetypes": archetype_count},
                })

        # Check for zero-size file
        if file_size == 0:
            issues.append({
                "file": rel_path,
                "file_type": ".ytyp",
                "severity": "warning",
                "category": "resource_config",
                "message": "Empty archetype file",
                "recommendation": "This ytyp file is empty and can be removed.",
            })

        return issues, metadata

    def _parse_ytyp(self, filepath):
        """Parse ytyp binary. Reads from disk, delegates to buffer parser."""
        try:
            file_size = os.path.getsize(filepath)
            if file_size < 16:
                return {}
            with open(filepath, 'rb') as f:
                data = f.read(min(file_size, 64 * 1024))
            return self._parse_ytyp_from_buffer(data, file_size)
        except (OSError, PermissionError):
            return {}

    def _parse_ytyp_from_buffer(self, data, file_size):
        """Parse ytyp binary buffer for archetype info. No file I/O."""
        info = {}
        try:
            if len(data) < 16:
                return info

            # Estimate archetype count from file size
            # Each archetype definition is roughly 128-256 bytes
            info["estimated_archetypes"] = max(1, int(file_size / 192))

            # Try to detect referenced model names in binary data
            text_data = data.decode('utf-8', errors='ignore').lower()
            ref_names = set()
            # Look for common asset name patterns
            for token in text_data.split('\x00'):
                token = token.strip()
                if 3 <= len(token) <= 64 and token.isascii() and not token.startswith(('-', '.')):
                    if any(c.isalpha() for c in token) and '_' in token:
                        ref_names.add(token)

            if ref_names:
                info["referenced_assets"] = list(ref_names)[:50]  # Cap at 50

        except Exception:
            pass

        return info
