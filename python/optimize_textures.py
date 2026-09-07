"""
FiveM texture optimizer - the engine behind the Textures tab.

    python optimize_textures.py <folder> <settings_json>      plan: what each .ytd holds and what shrinking would save
    python optimize_textures.py --execute <payload_json>       rewrite the selected files (backup first, always)

How a .ytd is shrunk
    1. The RSC7 container is inflated and the texture dictionary parsed (rsc7.py, ytd.py).
    2. Every texture whose longest side is over the target loses its top mip levels: the smaller
       level already exists in the file, so this is exact and keeps the same compression.
    3. A texture that ships without a mip chain is resampled by an external converter (texconv on
       Windows, ImageMagick elsewhere) into a full chain. Without a converter it is left alone and
       the report says so.
    4. Pixel data is repacked into RSC7 memory pages, the header flags are recomputed, and the file
       is rewritten. The "memory" numbers reported are the bytes the game will allocate, read back
       from the header flags - the same number FXServer prints in its boot warnings.

Rules
    * A backup folder is required. The original is copied there (with its relative path) before
      the file is touched.
    * script_rt textures and emissive/glow textures are never resized (settings can relax this).
    * FXAP-encrypted (escrow) files cannot be opened and are reported as such.
    * Nothing is ever upscaled.
"""
import json
import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import converter as converter_mod
import rsc7
import ytd

MIB = 1024 * 1024
SCRIPT_RT_PREFIXES = ("script_rt", "scr_")
EMISSIVE_MARKS = ("emis", "emissive", "glow", "neon")


def progress(msg):
    print(f"PROGRESS:{msg}", flush=True)


def is_script_rt(name):
    return name.lower().startswith(SCRIPT_RT_PREFIXES)


def is_emissive(name):
    n = name.lower()
    return any(m in n for m in EMISSIVE_MARKS) or n.endswith("_em")


def skip_rule(settings):
    skip_rt = settings.get("optimizerSkipScriptRt", True)
    skip_em = settings.get("optimizerSkipEmissive", True)

    def skip(t):
        return (skip_rt and is_script_rt(t.name)) or (skip_em and is_emissive(t.name))
    return skip


def scan_ytd_files(folder):
    found = []
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if name.lower().endswith(".ytd"):
                path = os.path.join(root, name)
                try:
                    found.append((path, os.path.relpath(path, folder), os.path.getsize(path)))
                except OSError:
                    pass
    found.sort(key=lambda f: -f[2])
    return found


def projected_sizes(d, target, skip, have_converter):
    """Per-texture data sizes after a shrink, without touching pixels. Returns (sizes, plan rows)."""
    sizes, rows = [], []
    for t in d.textures:
        size = t.chain_size()
        longest = max(t.width, t.height)
        row = {"name": t.name, "size": f"{t.width}x{t.height}", "format": t.format, "mipmaps": t.levels}
        if longest > target and not skip(t) and t.known_format:
            drop, w, h = 0, t.width, t.height
            while max(w, h) > target and drop < t.levels - 1:
                w, h, drop = max(1, w >> 1), max(1, h >> 1), drop + 1
            if max(w, h) <= target:
                size = ytd.chain_size(w, h, t.format_code, t.levels - drop)
                row.update(method="mipdrop", to=f"{w}x{h}")
            elif have_converter and t.format in converter_mod._TEXCONV_FORMAT:
                nw, nh = converter_mod.fit(t.width, t.height, target)
                size = ytd.chain_size(nw, nh, t.format_code, converter_mod.mip_count(nw, nh))
                row.update(method="resample", to=f"{nw}x{nh}")
            else:
                row.update(method="needs converter", to=None)
        elif longest > target:
            row.update(method="kept", to=None, why="script_rt" if is_script_rt(t.name) else "emissive" if is_emissive(t.name) else t.format)
        sizes.append(size)
        rows.append(row)
    return sizes, rows


