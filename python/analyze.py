"""
FiveM Streaming Asset Analyzer
Main entry point - scans a folder and outputs JSON results.

Performance: uses thread pool for I/O-bound file analysis, single-read-per-file
strategy, and fast partial hashing for duplicate detection.
"""
import sys
import os
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from analyzers.ytd_analyzer import YtdAnalyzer
from analyzers.yft_analyzer import YftAnalyzer
from analyzers.ydr_analyzer import YdrAnalyzer
from analyzers.ybn_analyzer import YbnAnalyzer
from analyzers.ymap_analyzer import YmapAnalyzer
from analyzers.ytyp_analyzer import YtypAnalyzer
from analyzers.generic_analyzer import GenericAnalyzer
from analyzers.manifest_analyzer import analyze_manifests, build_resource_size_map


SUPPORTED_ANALYZERS = {
    '.ytd': YtdAnalyzer,
    '.yft': YftAnalyzer,
    '.ydr': YdrAnalyzer,
    '.ybn': YbnAnalyzer,
    '.ymap': YmapAnalyzer,
    '.ytyp': YtypAnalyzer,
}

ALL_EXTENSIONS = frozenset(SUPPORTED_ANALYZERS.keys())

DEFAULT_SETTINGS = {
    # Texture limits (community-validated)
    "maxTextureResolution": 4096,       # 4K is common in community, 8K is hard GPU limit
    "recommendedMaxResolution": 2048,   # 2K is safe baseline for most assets
    "maxYtdSizeMB": 14,                # Safe under 16MB FiveM streaming hard limit
    # Vehicle/fragment limits
    "maxVehiclePolys": 150000,          # Community standard L0 range: 100-150K
    "recommendedMaxVehiclePolys": 70000,# Good target for optimized vehicles
    "maxBones": 200,                    # 255 theoretical max, 200 practical limit
    "maxYftSizeMB": 14,                # Safe under 16MB limit
    # Prop/drawable limits
    "maxPropPolys": 50000,              # Single-mesh props
    "recommendedMaxPropPolys": 15000,   # Good target for props placed many times
    "maxYdrSizeMB": 8,
    # Collision limits
    "maxCollisionPolys": 10000,         # Community: keep collision simple
    "maxYbnSizeMB": 4,
    "maxBoundsDimension": 500,
    # General
    "maxSingleFileMB": 16,             # FiveM HARD LIMIT - cannot stream above 16MB
    "largeFileWarningMB": 10,
    # LOD validation
    "minLodLevels": 2,                  # Minimum acceptable LOD chain
    "recommendedLodLevels": 4,          # L0-L3 preferred for vehicles
    # Optimizer settings
    "optimizerTargetResolution": 1024,  # Default downscale target
    "optimizerSkipScriptRt": True,      # Never resize script_rt textures
    "optimizerSkipEmissive": True,      # Skip emissive/light textures
    "optimizerMinResizeSize": 1048576,  # Only resize textures in files >1MB
}

# How many bytes to read for the fast duplicate hash (head + tail)
HASH_SAMPLE_SIZE = 16384  # 16KB from head + 16KB from tail
# Max bytes to read for binary analysis per file type
ANALYSIS_READ_LIMITS = {
    '.ytd': 65536,
    '.yft': 131072,
    '.ydr': 65536,
    '.ybn': 65536,
    '.ymap': 262144,
    '.ytyp': 65536,
}
# Worker threads for file analysis
WORKER_THREADS = 8


def progress(msg):
    """Send progress update to Electron."""
    print(f"PROGRESS:{msg}", flush=True)


