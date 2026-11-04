#!/usr/bin/env python3
"""
texswap - replace one named texture inside a GTA V / FiveM texture dictionary (.ytd).

    texswap.py <file.ytd> --texture NAME --image FILE [--apply] [--backup DIR] [--json]
    texswap.py <file.ytd> --list

Most vehicle and map mods that ship a re-skin tell you to open the archive in OpenIV and drop a
PNG over one texture by hand. This does the same swap on the server, from the command line, with
no Windows tooling in the loop.

The replacement is held to the texture it replaces: same width, same height, same block format and
the same number of mip levels. The image is encoded to that exact shape through ImageMagick or
texconv (whichever is installed), and anything that does not match is refused rather than written,
because a texture whose mip chain is the wrong length is a crash on a client, not a visual bug.

Without --apply nothing is written: you get the target's dimensions, the format, and what the
encoded replacement came out as. With --apply the file is copied to --backup first (or to
<file>.bak-texswap beside it), rewritten, then re-read and compared texture by texture.

Only .ytd files are handled. Textures embedded in a model (.yft, .ydd) are read by the shrinker
but are not swapped here; their physical segment holds model data as well, so a rewrite needs the
same guard ytdshrink applies before it will touch one.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import converter as converter_mod
import dds
import rsc7
import ytd


class Refused(RuntimeError):
    """The swap would produce a file the game cannot stream."""


def encode(conv, image, width, height, fmt, levels):
    """The image as a mip chain of exactly width x height in `fmt`, `levels` deep."""
    with tempfile.TemporaryDirectory(prefix="texswap-") as tmp:
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir)
        argv = conv.command(image, out_dir, width, height, fmt, levels)
        run = subprocess.run(argv, capture_output=True, text=True, timeout=900)
        if run.returncode != 0:
            raise Refused(f"{conv.name} failed: {(run.stderr or run.stdout).strip()[:300]}")
        if conv.name == "texconv":
            produced = os.path.join(out_dir, os.path.splitext(os.path.basename(image))[0] + ".dds")
            with open(produced, "rb") as fh:
                got_w, got_h, got_fmt, got_levels, data = dds.read(fh.read())
            if (got_w, got_h, got_levels) != (width, height, levels):
                raise Refused(f"texconv returned {got_w}x{got_h} x{got_levels}, wanted {width}x{height} x{levels}")
        else:
            chain, got_fmt = bytearray(), None
            for i in range(levels):
                with open(os.path.join(out_dir, f"level{i}.dds"), "rb") as fh:
                    got_w, got_h, got_fmt, _, level = dds.read(fh.read())
                lw, lh = max(1, width >> i), max(1, height >> i)
                need = ytd.mip_size(lw, lh, got_fmt)
                if (got_w, got_h) != (max(4, lw), max(4, lh)) or len(level) < need:
                    raise Refused(f"{conv.name} level {i}: got {got_w}x{got_h} {len(level)} bytes, need {need}")
                chain += level[:need]
            data = bytes(chain)
    want_fmt = converter_mod.output_format(fmt)
    if got_fmt != want_fmt:
        raise Refused(f"{conv.name} returned {got_fmt}, wanted {want_fmt}")
    need = ytd.chain_size(width, height, got_fmt, levels)
    if len(data) != need:
        raise Refused(f"encoded chain is {len(data)} bytes, the texture holds {need}")
    return data[:need]


def swap(path, texture, image, apply=False, backup=None):
    """Replace `texture` in `path` with `image`. -> report dict."""
    if not path.lower().endswith(".ytd"):
        raise Refused("only .ytd files are handled; a texture inside a model needs ytdshrink's guard")
    r = rsc7.read(path)
    d = ytd.parse(r.virtual, r.physical)
    names = [t.name for t in d.textures]
    hit = [t for t in d.textures if t.name == texture]
    if not hit:
        raise Refused(f"no texture named {texture!r}; this file has: {', '.join(names)}")
    t = hit[0]
    if not t.known_format:
        raise Refused(f"{texture} is format code {t.format_code}, which this tool cannot re-encode")
    conv = converter_mod.find()
    if conv is None:
        raise Refused("no converter found: install imagemagick or texconv")
    data = encode(conv, image, t.width, t.height, t.format, t.levels)
    report = {"file": path, "texture": texture, "image": image, "converter": conv.name,
              "width": t.width, "height": t.height, "format": t.format, "levels": t.levels,
              "bytes": len(data), "applied": False}
    if not apply:
        return report
    dest = None
    if backup:
        os.makedirs(backup, exist_ok=True)
        dest = os.path.join(backup, os.path.basename(path))
    else:
        dest = path + ".bak-texswap"
    shutil.copy2(path, dest)
    report["backup"] = dest
    t.data = data
    virtual, physical, pflags = ytd.serialize(d)
    tmp = path + ".texswap-tmp"
    rsc7.write(tmp, r.version, virtual, physical, virtual_flags=r.virtual_flags, physical_flags=pflags)
    # read the written file back before it replaces anything
    r2 = rsc7.read(tmp)
    d2 = ytd.parse(r2.virtual, r2.physical)
    if [x.name for x in d2.textures] != names:
        os.unlink(tmp)
        raise Refused("rewritten dictionary lost or reordered textures; nothing changed")
    check = [x for x in d2.textures if x.name == texture][0]
    if (check.width, check.height, check.format, check.levels) != (t.width, t.height, t.format, t.levels):
        os.unlink(tmp)
        raise Refused("rewritten texture changed shape; nothing changed")
    if check.data != data:
        os.unlink(tmp)
        raise Refused("rewritten pixels do not match the encoded image; nothing changed")
    os.replace(tmp, path)
    report["applied"] = True
    return report


def main():
    ap = argparse.ArgumentParser(description="Replace one named texture inside a .ytd")
    ap.add_argument("file")
    ap.add_argument("--texture", help="texture name inside the dictionary")
    ap.add_argument("--image", help="replacement image (png, dds, anything the converter reads)")
    ap.add_argument("--list", action="store_true", help="list the textures and exit")
    ap.add_argument("--apply", action="store_true", help="write the file (default is a dry run)")
    ap.add_argument("--backup", help="folder for the untouched original")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.list:
        r = rsc7.read(a.file)
        d = ytd.parse(r.virtual, r.physical)
        rows = [{"name": t.name, "width": t.width, "height": t.height,
                 "format": t.format, "levels": t.levels} for t in d.textures]
        if a.json:
            print(json.dumps(rows, indent=2))
        else:
            for t in rows:
                print(f"  {t['name']:<44s} {t['width']}x{t['height']} {t['format']} x{t['levels']}")
        return 0

    if not a.texture or not a.image:
        ap.error("--texture and --image are required unless --list")
    try:
        report = swap(a.file, a.texture, a.image, apply=a.apply, backup=a.backup)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        verb = "replaced" if report["applied"] else "would replace"
        print(f"{verb} {report['texture']} in {os.path.basename(report['file'])}: "
              f"{report['width']}x{report['height']} {report['format']} x{report['levels']} "
              f"({report['bytes']} bytes via {report['converter']})")
        if report["applied"]:
            print(f"  original kept at {report['backup']}")
        else:
            print("  dry run: pass --apply to write it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
