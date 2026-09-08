#!/usr/bin/env python3
"""
audiomerge - fold one or more FiveM audio resources into a single resource that registers once.

    audiomerge.py <resource-dir> [more resource dirs...] --out <new-resource-dir> --name <shortname>

FiveM stops registering addon audio after roughly 190 banks; anything declared past that is silent.
A resource that declares 84 game-data files, 84 sound-data files and 84 wave packs spends 84 slots.
This tool reads the source fxmanifest.lua, merges every declared AUDIO_GAMEDATA (.dat151.rel),
AUDIO_SOUNDDATA (.dat54.rel) and AUDIO_SYNTHDATA (.dat10.rel) file into one of each, copies every
wave (.awc) into one pack folder, rewrites the wave references to that folder, and writes a manifest
that declares exactly one of each. Result: one resource, three or four registrations.

Nothing in the source is modified. The output folder must not exist yet. A MERGE-REPORT.txt in the
output lists what went in, what was dropped as an exact duplicate, and every conflicting duplicate
(same name, different data - the first source wins, later ones are ignored).
"""
import argparse
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relmerge

KINDS = {  # data_file type -> (rel type, manifest suffix, file suffix)
    "AUDIO_GAMEDATA": (151, "_game.dat", "_game.dat151.rel"),
    "AUDIO_SOUNDDATA": (54, "_sounds.dat", "_sounds.dat54.rel"),
    "AUDIO_SYNTHDATA": (10, "_amp.dat", "_amp.dat10.rel"),
}


def declared(resource):
    """data_file declarations from fxmanifest.lua -> {type: [paths]} (paths as declared)."""
    manifest = os.path.join(resource, "fxmanifest.lua")
    if not os.path.isfile(manifest):
        manifest = os.path.join(resource, "__resource.lua")
    text = open(manifest, errors="replace").read()
    out = {}
    for kind, path in re.findall(r"data_file\s*\(?\s*['\"](AUDIO_\w+)['\"]\s*,?\s*['\"]([^'\"]+)['\"]", text):
        out.setdefault(kind, []).append(path)
    return out


