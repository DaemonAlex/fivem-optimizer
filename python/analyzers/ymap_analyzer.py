"""
YMAP (Map Placement) Analyzer

Analyzes .ymap files for placement density, streaming extents,
and references to assets.
"""
import struct
import os

RSC7_MAGIC = 0x37435352

MAX_ENTITIES_PER_YMAP = 2000
WARN_ENTITIES_PER_YMAP = 500
MAX_STREAMING_EXTENT = 1000.0
WARN_STREAMING_EXTENT = 400.0


class YmapAnalyzer:
    def __init__(self, settings):
        self.max_bounds = settings.get("maxBoundsDimension", 500)

    def analyze(self, filepath, rel_path, file_size):
        """Returns (issues, metadata) tuple. Reads file from disk and delegates to analyze_buffer."""
        try:
            with open(filepath, 'rb') as f:
                data = f.read(min(file_size, 256 * 1024))
        except (OSError, PermissionError):
            data = b''
        return self.analyze_buffer(data, filepath, rel_path, file_size)

    def analyze_buffer(self, data, filepath, rel_path, file_size):
        """Returns (issues, metadata) tuple. Operates on pre-read bytes, no file I/O."""
        issues = []
        metadata = {}
        size_mb = file_size / (1024 * 1024)

        if size_mb > 4:
            issues.append({
                "file": rel_path,
                "file_type": ".ymap",
                "severity": "critical",
                "category": "file_size",
                "message": f"Very large map file ({size_mb:.1f} MB)",
                "recommendation": "Split this ymap into smaller regions. Large ymaps increase load times and memory usage.",
                "details": {"size_mb": round(size_mb, 2)},
            })

        info = self._parse_ymap_from_buffer(data, file_size)
        metadata["ymap_info"] = info

        if info:
            entity_count = info.get("estimated_entities", 0)
            extent = info.get("streaming_extent", 0)

            if entity_count > MAX_ENTITIES_PER_YMAP:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ymap",
                    "severity": "critical",
                    "category": "streaming_bounds",
                    "message": f"Too many entities (~{entity_count:,})",
                    "recommendation": f"Split into smaller ymaps. Over {MAX_ENTITIES_PER_YMAP} entities per ymap causes streaming bottlenecks.",
                    "details": {"estimated_entities": entity_count, "limit": MAX_ENTITIES_PER_YMAP},
                })
            elif entity_count > WARN_ENTITIES_PER_YMAP:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ymap",
                    "severity": "warning",
                    "category": "streaming_bounds",
                    "message": f"High entity count (~{entity_count:,})",
                    "recommendation": f"Consider splitting. Target under {WARN_ENTITIES_PER_YMAP} entities per ymap for best performance.",
                    "details": {"estimated_entities": entity_count},
                })

            if extent > MAX_STREAMING_EXTENT:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ymap",
                    "severity": "critical",
                    "category": "streaming_bounds",
                    "message": f"Excessive streaming extent ({extent:.0f} units)",
                    "recommendation": "Large streaming extents force the game to load this ymap from very far away. Split into smaller geographic regions.",
                    "details": {"streaming_extent": round(extent, 1)},
                })
            elif extent > WARN_STREAMING_EXTENT:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ymap",
                    "severity": "warning",
                    "category": "streaming_bounds",
                    "message": f"Large streaming extent ({extent:.0f} units)",
                    "recommendation": "Consider splitting into smaller regions for more efficient streaming.",
                    "details": {"streaming_extent": round(extent, 1)},
                })

        return issues, metadata

    def _parse_ymap(self, filepath):
        """Parse ymap binary. Reads from disk, delegates to buffer parser."""
        try:
            file_size = os.path.getsize(filepath)
            if file_size < 32:
                return {}
            with open(filepath, 'rb') as f:
                data = f.read(min(file_size, 256 * 1024))
            return self._parse_ymap_from_buffer(data, file_size)
        except (OSError, PermissionError):
            return {}

    def _parse_ymap_from_buffer(self, data, file_size):
        """Parse ymap binary buffer for entity counts and extents. No file I/O."""
        info = {}
        try:
            if len(data) < 32:
                return info

            # Estimate entity count from file size
            # Each entity placement is roughly 128-192 bytes
            info["estimated_entities"] = max(1, int(file_size / 160))

            # Look for streaming extents (AABB bounding box)
            magic = struct.unpack_from('<I', data, 0)[0]
            scan_start = 16 if magic == RSC7_MAGIC else 0

            best_extent = 0
            pos = scan_start
            scan_end = min(len(data) - 24, 1024)
            while pos < scan_end:
                try:
                    vals = struct.unpack_from('<6f', data, pos)
                    if all(-15000 < v < 15000 for v in vals):
                        min_x, min_y, min_z = vals[0], vals[1], vals[2]
                        max_x, max_y, max_z = vals[3], vals[4], vals[5]
                        if (max_x > min_x and max_y > min_y and max_z > min_z):
                            dx = max_x - min_x
                            dy = max_y - min_y
                            dz = max_z - min_z
                            extent = max(dx, dy, dz)
                            if extent > best_extent and extent < 15000:
                                best_extent = extent
                except struct.error:
                    break
                pos += 4

            if best_extent > 0:
                info["streaming_extent"] = best_extent

        except Exception:
            pass

        return info