def fast_file_hash(filepath, file_size):
    """
    Fast duplicate detection hash using file size + head + tail sampling.
    Much faster than full SHA256 — reads at most 32KB per file instead of the
    entire file. Collisions are extremely unlikely given size+head+tail combo.
    """
    try:
        h = hashlib.md5()
        # Mix in the file size to avoid collisions between different-sized files
        h.update(file_size.to_bytes(8, 'little'))
        with open(filepath, 'rb') as f:
            # Read head
            head = f.read(HASH_SAMPLE_SIZE)
            h.update(head)
            # Read tail if file is large enough
            if file_size > HASH_SAMPLE_SIZE * 2:
                f.seek(-HASH_SAMPLE_SIZE, 2)
                tail = f.read(HASH_SAMPLE_SIZE)
                h.update(tail)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def scan_folder(folder_path):
    """Scan folder recursively for streaming assets. Returns list of (path, ext, stat)."""
    files = []
    try:
        for entry in os.scandir(folder_path):
            _scan_entry(entry, files)
    except (OSError, PermissionError):
        pass
    return files


def _scan_entry(entry, files):
    """Recursively scan a directory entry."""
    try:
        if entry.is_dir(follow_symlinks=False):
            for sub in os.scandir(entry.path):
                _scan_entry(sub, files)
        elif entry.is_file(follow_symlinks=False):
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in ALL_EXTENSIONS:
                try:
                    stat = entry.stat()
                    files.append((entry.path, ext, stat.st_size))
                except OSError:
                    pass
    except (OSError, PermissionError):
        pass


def analyze_single_file(filepath, ext, file_size, rel_path, settings, analyzers):
    """
    Analyze a single file. Runs in a worker thread.
    Returns (issues, metadata, hash_info, dep_data).
    Reads the file ONCE and shares the buffer between analyzer and hasher.
    """
    issues = []
    metadata = {}
    hash_info = None
    dep_data = None

    # Generic size checks (no I/O needed)
    generic = analyzers['generic']
    issues.extend(generic.analyze(filepath, rel_path, ext, file_size))

    # Read the file once — shared between analyzer and hasher
    read_limit = ANALYSIS_READ_LIMITS.get(ext, 65536)
    data_buf = None
    try:
        with open(filepath, 'rb') as f:
            data_buf = f.read(min(file_size, read_limit))

            # Fast hash for duplicate detection (uses same file handle)
            if 4096 <= file_size < 100 * 1024 * 1024:
                h = hashlib.md5()
                h.update(file_size.to_bytes(8, 'little'))
                h.update(data_buf[:HASH_SAMPLE_SIZE])
                if file_size > HASH_SAMPLE_SIZE * 2:
                    f.seek(-HASH_SAMPLE_SIZE, 2)
                    tail = f.read(HASH_SAMPLE_SIZE)
                    h.update(tail)
                hash_info = h.hexdigest()
    except (OSError, PermissionError):
        issues.append({
            "file": rel_path,
            "file_type": ext,
            "severity": "info",
            "category": "resource_config",
            "message": "File could not be accessed (may be in use)",
            "recommendation": "Close any programs using this file and re-scan.",
        })
        return issues, metadata, None, None

    # Type-specific analysis — pass the already-read buffer
    analyzer = analyzers.get(ext)
    if analyzer and data_buf is not None:
        try:
            type_issues, meta = analyzer.analyze_buffer(
                data_buf, filepath, rel_path, file_size
            )
            issues.extend(type_issues)
            metadata = meta
        except Exception as e:
            issues.append({
                "file": rel_path,
                "file_type": ext,
                "severity": "info",
                "message": f"Could not fully analyze file: {type(e).__name__}",
                "recommendation": "File may be corrupted or in an unexpected format.",
            })

    # Stash raw data for dependency mapping (ymap/ytyp only)
    if ext in ('.ymap', '.ytyp') and data_buf:
        dep_data = data_buf

    return issues, metadata, hash_info, dep_data


def build_dependency_map_fast(dep_buffers, known_assets, folder_path):
    """
    Build dependency map from pre-read buffers (no extra disk I/O).
    """
    deps = {"references": {}, "defined_by": {}, "missing": []}

    for rel_path, data_buf in dep_buffers.items():
        try:
            text_data = data_buf.decode('utf-8', errors='ignore').lower()
        except Exception:
            continue
        refs = set()
        for name in known_assets:
            if len(name) >= 3 and name in text_data:
                refs.add(name)
        self_name = os.path.splitext(os.path.basename(rel_path))[0].lower()
        refs.discard(self_name)
        if refs:
            deps["references"][rel_path] = list(refs)

    return deps


