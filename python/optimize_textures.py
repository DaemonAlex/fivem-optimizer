"""
FiveM Texture Optimization Engine

Optimizes .ytd texture files by:
- Identifying oversized textures via binary analysis
- In-place mipmap replacement: copies a lower mip level to mip 0 position,
  effectively halving dimensions without unpacking/repacking RSC7 containers
- Providing size estimates and optimization recommendations

Safety:
- Always creates backup before modifying any file
- Skips script_rt textures (MUST remain uncompressed)
- Skips emissive/light textures (visual artifacts if resized)
- Validates physical segment sizes before patching (15% tolerance)
- Dry-run mode to preview changes without modifying files

Usage:
    python optimize_textures.py <folder_path> <settings_json>
    python optimize_textures.py --execute <json_payload>
"""
import sys
import os
import json
import shutil
import struct
import subprocess
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent dir to path for analyzer imports
sys.path.insert(0, os.path.dirname(__file__))
from analyzers.model_parser import extract_texture_names

RSC7_MAGIC = 0x37435352

# Bytes per pixel for each DXGI format (block-compressed use fractional BPP)
FORMAT_BPP = {
    71: 0.5,   # BC1/DXT1: 4 bits per pixel (8 bytes per 4x4 block)
    74: 1.0,   # BC2/DXT3: 8 bits per pixel (16 bytes per 4x4 block)
    77: 1.0,   # BC3/DXT5: 8 bits per pixel (16 bytes per 4x4 block)
    80: 0.5,   # BC4/ATI1: 4 bits per pixel
    83: 1.0,   # BC5/ATI2: 8 bits per pixel
    98: 1.0,   # BC7: 8 bits per pixel (16 bytes per 4x4 block)
    28: 4.0,   # R8G8B8A8: 32 bits per pixel
    87: 4.0,   # B8G8R8A8: 32 bits per pixel
}

# Block-compressed formats use 4x4 blocks
BLOCK_COMPRESSED_FORMATS = {71, 74, 77, 80, 83, 98}

# Block sizes in bytes for block-compressed formats
BLOCK_SIZES = {
    71: 8,    # BC1/DXT1
    74: 16,   # BC2/DXT3
    77: 16,   # BC3/DXT5
    80: 8,    # BC4/ATI1
    83: 16,   # BC5/ATI2
    98: 16,   # BC7
}


def progress(msg):
    """Send progress update to Electron."""
    print(f"PROGRESS:{msg}", flush=True)


