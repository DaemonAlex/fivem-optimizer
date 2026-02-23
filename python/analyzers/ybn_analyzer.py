"""
YBN (Collision Bounds) Analyzer

Analyzes .ybn files with robust binary parsing.
"""
import struct
import os

RSC7_MAGIC = 0x37435352


class YbnAnalyzer:
    def __init__(self, settings):
        self.max_polys = settings.get("maxCollisionPolys", 10000)
        self.rec_polys = 5000
        self.max_size_mb = settings.get("maxYbnSizeMB", 4)
        self.max_bounds = settings.get("maxBoundsDimension", 500)
        self.large_bounds = 200

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

        if size_mb > self.max_size_mb:
            issues.append({
                "file": rel_path,
                "file_type": ".ybn",
                "severity": "critical",
                "category": "file_size",
                "message": f"Collision file is very large ({size_mb:.1f} MB)",
                "recommendation": f"Simplify collision geometry. Target under {self.max_size_mb} MB. Use simple box/capsule colliders where possible.",
                "details": {"size_mb": round(size_mb, 2)},
            })

        bounds_info = self._parse_bounds_info_from_buffer(data, file_size)
        metadata["bounds_info"] = bounds_info

        if bounds_info:
            poly_count = bounds_info.get("estimated_polys", 0)
            bbox_size = bounds_info.get("bbox_max_dimension", 0)

            if poly_count > self.max_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ybn",
                    "severity": "critical",
                    "category": "polygon_count",
                    "message": f"Very high collision polygon count (~{poly_count:,})",
                    "recommendation": f"Simplify to under {self.rec_polys:,} polygons. Complex collision meshes severely impact physics performance.",
                    "details": {"estimated_polygons": poly_count},
                })
            elif poly_count > self.rec_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ybn",
                    "severity": "warning",
                    "category": "polygon_count",
                    "message": f"High collision polygon count (~{poly_count:,})",
                    "recommendation": f"Consider simplifying to under {self.rec_polys:,} polygons.",
                    "details": {"estimated_polygons": poly_count},
                })

            if bbox_size > self.max_bounds:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ybn",
                    "severity": "critical",
                    "category": "streaming_bounds",
                    "message": f"Excessive bounding box size ({bbox_size:.0f} units)",
                    "recommendation": f"Streaming bounds of {bbox_size:.0f} units forces loading from very far away. Split into smaller sections.",
                    "details": {"max_dimension": round(bbox_size, 1), "limit": self.max_bounds},
                })
            elif bbox_size > self.large_bounds:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ybn",
                    "severity": "warning",
                    "category": "streaming_bounds",
                    "message": f"Large bounding box ({bbox_size:.0f} units)",
                    "recommendation": "Consider splitting into smaller collision sections for more efficient streaming.",
                    "details": {"max_dimension": round(bbox_size, 1)},
                })
        else:
            estimated = int(file_size / 12)
            if estimated > self.max_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ybn",
                    "severity": "warning",
                    "category": "polygon_count",
                    "message": f"File size suggests high collision complexity (~{estimated:,} estimated polygons)",
                    "recommendation": "Verify and simplify collision geometry.",
                    "details": {"estimated_polygons": estimated, "method": "file_size_heuristic"},
                })

        return issues, metadata

    def _parse_bounds_info(self, filepath):
        """Extract collision metadata. Reads from disk, delegates to buffer parser."""
        try:
            file_size = os.path.getsize(filepath)
            if file_size < 32:
                return {}
            with open(filepath, 'rb') as f:
                data = f.read(min(file_size, 64 * 1024))
            return self._parse_bounds_info_from_buffer(data, file_size)
        except (OSError, PermissionError):
            return {}

    def _parse_bounds_info_from_buffer(self, data, file_size):
        """Extract collision metadata from YBN binary buffer with robust validation. No file I/O."""
        info = {}
        try:
            if len(data) < 32:
                return info

            magic = struct.unpack_from('<I', data, 0)[0]
            scan_start = 16 if magic == RSC7_MAGIC else 0

            best_bbox = 0
            pos = scan_start
            scan_end = min(len(data) - 24, 512)
            while pos < scan_end:
                try:
                    vals = struct.unpack_from('<6f', data, pos)
                    if all(-10000 < v < 10000 for v in vals):
                        min_x, min_y, min_z = vals[0], vals[1], vals[2]
                        max_x, max_y, max_z = vals[3], vals[4], vals[5]
                        if max_x > min_x and max_y > min_y and max_z > min_z:
                            dx = max_x - min_x
                            dy = max_y - min_y
                            dz = max_z - min_z
                            max_dim = max(dx, dy, dz)
                            if max_dim > best_bbox and max_dim < 10000:
                                best_bbox = max_dim
                except struct.error:
                    break
                pos += 4

            if best_bbox > 0:
                info["bbox_max_dimension"] = best_bbox

            info["estimated_polys"] = int(file_size / 12)

        except Exception:
            pass

        return info
