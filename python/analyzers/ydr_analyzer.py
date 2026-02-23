"""
YDR (Drawable Model) Analyzer

Analyzes .ydr files with robust binary parsing.
"""
import os
from .model_parser import parse_model_geometry


class YdrAnalyzer:
    def __init__(self, settings):
        self.max_polys = settings.get("maxPropPolys", 50000)
        self.rec_polys = settings.get("recommendedMaxPropPolys", 15000)
        self.max_size_mb = settings.get("maxYdrSizeMB", 8)

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
                "file_type": ".ydr",
                "severity": "critical",
                "category": "file_size",
                "message": f"Drawable model is very large ({size_mb:.1f} MB)",
                "recommendation": f"Reduce geometry complexity and texture sizes. Target under {self.max_size_mb} MB for props/objects.",
                "details": {"size_mb": round(size_mb, 2)},
            })

        # Props use a lower vertex range than vehicles
        model_info = parse_model_geometry(data, vertex_range=(50, 150000), max_index_entries=6)
        metadata["model_info"] = model_info

        if model_info:
            poly_count = model_info.get("estimated_polys", 0)
            lod_count = model_info.get("estimated_lods", 0)

            if poly_count > self.max_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ydr",
                    "severity": "critical",
                    "category": "polygon_count",
                    "message": f"Very high polygon count (~{poly_count:,})",
                    "recommendation": f"Reduce to under {self.rec_polys:,} polygons. High-poly props multiply performance impact when placed multiple times.",
                    "details": {"estimated_polygons": poly_count},
                })
            elif poly_count > self.rec_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ydr",
                    "severity": "warning",
                    "category": "polygon_count",
                    "message": f"High polygon count (~{poly_count:,})",
                    "recommendation": f"Consider reducing to under {self.rec_polys:,} polygons.",
                    "details": {"estimated_polygons": poly_count},
                })

            if lod_count < 2 and file_size > 256 * 1024:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ydr",
                    "severity": "warning",
                    "category": "lod_bones",
                    "message": "Insufficient LOD levels",
                    "recommendation": "Add LOD levels so the model simplifies at distance.",
                    "details": {"detected_lods": lod_count},
                })
        else:
            estimated = int(file_size / 18)
            if estimated > self.max_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".ydr",
                    "severity": "warning",
                    "category": "polygon_count",
                    "message": f"File size suggests high polygon count (~{estimated:,} estimated)",
                    "recommendation": "Verify polygon count in OpenIV or 3D modeling tool.",
                    "details": {"estimated_polygons": estimated, "method": "file_size_heuristic"},
                })

        return issues, metadata