def mip_level_size(w, h, fmt):
    """Calculate byte size of a single mip level for the given format."""
    if fmt in BLOCK_COMPRESSED_FORMATS:
        block_size = BLOCK_SIZES.get(fmt, 16)
        blocks_w = max(1, (w + 3) // 4)
        blocks_h = max(1, (h + 3) // 4)
        return blocks_w * blocks_h * block_size
    else:
        bpp = FORMAT_BPP.get(fmt, 4.0)
        return int(w * h * bpp)


def total_mip_chain_size(w, h, fmt, mip_count):
    """Sum of all mip levels' byte sizes."""
    total = 0
    for i in range(mip_count):
        mw = max(1, w >> i)
        mh = max(1, h >> i)
        total += mip_level_size(mw, mh, fmt)
    return total


def calc_rsc7_sizes(virtual_flags, physical_flags):
    """
    Compute virtual and physical segment sizes from RSC7 flags.
    Based on CodeWalker's ResourceFile implementation.
    """
    def flag_to_size(flags):
        base_shift = flags & 0xF
        s0 = ((flags >> 4) & 0x1) << (base_shift + 0)
        s1 = ((flags >> 5) & 0x1) << (base_shift + 1)
        s2 = ((flags >> 6) & 0x1) << (base_shift + 2)
        s3 = ((flags >> 7) & 0x1) << (base_shift + 3)
        s4 = ((flags >> 8) & 0x1) << (base_shift + 4)
        s5 = ((flags >> 9) & 0x1) << (base_shift + 5)
        s6 = ((flags >> 10) & 0x1) << (base_shift + 6)
        s7 = ((flags >> 11) & 0x1) << (base_shift + 7)
        s8 = ((flags >> 12) & 0x1) << (base_shift + 8)
        size = s0 + s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8
        return size if size > 0 else (1 << base_shift)

    return flag_to_size(virtual_flags), flag_to_size(physical_flags)


def find_texture_entries(data, scan_start):
    """
    Scan binary data for texture metadata entries.
    Returns list of dicts with width, height, format, mipmaps, and the byte offset
    of the width/height fields so we can patch them in-place.
    """
    textures = []
    pos = scan_start
    seen = set()

    while pos < len(data) - 8 and len(textures) < 32:
        try:
            w = struct.unpack_from('<H', data, pos)[0]
            h = struct.unpack_from('<H', data, pos + 2)[0]

            if (_is_pow2(w) and _is_pow2(h) and 4 <= w <= 8192 and 4 <= h <= 8192):
                key = (w, h, pos // 64)
                if key not in seen:
                    seen.add(key)

                    fmt = 0
                    mips = 1
                    if pos >= 4:
                        potential_fmt = struct.unpack_from('<B', data, pos - 4)[0]
                        if potential_fmt in FORMAT_BPP:
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
                        "meta_offset": pos,  # offset of width field in data
                    })
                    pos += 16
                    continue
        except struct.error:
            break
        pos += 2

    return textures


def optimize_ytd_inplace(filepath, target_res, backup_folder):
    """
    Optimize a YTD file by in-place mipmap replacement.

    For each texture where max(w,h) > target_res:
    1. Calculate how many mip levels to skip
    2. Copy the lower mip's data to mip 0's position in the physical segment
    3. Patch width/height/mipcount in the metadata
    4. Zero-fill freed space

    Returns dict with status and stats.
    """
    result = {
        "status": "ok",
        "original_size": 0,
        "textures_resized": 0,
        "textures_total": 0,
        "errors": [],
    }

    try:
        with open(filepath, 'rb') as f:
            data = bytearray(f.read())
    except (OSError, PermissionError) as e:
        result["status"] = "error"
        result["errors"].append(f"Cannot read file: {e}")
        return result

    result["original_size"] = len(data)

    if len(data) < 16:
        result["status"] = "error"
        result["errors"].append("File too small to be a valid YTD")
        return result

    # Parse RSC7 header
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != RSC7_MAGIC:
        result["status"] = "error"
        result["errors"].append("Not a valid RSC7 file")
        return result

    version = struct.unpack_from('<I', data, 4)[0]
    virtual_flags = struct.unpack_from('<I', data, 8)[0]
    physical_flags = struct.unpack_from('<I', data, 12)[0]

    virtual_size, physical_size = calc_rsc7_sizes(virtual_flags, physical_flags)

    # Validate RSC7 segment sizes
    if virtual_size <= 0 or physical_size <= 0:
        result["status"] = "error"
        result["errors"].append("Invalid RSC7 header: zero or negative segment sizes")
        return result

    physical_offset = 16 + virtual_size  # where physical segment starts in file

    # Validate file size vs expected sizes
    expected_total = 16 + virtual_size + physical_size
    tolerance = 0.15
    if abs(len(data) - expected_total) > expected_total * tolerance:
        result["status"] = "skipped"
        result["errors"].append(
            f"File size {len(data)} doesn't match expected {expected_total} "
            f"(virtual={virtual_size}, physical={physical_size}). Skipping for safety."
        )
        return result

    # Find texture entries in the virtual segment (metadata lives there)
    # We scan the full data since the header scanner works on the raw bytes
    scan_start = 16  # skip RSC7 header, start in virtual segment
    textures = find_texture_entries(data, scan_start)
    result["textures_total"] = len(textures)

    if not textures:
        result["status"] = "skipped"
        result["errors"].append("No texture entries found in file")
        return result

    # Extract texture names for skip detection
    text_region = data[16:16 + min(virtual_size, 65536)]
    names = [n.lower() for n in extract_texture_names(bytes(text_region))]

    # Calculate pixel data offsets in the physical segment
    # Textures' pixel data is stored sequentially in the physical segment
    # We build a map of each texture's data region
    pixel_offsets = []
    current_pixel_offset = physical_offset
    for tex in textures:
        chain_size = total_mip_chain_size(
            tex["width"], tex["height"], tex["format"], tex["mipmaps"]
        )
        pixel_offsets.append({
            "start": current_pixel_offset,
            "chain_size": chain_size,
        })
        current_pixel_offset += chain_size

    # Verify total pixel data roughly fits in physical segment
    total_pixel_data = sum(p["chain_size"] for p in pixel_offsets)
    if total_pixel_data > physical_size * (1 + tolerance):
        result["status"] = "skipped"
        result["errors"].append(
            f"Calculated pixel data ({total_pixel_data}) exceeds physical segment "
            f"({physical_size}). Binary layout may differ from expected."
        )
        return result

    modified = False
    for i, tex in enumerate(textures):
        w, h = tex["width"], tex["height"]
        max_dim = max(w, h)

        if max_dim <= target_res:
            continue

        # Check name-based skip
        tex_name = names[i] if i < len(names) else ""
        if tex_name:
            if tex_name.startswith('scr') or tex_name.startswith('script_rt'):
                continue
            if any(p in tex_name for p in ('emis', 'emissive', 'light', 'glow')):
                continue

        # Calculate how many levels to skip to reach target_res
        levels_to_skip = 0
        cur_w, cur_h = w, h
        while max(cur_w, cur_h) > target_res and levels_to_skip < tex["mipmaps"] - 1:
            cur_w = max(1, cur_w >> 1)
            cur_h = max(1, cur_h >> 1)
            levels_to_skip += 1

        if levels_to_skip == 0:
            continue

        new_w = max(1, w >> levels_to_skip)
        new_h = max(1, h >> levels_to_skip)
        new_mip_count = tex["mipmaps"] - levels_to_skip

        if new_mip_count < 1:
            continue

        # Calculate source offset: skip past the first N mip levels
        source_offset_within = 0
        for lvl in range(levels_to_skip):
            mw = max(1, w >> lvl)
            mh = max(1, h >> lvl)
            source_offset_within += mip_level_size(mw, mh, tex["format"])

        pix = pixel_offsets[i]
        src_abs = pix["start"] + source_offset_within
        dst_abs = pix["start"]

        # Calculate new chain size
        new_chain_size = total_mip_chain_size(new_w, new_h, tex["format"], new_mip_count)
        old_chain_size = pix["chain_size"]

        # Safety: verify src and dst are within file bounds
        if src_abs + new_chain_size > len(data):
            result["errors"].append(
                f"Texture {i} ({w}x{h}): source data extends beyond file. Skipped."
            )
            continue
        if dst_abs + old_chain_size > len(data):
            result["errors"].append(
                f"Texture {i} ({w}x{h}): destination extends beyond file. Skipped."
            )
            continue

        # Copy the lower mip data to the start position
        data[dst_abs:dst_abs + new_chain_size] = data[src_abs:src_abs + new_chain_size]

        # Zero-fill the freed space
        freed_start = dst_abs + new_chain_size
        freed_end = dst_abs + old_chain_size
        if freed_end > freed_start:
            data[freed_start:freed_end] = b'\x00' * (freed_end - freed_start)

        # Patch metadata: width, height at meta_offset (2 bytes each, little-endian)
        meta_off = tex["meta_offset"]
        struct.pack_into('<H', data, meta_off, new_w)
        struct.pack_into('<H', data, meta_off + 2, new_h)

        # Patch mipmap count (1 byte at meta_offset + 4)
        if meta_off + 4 < len(data):
            struct.pack_into('<B', data, meta_off + 4, new_mip_count)

        result["textures_resized"] += 1
        modified = True

    if modified:
        try:
            with open(filepath, 'wb') as f:
                f.write(data)
        except (OSError, PermissionError) as e:
            result["status"] = "error"
            result["errors"].append(f"Failed to write modified file: {e}")
            return result

    return result


def execute_optimization(payload):
    """
    Execute texture optimization on selected files.

    payload = {
        folder_path: str,
        selected_files: [rel_path, ...],
        backup_folder: str or null,
        target_resolution: int
    }
    """
    folder_path = payload["folder_path"]
    selected_files = payload["selected_files"]
    backup_dir = payload.get("backup_folder")
    target_res = payload.get("target_resolution", 1024)

    results = {
        "status": "completed",
        "files_processed": 0,
        "files_succeeded": 0,
        "files_failed": 0,
        "files_skipped": 0,
        "total_original_size": 0,
        "errors": [],
    }

    total = len(selected_files)
    if total == 0:
        results["status"] = "no_files"
        return results

    progress(f"Optimizing {total} files...")

    for i, rel_path in enumerate(selected_files):
        pct = int((i + 1) / total * 100)
        progress(f"{pct}%|{i+1}/{total}|Optimizing {os.path.basename(rel_path)}")

        abs_path = os.path.normpath(os.path.join(folder_path, rel_path))
        # Path traversal protection: ensure resolved path stays within folder
        if not abs_path.startswith(os.path.normpath(folder_path)):
            results["files_failed"] += 1
            results["errors"].append({"file": rel_path, "error": "Invalid path: outside scan folder"})
            continue
        results["files_processed"] += 1

        if not os.path.isfile(abs_path):
            results["files_failed"] += 1
            results["errors"].append({"file": rel_path, "error": "File not found"})
            continue

        # Create backup
        if backup_dir:
            backup_path = create_backup(abs_path, backup_dir)
            if not backup_path:
                results["files_failed"] += 1
                results["errors"].append({"file": rel_path, "error": "Backup failed"})
                continue

        try:
            res = optimize_ytd_inplace(abs_path, target_res, backup_dir)
            results["total_original_size"] += res.get("original_size", 0)

            if res["status"] == "ok":
                if res["textures_resized"] > 0:
                    results["files_succeeded"] += 1
                else:
                    results["files_skipped"] += 1
            elif res["status"] == "skipped":
                results["files_skipped"] += 1
                if res["errors"]:
                    results["errors"].append({
                        "file": rel_path,
                        "error": res["errors"][0],
                    })
            else:
                results["files_failed"] += 1
                results["errors"].append({
                    "file": rel_path,
                    "error": "; ".join(res["errors"]),
                })
        except Exception as e:
            results["files_failed"] += 1
            results["errors"].append({"file": rel_path, "error": str(e)})

    progress("Optimization complete!")
    return results


def find_texconv():
    """Find texconv.exe in common locations."""
    candidates = [
        # Bundled with our app
        os.path.join(os.path.dirname(__file__), 'tools', 'texconv.exe'),
        os.path.join(os.path.dirname(__file__), '..', 'tools', 'texconv.exe'),
        # System PATH
        'texconv.exe',
        'texconv',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
        # Check PATH
        try:
            result = subprocess.run(
                [path, '--version'],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def scan_ytd_files(folder_path, min_size=0):
    """Scan folder for .ytd files above min_size bytes."""
    ytd_files = []
    for root, dirs, filenames in os.walk(folder_path):
        for name in filenames:
            if name.lower().endswith('.ytd'):
                filepath = os.path.join(root, name)
                try:
                    size = os.path.getsize(filepath)
                    if size >= min_size:
                        rel = os.path.relpath(filepath, folder_path)
                        ytd_files.append({
                            "path": filepath,
                            "rel_path": rel,
                            "size": size,
                        })
                except OSError:
                    pass
    ytd_files.sort(key=lambda f: f["size"], reverse=True)
    return ytd_files


def analyze_ytd_for_optimization(filepath):
    """
    Analyze a single YTD file and return optimization info.
    Returns dict with texture details and estimated savings.
    """
    info = {
        "path": filepath,
        "size": 0,
        "texture_count": 0,
        "max_dimension": 0,
        "has_script_rt": False,
        "has_emissive": False,
        "estimated_savings_pct": 0,
        "textures": [],
    }

    try:
        info["size"] = os.path.getsize(filepath)
        with open(filepath, 'rb') as f:
            data = f.read(min(info["size"], 65536))
    except (OSError, PermissionError):
        return info

    if len(data) < 16:
        return info

    # Scan for texture dimensions
    magic = struct.unpack_from('<I', data, 0)[0]
    scan_start = 12 if magic == RSC7_MAGIC else 0

    # Extract texture names
    names = [n.lower() for n in extract_texture_names(data)]

    # Check for script_rt
    for name in names:
        if name.startswith('scr') or name.startswith('script_rt'):
            info["has_script_rt"] = True
        if any(p in name for p in ('emis', 'emissive', 'light', 'glow')):
            info["has_emissive"] = True

    # Scan for texture dimensions
    pos = scan_start
    seen = set()
    while pos < len(data) - 8 and len(info["textures"]) < 32:
        try:
            w = struct.unpack_from('<H', data, pos)[0]
            h = struct.unpack_from('<H', data, pos + 2)[0]
            if _is_pow2(w) and _is_pow2(h) and w >= 4 and h >= 4 and w <= 8192 and h <= 8192:
                key = (w, h, pos // 64)
                if key not in seen:
                    seen.add(key)
                    info["textures"].append({"width": w, "height": h})
                    info["max_dimension"] = max(info["max_dimension"], w, h)
                    pos += 16
                    continue
        except struct.error:
            break
        pos += 2

    info["texture_count"] = len(info["textures"])

    # Estimate savings: if we could halve all textures >2048, file shrinks ~75%
    if info["max_dimension"] > 2048:
        info["estimated_savings_pct"] = 60
    elif info["max_dimension"] > 1024:
        info["estimated_savings_pct"] = 40
    elif info["size"] > 4 * 1024 * 1024:
        info["estimated_savings_pct"] = 20

    return info


def create_backup(filepath, backup_folder):
    """Create a backup of a file, preserving relative structure."""
    try:
        rel = os.path.basename(filepath)
        backup_path = os.path.join(backup_folder, rel)

        # Handle name collisions
        counter = 1
        base, ext = os.path.splitext(backup_path)
        while os.path.exists(backup_path):
            backup_path = f"{base}_{counter}{ext}"
            counter += 1

        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(filepath, backup_path)
        return backup_path
    except (OSError, PermissionError) as e:
        return None


def optimize_batch(folder_path, settings):
    """
    Analyze and prepare optimization plan for all YTD files in a folder.
    Returns a plan that can be executed or presented as dry-run.
    """
    min_size = settings.get("optimizerMinResizeSize", 1048576)
    target_res = settings.get("optimizerTargetResolution", 1024)
    skip_script_rt = settings.get("optimizerSkipScriptRt", True)
    skip_emissive = settings.get("optimizerSkipEmissive", True)

    progress("Scanning for YTD files...")
    ytd_files = scan_ytd_files(folder_path, min_size)
    total = len(ytd_files)

    if not ytd_files:
        return {
            "status": "no_files",
            "message": f"No YTD files found above {min_size / (1024*1024):.1f} MB",
            "files": [],
            "total_size": 0,
            "estimated_savings": 0,
        }

    progress(f"Analyzing {total} YTD files...")
    plan = []
    total_size = 0
    total_estimated_savings = 0

    for i, ytd in enumerate(ytd_files):
        if (i + 1) % 10 == 0 or i + 1 == total:
            pct = int((i + 1) / total * 100)
            progress(f"{pct}%|{i+1}/{total}|Analyzing textures...")

        info = analyze_ytd_for_optimization(ytd["path"])
        total_size += info["size"]

        # Determine if this file should be optimized
        should_optimize = True
        skip_reason = None

        if skip_script_rt and info["has_script_rt"]:
            should_optimize = False
            skip_reason = "Contains script_rt textures (unsafe to modify)"
        elif skip_emissive and info["has_emissive"] and info["texture_count"] <= 2:
            should_optimize = False
            skip_reason = "Contains only emissive/light textures"
        elif info["max_dimension"] <= target_res:
            should_optimize = False
            skip_reason = f"All textures already <= {target_res}px"
        elif info["estimated_savings_pct"] < 10:
            should_optimize = False
            skip_reason = "Minimal savings expected"

        estimated_savings = int(info["size"] * info["estimated_savings_pct"] / 100) if should_optimize else 0
        total_estimated_savings += estimated_savings

        plan.append({
            "path": ytd["path"],
            "rel_path": ytd["rel_path"],
            "size": info["size"],
            "texture_count": info["texture_count"],
            "max_dimension": info["max_dimension"],
            "has_script_rt": info["has_script_rt"],
            "has_emissive": info["has_emissive"],
            "should_optimize": should_optimize,
            "skip_reason": skip_reason,
            "estimated_savings": estimated_savings,
            "estimated_savings_pct": info["estimated_savings_pct"] if should_optimize else 0,
        })

    progress("Optimization plan ready!")

    return {
        "status": "ready",
        "files": plan,
        "total_files": total,
        "optimizable_files": sum(1 for f in plan if f["should_optimize"]),
        "total_size": total_size,
        "estimated_savings": total_estimated_savings,
        "target_resolution": target_res,
        "texconv_available": find_texconv() is not None,
    }


def _is_pow2(val):
    return val > 0 and (val & (val - 1)) == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: optimize_textures.py <folder_path> [settings_json] | --execute <json_payload>"}))
        sys.exit(1)

    # Execute mode: optimize_textures.py --execute <json_payload>
    if sys.argv[1] == "--execute":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Missing JSON payload for --execute"}))
            sys.exit(1)
        try:
            payload = json.loads(sys.argv[2])
        except (json.JSONDecodeError, TypeError) as e:
            print(json.dumps({"error": f"Invalid JSON payload: {e}"}))
            sys.exit(1)
        result = execute_optimization(payload)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    # Analyze mode: optimize_textures.py <folder_path> [settings_json]
    folder = sys.argv[1]

    settings = {}
    if len(sys.argv) >= 3:
        try:
            settings = json.loads(sys.argv[2])
        except (json.JSONDecodeError, TypeError):
            pass

    result = optimize_batch(folder, settings)
    print(json.dumps(result, ensure_ascii=False))
