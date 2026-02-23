"""Generic file-level checks applicable to all asset types."""


class GenericAnalyzer:
    def __init__(self, settings):
        self.max_size_mb = settings.get("maxSingleFileMB", 16)
        self.warn_size_mb = settings.get("largeFileWarningMB", 8)

    def analyze(self, filepath, rel_path, ext, file_size):
        issues = []
        size_mb = file_size / (1024 * 1024)

        if size_mb > self.max_size_mb:
            issues.append({
                "file": rel_path,
                "file_type": ext,
                "severity": "critical",
                "category": "file_size",
                "message": f"Extremely large file ({size_mb:.1f} MB)",
                "recommendation": f"This file is {size_mb:.1f} MB which will cause streaming issues. Consider splitting or optimizing to stay under {self.max_size_mb} MB.",
                "details": {"size_mb": round(size_mb, 2)},
            })
        elif size_mb > self.warn_size_mb:
            issues.append({
                "file": rel_path,
                "file_type": ext,
                "severity": "warning",
                "category": "file_size",
                "message": f"Large file ({size_mb:.1f} MB)",
                "recommendation": f"File is {size_mb:.1f} MB. Consider optimizing to improve streaming performance.",
                "details": {"size_mb": round(size_mb, 2)},
            })

        return issues