def resolve_rel(resource, declared_path, kind):
    """'audioconfig/x_game.dat' -> real file 'audioconfig/x_game.dat151.rel' (FiveM adds the suffix)."""
    rtype, msuffix, fsuffix = KINDS[kind]
    candidates = [declared_path, declared_path + str(rtype) + ".rel", declared_path + ".rel"]
    if declared_path.endswith(msuffix):
        candidates.insert(0, declared_path[: -len(msuffix)] + fsuffix)
    for c in candidates:
        p = os.path.join(resource, c)
        if os.path.isfile(p):
            return p
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+", help="resource folders holding fxmanifest.lua, audioconfig/, sfx/")
    ap.add_argument("--out", required=True, help="new resource folder to create")
    ap.add_argument("--name", required=True, help="short name: files become <name>_game.dat151.rel etc, waves go to sfx/dlc_<name>/")
    ap.add_argument("--keep-synth", action="store_true", help="do not merge AUDIO_SYNTHDATA (.dat10) files: copy and declare each as shipped")
    ap.add_argument("--drop-synth", action="store_true", help="leave AUDIO_SYNTHDATA (.dat10) files out entirely (the Gabz merge shipped none and plays fine)")
    ap.add_argument("--max-waves-per-pack", type=int, default=120, help="split the waves across dlc_<name>, dlc_<name>2, ... with at most this many files each (default 120)")
    args = ap.parse_args(argv)

    if os.path.exists(args.out):
        print(f"output folder exists: {args.out} (refusing to overwrite)", file=sys.stderr)
        return 2
    name = args.name.lower()
    pack = f"dlc_{name}"
    merged = {}
    reports = {}
    before = {k: 0 for k in KINDS}
    before["AUDIO_WAVEPACK"] = 0
    waves = []          # (src path, wave name)
    wave_names = {}
    problems = []

    kept_synth = []      # (real path, declared path) copied as shipped when --keep-synth
    own_packs = set()    # wave pack folders the sources ship; references to any other pack (RESIDENT etc) are left alone
    for src in args.sources:
        decl = declared(src)
        before["AUDIO_WAVEPACK"] += len(decl.get("AUDIO_WAVEPACK", []))
        for kind, (rtype, _m, _f) in KINDS.items():
            rels = []
            for path in decl.get(kind, []):
                before[kind] += 1
                real = resolve_rel(src, path, kind)
                if not real:
                    problems.append(f"{os.path.basename(src)}: declared {path} but no file found")
                    continue
                if kind == "AUDIO_SYNTHDATA" and args.drop_synth:
                    continue
                if kind == "AUDIO_SYNTHDATA" and args.keep_synth:
                    kept_synth.append((real, path))
                    continue
                rels.append(relmerge.parse(open(real, "rb").read(), os.path.relpath(real, src)))
            if rels:
                merged.setdefault(kind, []).extend(rels)
        for packdir in decl.get("AUDIO_WAVEPACK", []):
            own_packs.add(os.path.basename(packdir.rstrip("/")).lower())
            d = os.path.join(src, packdir)
            if not os.path.isdir(d):
                problems.append(f"{os.path.basename(src)}: wave pack folder {packdir} missing")
                continue
            for f in sorted(os.listdir(d)):
                if f.lower().endswith(".awc"):
                    wname = f[:-4].lower()
                    if wname in wave_names and wave_names[wname] != os.path.join(d, f):
                        problems.append(f"wave name clash: {wname} in {wave_names[wname]} and {os.path.join(d, f)} (second one skipped)")
                        continue
                    wave_names[wname] = os.path.join(d, f)
                    waves.append((os.path.join(d, f), f))

    if not merged:
        print("no audio data files declared in the sources", file=sys.stderr)
        return 1

    # assign every wave to a folder (by sorted wave name, so the split is stable)
    per = max(1, args.max_waves_per_pack)
    wave_folder = {}
    for i, (src, f) in enumerate(sorted(waves, key=lambda x: x[1].lower())):
        wave_folder[f[:-4].lower()] = pack if i // per == 0 else f"{pack}{i // per + 1}"
    folders = sorted(set(wave_folder.values()) or {pack})
    os.makedirs(os.path.join(args.out, "audioconfig"))
    for fo in folders:
        os.makedirs(os.path.join(args.out, "sfx", fo))
    manifest_lines = ["fx_version 'cerulean'", "game 'gta5'", "",
                      f"-- built by audiomerge on {time.strftime('%Y-%m-%d %H:%M')} from: " + ", ".join(os.path.basename(os.path.abspath(s)) for s in args.sources),
                      "-- one registration per data type: FiveM caps addon audio banks at roughly 190", "",
                      "files {"]
    data_lines = []
    for kind, rels in merged.items():
        rtype, msuffix, fsuffix = KINDS[kind]
        rel, report = relmerge.merge(rels, pack_rename=(lambda p, wave: wave_folder.get(wave.lower(), pack) if p in own_packs else None) if rtype == 54 else None)
        out_path = os.path.join(args.out, "audioconfig", name + fsuffix)
        blob = relmerge.write(rel)
        with open(out_path, "wb") as fh:
            fh.write(blob)
        check = relmerge.parse(blob)
        if len(check.index) != len(rel.index):
            problems.append(f"{kind}: verification failed, {len(check.index)} items after re-read, {len(rel.index)} written")
        if not relmerge.index_sorted(check):
            problems.append(f"{kind}: verification failed, index is not in the game's lookup order")
        reports[kind] = report
        manifest_lines.append(f"    'audioconfig/{name}{fsuffix}',")
        data_lines.append(f"data_file '{kind}' 'audioconfig/{name}{msuffix}'")
    for real, path in kept_synth:
        dest = os.path.join(args.out, "audioconfig", os.path.basename(real))
        shutil.copy2(real, dest)
        manifest_lines.append(f"    'audioconfig/{os.path.basename(real)}',")
        data_lines.append(f"data_file 'AUDIO_SYNTHDATA' 'audioconfig/{os.path.basename(path)}'")
    for src, f in waves:
        shutil.copy2(src, os.path.join(args.out, "sfx", wave_folder[f[:-4].lower()], f))
    manifest_lines += [f"    'sfx/{fo}/*.awc'," for fo in folders] + ["}", ""] + data_lines + [f"data_file 'AUDIO_WAVEPACK' 'sfx/{fo}'" for fo in folders] + [""]
    with open(os.path.join(args.out, "fxmanifest.lua"), "w") as fh:
        fh.write("\n".join(manifest_lines))

    after = {k: (1 if k in merged else 0) for k in KINDS}
    if kept_synth:
        after["AUDIO_SYNTHDATA"] = len(kept_synth)
    after["AUDIO_WAVEPACK"] = len(folders) if waves else 0
    lines = [f"audiomerge report - {time.strftime('%Y-%m-%d %H:%M:%S')}", f"sources: {', '.join(args.sources)}", f"output: {args.out}", "",
             "registrations before -> after:"]
    for k in list(KINDS) + ["AUDIO_WAVEPACK"]:
        lines.append(f"  {k:<16} {before[k]:>4} -> {after[k]}")
    lines += ["", f"waves copied: {len(waves)} into {len(folders)} pack folder(s) ({', '.join(folders)}), max {per} per folder", ""]
    for kind, rep in reports.items():
        lines.append(f"{kind}: {rep['sources']} files -> {rep['items']} items, {rep['dropped_identical']} exact duplicates dropped, {len(rep['conflicts'])} conflicts")
        for c in rep["conflicts"]:
            lines.append(f"    conflict {c['hash']:#010x}: kept {c['kept']}, ignored {c['dropped']} (lengths {c['length']})")
    if problems:
        lines += ["", "problems:"] + [f"  {p}" for p in problems]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(args.out, "MERGE-REPORT.txt"), "w") as fh:
        fh.write(text)
    print(text)
    return 1 if any("verification failed" in p for p in problems) else 0


if __name__ == "__main__":
    sys.exit(main())
