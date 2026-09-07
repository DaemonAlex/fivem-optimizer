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
                "message": f"Very large file on disk ({size_mb:.1f} MB)",
                "recommendation": f"Disk size is a hint only: stream files are compressed on disk and the game allocates what the file header says. Check FXServer's boot log for the real memory number.",
                "details": {"size_mb": round(size_mb, 2)},
            })
        elif size_mb > self.warn_size_mb:
            issues.append({
                "file": rel_path,
                "file_type": ext,
                "severity": "warning",
                "category": "file_size",
                "message": f"Large file ({size_mb:.1f} MB)",
                "recommendation": "Disk size is a hint only; the boot log's 'uses N MiB' line is the real cost.",
                "details": {"size_mb": round(size_mb, 2)},
            })

        return issues
