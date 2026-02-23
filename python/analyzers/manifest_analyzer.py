"""
FiveM Resource Manifest Analyzer

Parses fxmanifest.lua and __resource.lua files to extract:
- Resource name and metadata
- Dependencies (for load order / circular dependency detection)
- Streamed file declarations
- Data file entries
"""
import os
import re


# Patterns for manifest parsing
DEPENDENCY_PATTERN = re.compile(
    r'''(?:dependencies?\s*\{([^}]*)\}|dependency\s+['"]([^'"]+)['"])''',
    re.IGNORECASE | re.DOTALL
)
STRING_IN_LIST = re.compile(r'''['"]([^'"]+)['"]''')
FILES_PATTERN = re.compile(
    r'''files?\s*\{([^}]*)\}''',
    re.IGNORECASE | re.DOTALL
)
DATA_FILE_PATTERN = re.compile(
    r'''data_file\s+['"]([^'"]+)['"]\s+['"]([^'"]+)['"]''',
    re.IGNORECASE
)
FX_VERSION_PATTERN = re.compile(
    r'''fx_version\s+['"]([^'"]+)['"]''',
    re.IGNORECASE
)
GAME_PATTERN = re.compile(
    r'''game\s+['"]([^'"]+)['"]''',
    re.IGNORECASE
)
RESOURCE_MANIFEST_PATTERN = re.compile(
    r'''resource_manifest_version\s+['"]([^'"]+)['"]''',
    re.IGNORECASE
)


def parse_manifest(filepath):
    """Parse a fxmanifest.lua or __resource.lua file. Returns dict of metadata."""
    result = {
        "path": filepath,
        "fx_version": None,
        "game": None,
        "dependencies": [],
        "files": [],
        "data_files": [],
        "is_fxmanifest": os.path.basename(filepath).lower() == "fxmanifest.lua",
    }

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(32768)  # Cap at 32KB
    except (OSError, PermissionError):
        return result

    # Strip Lua comments (-- single line, --[[ multiline ]])
    content_no_comments = re.sub(r'--\[\[.*?\]\]', '', content, flags=re.DOTALL)
    content_no_comments = re.sub(r'--[^\n]*', '', content_no_comments)

    # fx_version
    m = FX_VERSION_PATTERN.search(content_no_comments)
    if m:
        result["fx_version"] = m.group(1)

    # resource_manifest_version (older format)
    if not result["fx_version"]:
        m = RESOURCE_MANIFEST_PATTERN.search(content_no_comments)
        if m:
            result["fx_version"] = m.group(1)

    # game
    m = GAME_PATTERN.search(content_no_comments)
    if m:
        result["game"] = m.group(1)

    # Dependencies
    for m in DEPENDENCY_PATTERN.finditer(content_no_comments):
        if m.group(1):  # dependencies { ... }
            for sm in STRING_IN_LIST.finditer(m.group(1)):
                dep = sm.group(1).strip()
                if dep:
                    result["dependencies"].append(dep)
        elif m.group(2):  # dependency 'name'
            result["dependencies"].append(m.group(2).strip())

    # Files
    for m in FILES_PATTERN.finditer(content_no_comments):
        for sm in STRING_IN_LIST.finditer(m.group(1)):
            result["files"].append(sm.group(1))

    # Data files
    for m in DATA_FILE_PATTERN.finditer(content_no_comments):
        result["data_files"].append({
            "type": m.group(1),
            "path": m.group(2),
        })

    return result


def find_manifests(folder_path):
    """Find all manifest files in a folder tree. Returns list of (resource_name, manifest_path)."""
    manifests = []
    try:
        for entry in os.scandir(folder_path):
            if entry.is_dir(follow_symlinks=False):
                _find_manifest_in_resource(entry.path, entry.name, manifests)
    except (OSError, PermissionError):
        pass
    return manifests