def plan_file(path, rel, disk_size, target, skip, conv):
    entry = {"path": path, "rel_path": rel, "disk_size": disk_size, "size": 0, "memory_mib": 0.0, "memory_after_mib": None,
             "texture_count": 0, "max_dimension": 0, "has_script_rt": False, "has_emissive": False,
             "should_optimize": False, "skip_reason": None, "estimated_savings": 0, "estimated_savings_pct": 0,
             "oversized": [], "needs_converter": 0, "error": None}
    try:
        r = rsc7.read_virtual(path)
        d = ytd.parse(r.virtual)
    except rsc7.NotRsc7 as e:
        entry["skip_reason"] = "FXAP-encrypted (FiveM escrow): the file cannot be opened" if "FXAP" in str(e) else f"Not a readable RSC7 file: {e}"
        entry["error"] = str(e)
        return entry
    except Exception as e:
        entry["skip_reason"] = f"Could not parse the texture dictionary: {type(e).__name__}: {e}"
        entry["error"] = traceback.format_exc()
        return entry
    entry["size"] = r.physical_size
    entry["memory_mib"] = round(r.physical_size / MIB, 1)
    entry["texture_count"] = len(d.textures)
    entry["max_dimension"] = max((max(t.width, t.height) for t in d.textures), default=0)
    entry["has_script_rt"] = any(is_script_rt(t.name) for t in d.textures)
    entry["has_emissive"] = any(is_emissive(t.name) for t in d.textures)
    sizes, rows = projected_sizes(d, target, skip, conv is not None)
    entry["oversized"] = [row for row in rows if max(map(int, row["size"].split("x"))) > target]
    entry["oversized"].sort(key=lambda row: -max(map(int, row["size"].split("x"))))
    entry["needs_converter"] = sum(1 for row in rows if row.get("method") == "needs converter")
    doable = sum(1 for row in rows if row.get("method") in ("mipdrop", "resample"))
    if doable:
        flags, _ = rsc7.pack(sizes, align=ytd.DATA_ALIGN)
        after = rsc7.flags_to_size(flags)
        entry["memory_after_mib"] = round(after / MIB, 1)
        entry["estimated_savings"] = max(0, r.physical_size - after)
        entry["estimated_savings_pct"] = round(entry["estimated_savings"] / r.physical_size * 100) if r.physical_size else 0
        entry["should_optimize"] = entry["estimated_savings"] > 0
        if not entry["should_optimize"]:
            entry["skip_reason"] = "Shrinking would not reduce the memory the game allocates"
    elif not entry["oversized"]:
        entry["skip_reason"] = f"All textures already {target}px or smaller"
    elif entry["needs_converter"]:
        entry["skip_reason"] = (f"{entry['needs_converter']} oversized texture(s) have no mipmaps; resizing them needs a converter "
                                f"(texconv.exe in the app's tools folder, or ImageMagick on PATH)")
    else:
        kept = ", ".join(row["name"] for row in rows if row.get("method") == "kept")
        entry["skip_reason"] = f"Oversized textures are protected by the skip rules ({kept})"
    return entry


def optimize_batch(folder, settings):
    target = int(settings.get("optimizerTargetResolution", 1024))
    skip = skip_rule(settings)
    conv = converter_mod.find()
    progress("Scanning for .ytd files...")
    files = scan_ytd_files(folder)
    if not files:
        return {"status": "no_files", "message": "No .ytd files found in this folder", "files": [], "total_files": 0,
                "optimizable_files": 0, "total_size": 0, "estimated_savings": 0, "target_resolution": target,
                "converter": conv.name if conv else None, "texconv_available": conv is not None}
    plan = []
    for i, (path, rel, disk) in enumerate(files):
        progress(f"{int((i + 1) / len(files) * 100)}%|{i + 1}/{len(files)}|Reading {os.path.basename(path)}")
        plan.append(plan_file(path, rel, disk, target, skip, conv))
    progress("Plan ready")
    return {
        "status": "ready",
        "files": plan,
        "total_files": len(plan),
        "optimizable_files": sum(1 for f in plan if f["should_optimize"]),
        "total_size": sum(f["size"] for f in plan),
        "estimated_savings": sum(f["estimated_savings"] for f in plan),
        "target_resolution": target,
        "converter": conv.name if conv else None,
        "converter_note": (f"Textures without mipmaps will be resampled with {conv.name}" if conv else
                           "No converter found: textures without mipmaps will be left as they are "
                           "(put texconv.exe in the app's tools folder, or install ImageMagick)"),
        "texconv_available": conv is not None,
    }


