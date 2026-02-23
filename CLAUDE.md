# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

FiveM Streaming Asset Optimizer - A Windows desktop tool that scans FiveM streaming folders to identify and fix optimization issues for game assets (.ytd, .yft, .ybn, etc.).

## Tech Stack

- **Frontend**: Electron 28 + React 18 (Vite bundler)
- **Backend**: Node.js (IPC communication, electron-store for persistence)
- **Analysis Engine**: Python 3.10+ (binary file analysis)
- **Platform**: Windows (frameless window, NSIS installer)

## Build & Development Commands

```bash
# Install dependencies
npm install

# Development (starts Vite dev server + Electron)
npm run dev

# Production build (Vite build + electron-builder)
npm run build

# Run Python analysis directly
C:\Python311\python.exe python/analyze.py <folder_path> [settings_json]

# Build renderer only
npm run build:renderer
```

**Important**: `python` is not in PATH on this system. Use `C:\Python311\python.exe` for direct testing.

## Architecture

```
├── src/
│   ├── main/main.js          # Electron main process (IPC, Python spawning, store)
│   ├── preload/preload.js     # Secure IPC bridge (contextIsolation)
│   └── renderer/
│       ├── App.jsx            # Root component, view routing
│       ├── styles.css         # All styles (dark theme, CSS variables)
│       ├── main.jsx           # React entry point
│       ├── index.html         # HTML shell with CSP
│       └── components/
│           ├── TitleBar.jsx          # Frameless window controls
│           ├── FolderPicker.jsx      # Landing page, drag-drop, folder select
│           ├── ScanProgress.jsx      # Progress bar with percentage
│           ├── ResultsDashboard.jsx  # Results, filters, export, stats
│           ├── IssueCard.jsx         # Expandable issue cards
│           ├── DependencyMap.jsx     # Asset dependency viewer
│           ├── SettingsPage.jsx      # Configurable thresholds
│           └── ErrorBoundary.jsx     # React error catch
├── python/
│   ├── analyze.py             # Main entry point (accepts settings as argv[2])
│   └── analyzers/
│       ├── generic_analyzer.py  # File size checks (all types)
│       ├── ytd_analyzer.py      # Textures: resolution, compression, mipmaps, VRAM
│       ├── yft_analyzer.py      # Vehicles: polys, bones, LODs
│       ├── ydr_analyzer.py      # Props: polys, LODs
│       ├── ybn_analyzer.py      # Collisions: complexity, bounds
│       ├── ymap_analyzer.py     # Maps: entity count, streaming extent
│       └── ytyp_analyzer.py     # Archetypes: count, references
├── package.json
├── vite.config.js
└── requirements.txt
```

### Data Flow

1. User selects/drops streaming folder in React UI
2. Electron validates folder, passes path + user settings to Python
3. Python walks directory, runs per-file analyzers, hashes for duplicates
4. Progress streamed as `PROGRESS:pct%|current/total|message` via stdout
5. Final JSON result extracted from stdout (first `{` to last `}`)
6. Results rendered in dashboard with severity filters, export, dependency map
7. Scan history saved to electron-store (last 20 scans)

### Key Patterns

- **Python analyzers** all take `(settings)` constructor and return `(issues, metadata)` tuples
- **IPC listeners** return cleanup functions for React `useEffect` teardown
- **Settings** are persisted via electron-store and passed to Python as JSON argv
- **Binary parsing** validates RSC7 magic headers and uses `struct.unpack_from` with bounds checking
- **Stat cards** act as toggle filters (click to filter by severity)
- **Export** supports JSON and CSV via native save dialog

### Key Analysis Capabilities

- **Texture analysis**: Resolution, compression format, mipmaps, NPOT detection, VRAM estimation
- **Model analysis**: Poly counts, bone counts, LOD validation (YFT + YDR)
- **Collision analysis**: Polygon complexity, bounding box dimensions
- **Map analysis**: Entity count, streaming extent validation (YMAP)
- **Archetype analysis**: Archetype count, referenced asset extraction (YTYP)
- **Memory footprint**: Total file size + per-texture VRAM estimation
- **Duplicate detection**: SHA256 hash-based, with wasted space calculation
- **Dependency mapping**: Cross-references ymaps/ytyps against known asset names

### FiveM File Types

- `.ytd` - Texture dictionaries (DXT1/DXT5/BC7 compressed)
- `.yft` - Fragment/vehicle models (with physics/bones)
- `.ydr` - Drawable models (static props)
- `.ybn` - Collision bounds (physics meshes)
- `.ymap` - Map placements (entity positions)
- `.ytyp` - Archetype definitions (model metadata)

## Installed Agent Skills

These skills are installed in `.claude/skills/` and `.agents/skills/`:

| Skill | Source | Use For |
|-------|--------|---------|
| `systematic-debugging` | obra/superpowers | Structured debugging approach |
| `test-driven-development` | obra/superpowers | Writing tests before implementation |
| `verification-before-completion` | obra/superpowers | Verify work is correct before marking done |
| `frontend-design` | anthropics/skills | High-quality UI/UX implementation |
| `python-performance-optimization` | wshobson/agents | Optimizing Python analysis scripts |
| `binary-analysis-patterns` | wshobson/agents | Improving RAGE binary file parsing |
| `code-review-excellence` | wshobson/agents | Thorough code review practices |
| `wcag-audit-patterns` | wshobson/agents | Accessibility compliance checking |

Install more with: `npx skills add <owner/repo> --skill <name> -a claude-code -y`

## Code Conventions

- No TypeScript — plain JSX + vanilla CSS (CSS variables for theming)
- Electron contextIsolation enabled — all IPC goes through preload bridge
- Python analyzers are standalone (no external deps beyond stdlib)
- All thresholds are user-configurable via Settings page
- Dark theme only (--bg-primary: #0a0a0f)
- SVG icons inline (no icon library dependency)