def _find_manifest_in_resource(dir_path, resource_name, manifests, depth=0):
    """Check a directory for manifest files (max 3 levels deep)."""
    if depth > 3:
        return
    try:
        for entry in os.scandir(dir_path):
            if entry.is_file(follow_symlinks=False):
                name_lower = entry.name.lower()
                if name_lower in ('fxmanifest.lua', '__resource.lua'):
                    manifests.append((resource_name, entry.path))
                    return
            elif entry.is_dir(follow_symlinks=False):
                _find_manifest_in_resource(entry.path, resource_name, manifests, depth + 1)
    except (OSError, PermissionError):
        pass


def analyze_manifests(folder_path):
    """Analyze all manifests in a folder. Returns issues list and resource metadata."""
    issues = []
    resources = {}

    manifests = find_manifests(folder_path)

    for resource_name, manifest_path in manifests:
        info = parse_manifest(manifest_path)
        resources[resource_name] = info

        # Check for old-style manifest
        if not info["is_fxmanifest"] and not info["fx_version"]:
            issues.append({
                "file": f"{resource_name}/__resource.lua",
                "file_type": "manifest",
                "severity": "info",
                "category": "resource_config",
                "message": f"Resource '{resource_name}' uses legacy __resource.lua",
                "recommendation": "Migrate to fxmanifest.lua for better compatibility and features.",
                "details": {"resource": resource_name},
            })

    # Detect circular dependencies
    dep_graph = {name: set(info["dependencies"]) for name, info in resources.items()}
    cycles = _detect_cycles(dep_graph)
    for cycle in cycles:
        issues.append({
            "file": f"{cycle[0]}/fxmanifest.lua",
            "file_type": "manifest",
            "severity": "warning",
            "category": "resource_config",
            "message": f"Circular dependency detected: {' -> '.join(cycle)}",
            "recommendation": "Circular dependencies can cause race conditions and load failures. Restructure your resources.",
            "details": {"cycle": cycle},
        })

    # Detect missing dependencies
    known_resources = set(resources.keys())
    for name, info in resources.items():
        for dep in info["dependencies"]:
            if dep not in known_resources and not dep.startswith(('yarn', 'webpack', 'mysql', 'oxmysql', 'es_extended', 'qb-core')):
                # Only flag if the dep looks like a local resource
                if '/' not in dep and not dep.startswith('['):
                    issues.append({
                        "file": f"{name}/fxmanifest.lua",
                        "file_type": "manifest",
                        "severity": "info",
                        "category": "resource_config",
                        "message": f"Resource '{name}' depends on '{dep}' (not found in scan folder)",
                        "recommendation": "Ensure this dependency is available on the server. Missing dependencies cause load failures.",
                        "details": {"resource": name, "missing_dep": dep},
                    })

    return issues, resources


def _detect_cycles(graph):
    """Detect cycles in a dependency graph using DFS."""
    cycles = []
    visited = set()
    in_stack = set()

    def dfs(node, path):
        if node in in_stack:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        for dep in graph.get(node, []):
            if dep in graph:
                dfs(dep, path)
        path.pop()
        in_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return cycles


def build_resource_size_map(files, folder_path):
    """
    Group files by their parent resource folder.
    Returns dict: resource_name -> {total_size, file_count, files_by_type}.
    """
    resources = {}
    folder_prefix_len = len(folder_path.rstrip(os.sep)) + 1

    for filepath, ext, file_size in files:
        rel = filepath[folder_prefix_len:]
        parts = rel.replace("\\", "/").split("/")
        resource = parts[0] if len(parts) > 1 else "(root)"

        if resource not in resources:
            resources[resource] = {
                "total_size": 0,
                "file_count": 0,
                "files_by_type": {},
            }
        resources[resource]["total_size"] += file_size
        resources[resource]["file_count"] += 1
        if ext not in resources[resource]["files_by_type"]:
            resources[resource]["files_by_type"][ext] = {"count": 0, "size": 0}
        resources[resource]["files_by_type"][ext]["count"] += 1
        resources[resource]["files_by_type"][ext]["size"] += file_size

    return resources