def backup_file(abs_path, rel_path, backup_dir):
    dest = os.path.join(backup_dir, rel_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        base, ext = os.path.splitext(dest)
        dest = f"{base}.{stamp}{ext}"
    shutil.copy2(abs_path, dest)
    return dest


def optimize_file(abs_path, target, skip, conv):
    """Shrink one .ytd in place. Returns (memory_before, memory_after, report)."""
    r = rsc7.read(abs_path)
    d = ytd.parse(r.virtual, r.physical)
    report = ytd.shrink(d, target, skip=skip, converter=conv)
    if report["resized"] == 0:
        return r.physical_size, r.physical_size, report
    virtual, physical, pflags = ytd.serialize(d)
    tmp = abs_path + ".fivem-optimizer.tmp"
    rsc7.write(tmp, r.version, virtual, physical, virtual_flags=r.virtual_flags, physical_flags=pflags)
    check = rsc7.read(tmp)
    d2 = ytd.parse(check.virtual, check.physical)
    if [t.name for t in d2.textures] != [t.name for t in d.textures]:
        os.remove(tmp)
        raise RuntimeError("verification failed: the rewritten file does not list the same textures")
    os.replace(tmp, abs_path)
    return r.physical_size, check.physical_size, report


def execute_optimization(payload):
    folder = os.path.normpath(payload["folder_path"])
    selected = payload.get("selected_files") or []
    backup_dir = payload.get("backup_folder")
    target = int(payload.get("target_resolution", 1024))
    settings = payload.get("settings") or {}
    skip = skip_rule(settings)
    conv = converter_mod.find()

    out = {"status": "completed", "files_processed": 0, "files_succeeded": 0, "files_failed": 0, "files_skipped": 0,
           "total_original_size": 0, "memory_before_mib": 0.0, "memory_after_mib": 0.0, "errors": [], "results": [],
           "converter": conv.name if conv else None, "log_path": None, "message": None}
    if not selected:
        out["status"] = "no_files"
        out["message"] = "No files were selected"
        return out
    if not backup_dir:
        out["status"] = "no_backup"
        out["message"] = "A backup folder is required before any file is changed"
        return out
    os.makedirs(backup_dir, exist_ok=True)
    log_path = os.path.join(backup_dir, "fivem-optimizer-log.txt")
    out["log_path"] = log_path
    log = open(log_path, "a", encoding="utf-8")
    log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')}  folder={folder}  target={target}px  converter={conv.name if conv else 'none'}\n")

    def line(msg):
        log.write(msg + "\n")
        log.flush()

    total = len(selected)
    for i, rel in enumerate(selected):
        progress(f"{int((i + 1) / total * 100)}%|{i + 1}/{total}|Optimizing {os.path.basename(rel)}")
        result = {"file": rel, "status": "failed", "memory_before_mib": None, "memory_after_mib": None,
                  "textures_resized": 0, "textures_skipped": [], "reason": None, "backup": None}
        out["results"].append(result)
        abs_path = os.path.normpath(os.path.join(folder, rel))
        if not abs_path.startswith(folder + os.sep):
            result["reason"] = "Refused: path is outside the scanned folder"
            out["files_failed"] += 1
            out["errors"].append({"file": rel, "error": result["reason"]})
            line(f"FAILED  {rel}: {result['reason']}")
            continue
        out["files_processed"] += 1
        if not os.path.isfile(abs_path):
            result["reason"] = "File not found"
            out["files_failed"] += 1
            out["errors"].append({"file": rel, "error": result["reason"]})
            line(f"FAILED  {rel}: file not found")
            continue
        try:
            out["total_original_size"] += os.path.getsize(abs_path)
            result["backup"] = backup_file(abs_path, rel, backup_dir)
            before, after, report = optimize_file(abs_path, target, skip, conv)
            result["memory_before_mib"] = round(before / MIB, 1)
            result["memory_after_mib"] = round(after / MIB, 1)
            result["textures_resized"] = report["resized"]
            result["textures_skipped"] = [x for x in report["details"] if x.get("reason")]
            out["memory_before_mib"] += result["memory_before_mib"]
            out["memory_after_mib"] += result["memory_after_mib"]
            if report["resized"]:
                result["status"] = "optimized"
                result["reason"] = (f"{report['resized']} texture(s) resized: {result['memory_before_mib']} MiB -> "
                                    f"{result['memory_after_mib']} MiB in game")
                out["files_succeeded"] += 1
            else:
                result["status"] = "skipped"
                why = "; ".join(f"{x['name']}: {x['reason']}" for x in result["textures_skipped"]) or f"nothing over {target}px"
                result["reason"] = f"Unchanged ({why})"
                out["files_skipped"] += 1
            line(f"{result['status'].upper():9s} {rel}: {result['reason']}")
            for x in report["details"]:
                if x.get("reason"):
                    line(f"    kept    {x['name']}: {x['reason']}")
                else:
                    line(f"    {x['method']:<9s}{x['name']}: {x['from']} -> {x['to']} {x['format']} mips {x['levels'][0]}->{x['levels'][1]}")
        except Exception as e:
            result["reason"] = f"{type(e).__name__}: {e}"
            out["files_failed"] += 1
            out["errors"].append({"file": rel, "error": result["reason"]})
            line(f"FAILED  {rel}: {result['reason']}")
            line(traceback.format_exc())
    out["memory_before_mib"] = round(out["memory_before_mib"], 1)
    out["memory_after_mib"] = round(out["memory_after_mib"], 1)
    out["message"] = (f"{out['files_succeeded']} optimized, {out['files_skipped']} unchanged, {out['files_failed']} failed. "
                      f"Memory {out['memory_before_mib']} MiB -> {out['memory_after_mib']} MiB. Log: {log_path}")
    line(out["message"])
    log.close()
    progress("Done")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: optimize_textures.py <folder> [settings_json] | --execute <payload_json>"}))
        sys.exit(1)
    if sys.argv[1] == "--execute":
        try:
            payload = json.loads(sys.argv[2])
        except (IndexError, json.JSONDecodeError) as e:
            print(json.dumps({"error": f"Invalid payload: {e}"}))
            sys.exit(1)
        print(json.dumps(execute_optimization(payload), ensure_ascii=False))
        sys.exit(0)
    settings = {}
    if len(sys.argv) >= 3:
        try:
            settings = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            pass
    print(json.dumps(optimize_batch(sys.argv[1], settings), ensure_ascii=False))
