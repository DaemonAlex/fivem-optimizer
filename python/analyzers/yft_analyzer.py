"""
YFT (Fragment/Vehicle Model) Analyzer

Analyzes .yft files with robust binary parsing.
"""
import os
from .model_parser import parse_model_geometry


class YftAnalyzer:
    def __init__(self, settings):
        self.max_polys = settings.get("maxVehiclePolys", 150000)
        self.rec_polys = settings.get("recommendedMaxVehiclePolys", 70000)
        self.max_bones = settings.get("maxBones", 200)
        self.rec_bones = 128
        self.max_size_mb = settings.get("maxYftSizeMB", 14)

    def analyze(self, filepath, rel_path, file_size):
        """Returns (issues, metadata) tuple. Reads file from disk and delegates to analyze_buffer."""
        try:
            with open(filepath, 'rb') as f:
                data = f.read(min(file_size, 128 * 1024))
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
                "file_type": ".yft",
                "severity": "critical",
                "category": "file_size",
                "message": f"Fragment model is very large ({size_mb:.1f} MB)",
                "recommendation": f"Optimize model geometry, reduce texture quality, or simplify LODs. Target under {self.max_size_mb} MB.",
                "details": {"size_mb": round(size_mb, 2)},
            })

        model_info = parse_model_geometry(data, vertex_range=(100, 200000), max_index_entries=8)
        metadata["model_info"] = model_info

        if model_info:
            poly_count = model_info.get("estimated_polys", 0)
            bone_count = model_info.get("estimated_bones", 0)
            lod_count = model_info.get("estimated_lods", 0)

            if poly_count > self.max_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".yft",
                    "severity": "critical",
                    "category": "polygon_count",
                    "message": f"Very high polygon count (~{poly_count:,})",
                    "recommendation": f"Reduce to under {self.rec_polys:,} polygons. High-poly vehicles cause FPS drops for all nearby players.",
                    "details": {"estimated_polygons": poly_count, "limit": self.max_polys},
                })
            elif poly_count > self.rec_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".yft",
                    "severity": "warning",
                    "category": "polygon_count",
                    "message": f"High polygon count (~{poly_count:,})",
                    "recommendation": f"Consider reducing to under {self.rec_polys:,} polygons for better multiplayer performance.",
                    "details": {"estimated_polygons": poly_count},
                })

            if bone_count > self.max_bones:
                issues.append({
                    "file": rel_path,
                    "file_type": ".yft",
                    "severity": "critical",
                    "category": "lod_bones",
                    "message": f"Exceeds bone limit ({bone_count} bones)",
                    "recommendation": f"GTA V supports max {self.max_bones} bones. Remove unnecessary bones to prevent crashes.",
                    "details": {"bone_count": bone_count, "limit": self.max_bones},
                })
            elif bone_count > self.rec_bones:
                issues.append({
                    "file": rel_path,
                    "file_type": ".yft",
                    "severity": "warning",
                    "category": "lod_bones",
                    "message": f"High bone count ({bone_count} bones)",
                    "recommendation": f"Consider reducing bone count to under {self.rec_bones} for stability.",
                    "details": {"bone_count": bone_count},
                })

            if lod_count < 2 and file_size > 512 * 1024:
                issues.append({
                    "file": rel_path,
                    "file_type": ".yft",
                    "severity": "warning",
                    "category": "lod_bones",
                    "message": "Insufficient LOD levels",
                    "recommendation": "Add at least 3 LOD levels (High, Medium, Low). Missing LODs force the game to render full detail at all distances.",
                    "details": {"detected_lods": lod_count, "recommended_minimum": 3},
                })

        # Heuristic fallback
        if not model_info or model_info.get("estimated_polys", 0) == 0:
            estimated = int(file_size / 20)
            if estimated > self.max_polys:
                issues.append({
                    "file": rel_path,
                    "file_type": ".yft",
                    "severity": "warning",
                    "category": "polygon_count",
                    "message": f"File size suggests high polygon count (~{estimated:,} estimated)",
                    "recommendation": "Based on file size, this model likely has excessive geometry. Verify in OpenIV and optimize if needed.",
                    "details": {"estimated_polygons": estimated, "method": "file_size_heuristic"},
                })

        return issues, metadata