def analyze(folder_path, settings):
    """Run full analysis on a streaming folder."""
    if not os.path.isdir(folder_path):
        return {"error": f"Not a valid directory: {folder_path}"}

    progress("Scanning directory structure...")
    files = scan_folder(folder_path)
    total_files = len(files)

    if not files:
        return {
            "summary": {
                "total_files": 0, "total_size": 0, "issues_count": 0,
                "critical_count": 0, "warning_count": 0, "vram_estimate": 0,
                "no_assets_found": True,
            },
            "issues": [], "duplicates": [],
            "dependencies": {"references": {}, "defined_by": {}, "missing": []},
            "file_stats": {},
        }

    progress(f"Found {total_files} streaming assets")

    # Pre-create analyzer instances once (not per-file)
    analyzer_instances = {
        'generic': GenericAnalyzer(settings),
    }
    for ext, cls in SUPPORTED_ANALYZERS.items():
        analyzer_instances[ext] = cls(settings)

    # Precompute all rel_paths at once
    folder_prefix_len = len(folder_path.rstrip(os.sep)) + 1
    file_entries = []
    for filepath, ext, file_size in files:
        rel_path = filepath[folder_prefix_len:]  # Fast substring instead of os.path.relpath
        file_entries.append((filepath, ext, file_size, rel_path))

    # Parallel analysis with thread pool
    all_issues = []
    all_files = []  # Per-file info for optimizer
    file_stats = {}
    hash_map = {}
    dep_buffers = {}
    total_size = 0
    total_vram = 0
    completed = 0

    def update_progress(count):
        pct = int(count / total_files * 100)
        progress(f"{pct}%|{count}/{total_files}|Analyzing files...")

    with ThreadPoolExecutor(max_workers=WORKER_THREADS) as pool:
        futures = {}
        for filepath, ext, file_size, rel_path in file_entries:
            fut = pool.submit(
                analyze_single_file,
                filepath, ext, file_size, rel_path,
                settings, analyzer_instances,
            )
            futures[fut] = (ext, file_size, rel_path)

        for fut in as_completed(futures):
            ext, file_size, rel_path = futures[fut]
            completed += 1

            if completed % 50 == 0 or completed == total_files:
                update_progress(completed)

            total_size += file_size

            # File stats
            if ext not in file_stats:
                file_stats[ext] = {"count": 0, "size": 0}
            file_stats[ext]["count"] += 1
            file_stats[ext]["size"] += file_size

            try:
                issues, metadata, hash_info, dep_data = fut.result()
            except Exception:
                continue

            # Track per-file info for optimizer
            file_issue_count = len(issues)
            file_entry_info = {
                "rel_path": rel_path,
                "ext": ext,
                "size": file_size,
                "issues": file_issue_count,
            }
            if ext == '.ytd' and metadata.get("vram_estimate"):
                file_entry_info["vram"] = metadata["vram_estimate"]
            all_files.append(file_entry_info)

            all_issues.extend(issues)

            if ext == '.ytd' and metadata.get("vram_estimate"):
                total_vram += metadata["vram_estimate"]

            if hash_info:
                if hash_info not in hash_map:
                    hash_map[hash_info] = {"files": [], "size": file_size}
                hash_map[hash_info]["files"].append(rel_path)

            if dep_data:
                dep_buffers[rel_path] = dep_data

    # Dependency map from pre-read buffers (zero extra I/O)
    progress("Mapping asset dependencies...")
    known_assets = set()
    for _, _, _, rel_path in file_entries:
        name = os.path.splitext(os.path.basename(rel_path))[0].lower()
        known_assets.add(name)
    dependencies = build_dependency_map_fast(dep_buffers, known_assets, folder_path)

    # Build duplicate groups (cross-resource, same-name only)
    progress("Checking for duplicates...")
    duplicates = []
    for file_hash, data in hash_map.items():
        if len(data["files"]) < 2:
            continue

        resource_folders = set()
        for f in data["files"]:
            parts = f.replace("\\", "/").split("/")
            resource_folders.add(parts[0] if len(parts) > 1 else "")

        if len(resource_folders) < 2:
            continue

        filenames = [os.path.basename(f) for f in data["files"]]
        name_groups = {}
        for i, name in enumerate(filenames):
            name_groups.setdefault(name, []).append(data["files"][i])

        for name, file_list in name_groups.items():
            if len(file_list) < 2:
                continue
            res_folders = set()
            for f in file_list:
                parts = f.replace("\\", "/").split("/")
                res_folders.add(parts[0] if len(parts) > 1 else "")
            if len(res_folders) < 2:
                continue
            duplicates.append({
                "hash": file_hash,
                "size": data["size"],
                "files": file_list,
            })

    duplicates.sort(key=lambda d: d["size"] * (len(d["files"]) - 1), reverse=True)

    for dup in duplicates:
        wasted = dup["size"] * (len(dup["files"]) - 1)
        all_issues.append({
            "file": dup["files"][0],
            "file_type": os.path.splitext(dup["files"][0])[1],
            "severity": "warning" if wasted > 1024 * 1024 else "info",
            "category": "duplicates",
            "message": f"Duplicate file across resources ({len(dup['files'])} copies of {os.path.basename(dup['files'][0])})",
            "recommendation": f"The same file exists in {len(dup['files'])} different resources. Remove {len(dup['files']) - 1} copy(ies) to save {wasted / (1024*1024):.1f} MB.",
            "details": {"copies": len(dup["files"]), "wasted_bytes": wasted},
        })

    # Analyze resource manifests (fxmanifest.lua / __resource.lua)
    progress("Analyzing resource manifests...")
    manifest_issues, resource_manifests = analyze_manifests(folder_path)
    all_issues.extend(manifest_issues)

    # Build per-resource size breakdown
    resource_sizes = build_resource_size_map(files, folder_path)

    # Flag oversized resources (total streaming cost)
    for res_name, res_info in resource_sizes.items():
        res_size_mb = res_info["total_size"] / (1024 * 1024)
        if res_size_mb > 64:
            all_issues.append({
                "file": f"{res_name}/",
                "file_type": "resource",
                "severity": "warning",
                "category": "resource_config",
                "message": f"Resource '{res_name}' is very large ({res_size_mb:.1f} MB total, {res_info['file_count']} files)",
                "recommendation": "Large resources increase download time for joining players. Consider splitting into smaller resources.",
                "details": {"resource": res_name, "total_size_mb": round(res_size_mb, 1), "file_count": res_info["file_count"]},
            })

    progress("Analysis complete!")

    # Sort files by size descending for optimizer
    all_files.sort(key=lambda f: f["size"], reverse=True)

    return {
        "summary": {
            "total_files": total_files,
            "total_size": total_size,
            "issues_count": len(all_issues),
            "critical_count": sum(1 for i in all_issues if i["severity"] == "critical"),
            "warning_count": sum(1 for i in all_issues if i["severity"] == "warning"),
            "vram_estimate": total_vram,
            "resource_count": len(resource_sizes),
        },
        "issues": all_issues,
        "duplicates": duplicates,
        "dependencies": dependencies,
        "file_stats": file_stats,
        "files": all_files,
        "resources": resource_sizes,
        "manifests": {
            name: {
                "fx_version": info.get("fx_version"),
                "dependencies": info.get("dependencies", []),
                "data_files_count": len(info.get("data_files", [])),
            }
            for name, info in resource_manifests.items()
        },
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"error": "Usage: analyze.py <folder_path> [settings_json]"}))
            sys.exit(1)

        folder = sys.argv[1]

        settings = DEFAULT_SETTINGS.copy()
        if len(sys.argv) >= 3:
            try:
                user_settings = json.loads(sys.argv[2])
                settings.update(user_settings)
            except (json.JSONDecodeError, TypeError):
                pass

        results = analyze(folder, settings)
        print(json.dumps(results, ensure_ascii=False))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
