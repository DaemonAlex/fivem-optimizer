# FiveM Optimizer

Windows desktop tool that scans FiveM streaming folders to identify and fix optimization issues in game assets (`.ytd`, `.yft`, `.ydr`, `.ybn`, `.ymap`, `.ytyp`).

<img width="1194" height="793" alt="{A651BFAC-B1A2-44BB-94D7-080D2CF38D37}" src="https://github.com/user-attachments/assets/801f3e64-57fa-41a5-9ef4-61225370b2e6" />

![Electron](https://img.shields.io/badge/Electron-28-blue) ![React](https://img.shields.io/badge/React-18-blue) ![Python](https://img.shields.io/badge/Python-3.10+-green) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

## Features

- **Texture Analysis** — Detects oversized textures, missing mipmaps, incorrect compression, NPOT dimensions, and estimates VRAM usage
- **Texture Optimization** — In-place mipmap replacement to downsize textures without external tools (backups always created)
- **Model Analysis** — Poly count checks, bone limits, and LOD validation for `.yft` (vehicles) and `.ydr` (props)
- **Collision Analysis** — Polygon complexity and bounding box checks for `.ybn` files
- **Map/Archetype Analysis** — Entity counts and streaming extent validation for `.ymap` and `.ytyp`
- **Duplicate Detection** — SHA256-based duplicate finder with one-click removal
- **Memory Footprint** — Total file size and per-texture VRAM estimation
- **Dependency Mapping** — Cross-references `.ymap`/`.ytyp` against known asset names

## Install

Download the latest installer from [Releases](../../releases). Python is bundled — no extra setup needed.

## Development

```bash
# Install dependencies
npm install

# Download bundled Python (required for builds)
npm run download-python

# Start dev server
npm run dev

# Production build (builds renderer + installer)
npm run build
```

### Requirements

- Node.js 18+
- Python 3.10+ (bundled in production builds, or install locally for dev)

## Project Structure

```
src/
  main/main.js           # Electron main process, IPC, Python spawning
  preload/preload.js      # Secure IPC bridge (contextIsolation)
  renderer/               # React app (Vite)
    components/           # UI components
    styles.css            # Dark theme, CSS variables
python/
  analyze.py              # Main analysis entry point
  optimize_textures.py    # Texture optimization engine
  analyzers/              # Per-type analyzers (ytd, yft, ydr, ybn, ymap, ytyp)
scripts/
  download-python.js      # Downloads Python embeddable for bundling
  generate-icon.js        # Generates app icon
assets/                   # App icons
.github/workflows/        # CI/CD (build + publish on tag)
```

## Releasing

```bash
npm version patch   # or minor / major
git push && git push --tags
```

GitHub Actions builds the installer and publishes to Releases automatically. The app checks for updates on startup via `electron-updater`.

## License

MIT
