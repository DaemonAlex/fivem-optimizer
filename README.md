# FiveM Optimizer

Shrinks FiveM / GTA V texture dictionaries (`.ytd`) so the game allocates less memory for them, and reports
the real in-game memory cost of stream files instead of their size on disk.

Two ways to use it:

- **`ytdshrink` on the server** (Linux, Python 3.10+, ImageMagick). No clicking: point it at a folder, read the
  table, add `--apply`. This is the recommended way.
- **The desktop app** (Windows, Electron) for scanning a folder on a PC. Same Python engine underneath.

A web front end that runs on the server is the planned next step; the engine in `python/` is the shared core.

## Why disk size lies

Stream files are RSC7 containers: a 16-byte header plus a compressed stream. The game never looks at the file size.
It allocates what the header's two flag words say and inflates the file into that memory. A 9.9 MB `.ytd` on disk
can be 86 MiB in the game. That header number is what FXServer prints at boot:

    Asset dpsveh-race/fer49p2025.ytd uses 86.0 MiB of physical memory.

Everything this tool reports is that number, read from the header. After shrinking, the boot line drops to match.

## How shrinking works

1. The container is inflated and the texture dictionary parsed: every texture's name, size, format, mip count and
   pixel data.
2. A texture whose longest side is over the target (default 1024 px) loses its top mip levels. The smaller level is
   already in the file, so this is exact and keeps the same compression.
3. A texture that shipped **without** a mip chain has nothing to promote. It is exported, resampled by a converter
   (ImageMagick on Linux/macOS, texconv on Windows) into a full mip chain in the same compression family, and imported.
   Without a converter it is left alone and the report says so.
4. Pixel data is repacked into RSC7 memory pages (a texture never straddles a page), each record's size word is
   updated, the header flags are recomputed, and the file is rewritten and re-read to verify.

5. 32-bit uncompressed textures (A8R8G8B8 and friends, 4 bytes per pixel) are re-encoded as DXT5 or DXT1 with a
   full mip chain even when they are already small enough. A 4096-square uncompressed sign is 64 MiB; as DXT5 with
   mips at 1024 it is 1.3 MiB. `--keep-uncompressed` turns this off.

Rules: a backup folder is required; `script_rt` and emissive/glow textures are never resized; nothing is ever
upscaled; FXAP-encrypted (escrow) files are reported as unreadable, never guessed at; empty dictionaries are fine.

## Server tool: ytdshrink

### Install (Debian/Ubuntu)

    sudo apt install python3 imagemagick
    git clone https://github.com/DaemonAlex/fivem-optimizer
    sudo cp -r fivem-optimizer/python /opt/fivem/tools/ytdshrink

Check the converter is visible: `magick -version`. Without it, textures that have no mipmaps stay as they are.

### Use

    # dry run: nothing is written
    python3 /opt/fivem/tools/ytdshrink/ytdshrink.py "/opt/fivem/server-data/resources/[vehicles]/[race]/dpsveh-race/stream"

    file                                     textures  max px  now MiB   after  note
    ----------------------------------------------------------------------------------------------------
    fer49p2025.ytd                                 51    4096     86.0    33.0  11 oversized
    formula.ytd                                    11     512      0.5       -  All textures already 1024px or smaller
    ----------------------------------------------------------------------------------------------------
    TOTAL                                                         86.5    33.5  converter: magick

    DRY RUN. Add --apply --backup DIR to write. 1 file(s) would change.

    # apply: originals are copied to the backup folder first, then each file is rewritten and verified
    sudo python3 /opt/fivem/tools/ytdshrink/ytdshrink.py <folder> --apply --backup /opt/fivem/backups/ytdshrink-$(date +%Y%m%d)

Options:

| flag | meaning |
|------|---------|
| `--max N` | longest side allowed in pixels (default 1024) |
| `--only a,b` | only files whose name contains one of these fragments |
| `--apply` | write changes (needs `--backup`) |
| `--backup DIR` | where originals and `fivem-optimizer-log.txt` go; relative paths are kept |
| `--keep-emissive` | also shrink emissive/glow textures |
| `--keep-uncompressed` | leave 32-bit uncompressed textures as they are |
| `--json` | machine-readable output |

After applying, restart the server and read the boot log: the `uses N MiB` line for each file should show the new
number. The log in the backup folder lists every texture that changed, with before/after size, format and mip count,
and every one that was kept, with the reason.

### Put a file back

Copy it from the backup folder over the live file and restart. The backup keeps the resource's relative path.

## Desktop app (Windows)

Download the installer from Releases. Python and texconv are bundled.

- **Analyze**: scans a folder and lists issues per file. For `.ytd` files the texture list, formats, mip counts and
  in-game memory are real; a file over the memory threshold (Settings, default 32 MiB) is flagged critical.
- **Textures tab**: lists every `.ytd` with memory now, memory after, and why a file would be skipped. Set a backup
  folder, select files, Optimize. The result shows one line per file: optimized (with before/after memory), unchanged
  (with the reason) or failed (with the error), plus the path of the log.
- Model, collision and map analyzers (`.yft`, `.ydr`, `.ybn`, `.ymap`, `.ytyp`) still use heuristics on partially
  read data; treat their numbers as rough hints.

### Development

    npm install
    npm run download-python      # Python embeddable for the installer
    npm run download-texconv     # texconv.exe into python/tools/
    npm run dev                  # renderer + Electron
    npm run build                # installer

### Tests

    FIVEM_OPTIMIZER_FIXTURES=/path/to/fixtures python3 -m pytest python/tests -q

The fixture folder needs a real vehicle `.ytd` named `fer49p2025.ytd` and a small stock one named `formula.ytd`
(see `python/tests/README.md`). Tests that need fixtures skip when the variable is unset. 51 tests cover the RSC7
container maths, page packing, texture parsing, mip dropping, resampling, the optimizer entry point, the analyzer
and the command-line tool.

## Project layout

    python/
      rsc7.py               RSC7 container: header flags <-> bytes, page layout, inflate/deflate
      ytd.py                texture dictionary: parse records, shrink, serialize
      dds.py                DDS in/out for the converter
      converter.py          ImageMagick / texconv driver
      optimize_textures.py  plan + execute (used by the app and by ytdshrink)
      ytdshrink.py          command-line tool
      analyze.py            folder scan for the app
      analyzers/            per-type analyzers (ytd_analyzer is header-accurate; the rest are heuristics)
      tests/                pytest suite
    src/main/main.js        Electron main process
    src/renderer/           React UI
    scripts/                download-python.js, download-texconv.js

## License

MIT
