# IgnoreScope

> **Platform: Windows only** — macOS and Linux are not yet tested or supported.

IgnoreScope is a Docker container management tool that uses volume layering to selectively hide directories from your project while allowing individual files to be pushed or pulled at runtime via `docker cp`. It provides both a CLI and a PyQt6 GUI with a glassmorphism-styled theme system for managing scoped container configurations across multiple projects.

## What's New in v0.3

### Theme & Visual System
- **Glassmorphism theme** — single consolidated `glassmorphism_v1_theme.json` drives all colors, gradients, and fonts
- **Widget gradient backgrounds** — JSON-driven panel gradients for docks, status bar, config panel
- **Formulaic gradient derivation** — `derive_gradient()` and `derive_file_style()` replace hand-built state definitions
- **Categorical color system** — state classification with deep navy + vivid accent palette
- **Tree highlight fix** — suppress Windows accent bleed in branch indicators, focus rects, and palette

### Core Architecture
- **Visibility refactor** — pure STATE values (`accessible`, `restricted`, `virtual`) replacing mixed boolean flags
- **New folder states** — `FOLDER_MOUNTED`, `FOLDER_MOUNTED_REVEALED`, `FOLDER_MIRRORED`, `FOLDER_MIRRORED_REVEALED`
- **O(1) state resolution** — replaces O(n*states) gradient matching

### GUI
- **Config panel collapse/expand** — min/max pin pattern for reliable dock sizing
- **Dead code removal** — Undo/Redo menu enabled, unused extensions and compose module removed
- **Focus suppression** — unconditional focus rect clearing + QPalette.Highlight override

### Infrastructure
- **GitHub-primary VCS** — architecture docs moved to `docs/architecture/`, local configs gitignored
- **New architecture doc** — `THEME_WORKFLOW.md` for color sampling and theme application
- **Expanded test coverage** — style engine, display config, and node state test suites

## Prerequisites

### Docker Desktop

IgnoreScope requires Docker Desktop to create and manage containers.

1. Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
2. Run the installer
3. After install, Docker Desktop must be **running** (check the system tray icon)
4. Verify from a terminal:
   ```bash
   docker --version
   # Expected: Docker version 27.x or later
   ```

Docker Desktop uses WSL 2 by default on Windows. If prompted, follow the WSL 2 kernel update instructions.

### Python 3.13+

```bash
python --version
# Expected: Python 3.13.x
```

Download from [python.org](https://www.python.org/downloads/) if needed. Ensure "Add to PATH" is checked during install.

### uv (Package Manager)

[uv](https://docs.astral.sh/uv/) is used for installation. Install it first:

```bash
winget install --id=astral-sh.uv -e
```

## Install

```bash
uv tool install git+https://github.com/ManaDork/IgnoreScope
```

Verify:
```bash
ignorescope-docker --help
```

This installs two entry points: `ignorescope-docker` and `IgnoreScope` (both run the same tool).

### Python Dependencies (handled automatically)

These are installed automatically by `uv` — listed here for reference:

| Package | Purpose |
|---------|---------|
| `PyQt6 >= 6.5.0` | GUI framework |
| `pathspec >= 0.12.0` | Gitignore-style pattern matching |
| `pytest >= 7.0` | Testing (optional, dev only) |

## Usage

```bash
# Launch GUI
ignorescope-docker gui

# CLI commands
ignorescope-docker create --project /path/to/project
ignorescope-docker list
ignorescope-docker push file1.txt file2.txt
ignorescope-docker pull file1.txt
ignorescope-docker remove --yes
```

See [USAGE.md](USAGE.md) for the full step-by-step workflow guide.

## License

MIT
