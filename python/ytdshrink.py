#!/usr/bin/env python3
"""
ytdshrink - shrink GTA V / FiveM texture dictionaries (.ytd) from the command line.

    ytdshrink.py <folder-or-file> [more paths...] [--max 1024] [--only name,name] [--apply --backup DIR] [--json]

Without --apply nothing is written: you get a table of every .ytd found, the memory the game
allocates for it now, and what it would allocate after shrinking. With --apply each file is copied
to the backup folder first (relative path kept), rewritten, re-read to verify, and a line is added
to <backup>/fivem-optimizer-log.txt.

Numbers are in MiB of in-game memory, read from the RSC7 header (the same figure FXServer prints
in its "uses N MiB of physical memory" boot warnings), never the size on disk.

Textures over --max lose their top mip levels (exact, same compression). Textures with no mip
chain are resampled through ImageMagick (magick) or texconv when one is installed; otherwise
they are left alone and listed under "needs converter".
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimize_textures as engine

MIB = 1024 * 1024


def collect(paths, only):
    files = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            files.append((p, os.path.basename(p), os.path.getsize(p)))
        elif os.path.isdir(p):
            base = os.path.dirname(p) if len(paths) > 1 else p
            files += [(a, os.path.relpath(a, base), s) for a, r, s in engine.scan_ytd_files(p)]
        else:
            print(f"not found: {p}", file=sys.stderr)
    if only:
        wants = [w.strip().lower() for w in only.split(",") if w.strip()]
        files = [f for f in files if any(w in f[1].lower() for w in wants)]
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="folders (searched recursively) or .ytd files")
    ap.add_argument("--max", type=int, default=1024, help="longest side allowed, in pixels (default 1024)")
    ap.add_argument("--only", default=None, help="comma-separated name fragments to limit which files are touched")
    ap.add_argument("--apply", action="store_true", help="rewrite files (requires --backup)")
    ap.add_argument("--backup", default=None, help="folder that receives the originals and the log")
    ap.add_argument("--keep-emissive", action="store_true", help="also shrink emissive/glow textures")
    ap.add_argument("--keep-uncompressed", action="store_true", help="leave 32-bit uncompressed textures as they are (default: re-encode as DXT)")
    ap.add_argument("--json", action="store_true", help="print the plan/result as JSON instead of a table")
    args = ap.parse_args(argv)

    if args.apply and not args.backup:
        print("--apply needs --backup DIR: originals are always copied before a file is changed", file=sys.stderr)
        return 2

    settings = {"optimizerTargetResolution": args.max, "optimizerSkipEmissive": not args.keep_emissive,
                "optimizerRecompress": not args.keep_uncompressed}
    skip = engine.skip_rule(settings)
    conv = engine.converter_mod.find()
    files = collect(args.paths, args.only)
    if not files:
        print("no .ytd files found")
        return 1

    plan = [engine.plan_file(path, rel, disk, args.max, skip, conv, not args.keep_uncompressed) for path, rel, disk in files]

    if not args.apply:
        if args.json:
            print(json.dumps({"status": "ready", "files": plan, "converter": conv.name if conv else None,
                              "target_resolution": args.max}, ensure_ascii=False))
            return 0
        print(f"{'file':<40}{'textures':>9}{'max px':>8}{'now MiB':>9}{'after':>8}  note")
        print("-" * 100)
        before = after = 0.0
        for f in plan:
            before += f["memory_mib"]
            after += f["memory_after_mib"] if f["memory_after_mib"] is not None else f["memory_mib"]
            note = f["skip_reason"] or ""
            if f["should_optimize"]:
                rc = sum(1 for t in f["oversized"] if t.get("method") == "recompress")
                note = f"{len(f['oversized']) - rc} oversized" + (f", {rc} uncompressed" if rc else "") + (f", {f['needs_converter']} need converter" if f["needs_converter"] else "")
            aft = f"{f['memory_after_mib']:.1f}" if f["memory_after_mib"] is not None else "-"
            print(f"{f['rel_path'][-40:]:<40}{f['texture_count']:>9}{f['max_dimension']:>8}{f['memory_mib']:>9.1f}{aft:>8}  {note}")
        print("-" * 100)
        print(f"{'TOTAL':<40}{'':>9}{'':>8}{before:>9.1f}{after:>8.1f}  converter: {conv.name if conv else 'none'}")
        print(f"\nDRY RUN. Add --apply --backup DIR to write. {sum(1 for f in plan if f['should_optimize'])} file(s) would change.")
        return 0

    todo = [f for f in plan if f["should_optimize"]]
    unchanged = [f for f in plan if not f["should_optimize"]]
    result = {"status": "no_files", "results": [], "message": "nothing to do"}
    if todo:
        folder = os.path.commonpath([os.path.dirname(f["path"]) for f in todo])
        payload = {"folder_path": folder, "selected_files": [os.path.relpath(f["path"], folder) for f in todo],
                   "backup_folder": args.backup, "target_resolution": args.max, "settings": settings}
        result = engine.execute_optimization(payload)
    if args.json:
        result["unchanged"] = unchanged
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("files_failed", 0) == 0 else 1
    for r in result["results"]:
        print(f"{r['status']:<10}{r['file'][-50:]:<50}  {r['reason']}")
    for f in unchanged:
        print(f"{'unchanged':<10}{f['rel_path'][-50:]:<50}  {f['skip_reason']}")
    if result.get("message"):
        print("\n" + result["message"])
    return 0 if result.get("files_failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
