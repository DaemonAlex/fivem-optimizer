"""
External resampler for textures that have no mip chain to promote.

Dropping mip levels is exact and free, but a texture shipped with a single level has nothing to
promote. For those we export mip 0 as DDS, ask a converter to resize it and build a full mip chain
in the same compression family, and import the result:

    texconv.exe  (Microsoft DirectXTex, Windows)  - bundled with the app or on PATH
    magick       (ImageMagick 7, any platform)    - on PATH

Nothing here touches the game files; callers get bytes back.
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile

import dds
import ytd

_TEXCONV_FORMAT = {"DXT1": "BC1_UNORM", "DXT3": "BC2_UNORM", "DXT5": "BC3_UNORM", "ATI1": "BC4_UNORM", "ATI2": "BC5_UNORM"}
_MAGICK_COMPRESSION = {"DXT1": "dxt1", "DXT3": "dxt5", "DXT5": "dxt5"}   # ImageMagick cannot write DXT3/ATI1/ATI2


class Unsupported(ValueError):
    """The converter cannot produce this format."""


def fit(width, height, target):
    """Largest size with max side <= target, aspect kept, snapped down to a multiple of 4 (min 4)."""
    scale = target / max(width, height)
    return (max(4, int(width * scale) // 4 * 4), max(4, int(height * scale) // 4 * 4))


def mip_count(width, height):
    return int(math.floor(math.log2(max(width, height)))) + 1


class Converter:
    def __init__(self, name, exe):
        self.name = name
        self.exe = exe

    def supports(self, fmt):
        return fmt in (_TEXCONV_FORMAT if self.name == "texconv" else _MAGICK_COMPRESSION)

    def command(self, in_path, out_dir, width, height, fmt, levels):
        """argv that turns in_path into a full mip chain of width x height in `fmt` inside out_dir."""
        if not self.supports(fmt):
            raise Unsupported(f"{self.name} cannot write {fmt}")
        if self.name == "texconv":
            return [self.exe, "-nologo", "-y", "-f", _TEXCONV_FORMAT[fmt], "-w", str(width), "-h", str(height),
                    "-m", str(levels), "-o", out_dir, in_path]
        # ImageMagick only builds mip chains for power-of-two sizes, so ask for one file per level
        # in a single invocation (one decode of the source). Levels under 4 px are one 4x4 block.
        argv = [self.exe, in_path, "-define", f"dds:compression={_MAGICK_COMPRESSION[fmt]}", "-define", "dds:mipmaps=0"]
        for i in range(levels):
            lw, lh = max(4, width >> i), max(4, height >> i)
            argv += ["(", "+clone", "-resize", f"{lw}x{lh}!", "-write", os.path.join(out_dir, f"level{i}.dds"), "+delete", ")"]
        return argv + ["null:"]

    def resize(self, mip0, width, height, fmt, target):
        """-> (new width, new height, levels, full mip chain bytes, output format) in the same format family."""
        new_w, new_h = fit(width, height, target)
        levels = mip_count(new_w, new_h)
        with tempfile.TemporaryDirectory(prefix="fivem-opt-") as tmp:
            in_path = os.path.join(tmp, "in.dds")
            with open(in_path, "wb") as fh:
                fh.write(dds.write(width, height, fmt, 1, mip0))
            out_dir = os.path.join(tmp, "out")
            os.makedirs(out_dir)
            run = subprocess.run(self.command(in_path, out_dir, new_w, new_h, fmt, levels),
                                 capture_output=True, text=True, timeout=900)
            if run.returncode != 0:
                raise RuntimeError(f"{self.name} failed: {(run.stderr or run.stdout).strip()[:300]}")
            if self.name == "texconv":
                with open(os.path.join(out_dir, "in.dds"), "rb") as fh:
                    got_w, got_h, got_fmt, got_levels, data = dds.read(fh.read())
                if (got_w, got_h, got_levels) != (new_w, new_h, levels):
                    raise RuntimeError(f"{self.name} returned {got_w}x{got_h} x{got_levels}, wanted {new_w}x{new_h} x{levels}")
            else:
                chain, got_fmt = bytearray(), None
                for i in range(levels):
                    with open(os.path.join(out_dir, f"level{i}.dds"), "rb") as fh:
                        got_w, got_h, got_fmt, _, data = dds.read(fh.read())
                    lw, lh = max(1, new_w >> i), max(1, new_h >> i)
                    need = ytd.mip_size(lw, lh, got_fmt)
                    if (got_w, got_h) != (max(4, lw), max(4, lh)) or len(data) < need:
                        raise RuntimeError(f"{self.name} level {i}: got {got_w}x{got_h} {len(data)} bytes, need {need}")
                    chain += data[:need]
                data = bytes(chain)
        out_fmt = got_fmt
        if out_fmt != fmt and not (fmt == "DXT3" and out_fmt == "DXT5"):
            raise RuntimeError(f"{self.name} changed the format from {fmt} to {out_fmt}")
        need = ytd.chain_size(new_w, new_h, out_fmt, levels)
        if len(data) < need:
            raise RuntimeError(f"{self.name} returned {len(data)} bytes, mip chain needs {need}")
        return new_w, new_h, levels, bytes(data[:need]), out_fmt


def find(extra_dirs=()):
    """texconv.exe (bundled or on PATH) on Windows, else ImageMagick's magick on PATH."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(d, "texconv.exe") for d in (*extra_dirs, os.path.join(here, "tools"), os.path.join(here, "..", "tools"))]
    for path in candidates:
        if os.path.isfile(path):
            return Converter("texconv", os.path.abspath(path))
    if sys.platform.startswith("win"):
        exe = shutil.which("texconv") or shutil.which("texconv.exe")
        if exe:
            return Converter("texconv", exe)
    exe = shutil.which("magick")
    if exe:
        return Converter("magick", exe)
    return None
