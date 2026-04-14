# IgnoreScope

> **Platform: Windows only** — macOS and Linux are not yet tested or supported.

IgnoreScope is a Docker container management tool that uses volume layering to selectively hide directories from your project while allowing individual files to be pushed or pulled at runtime via `docker cp`. It provides both a CLI and a PyQt6 GUI with a glassmorphism-styled theme system for managing scoped container configurations across multiple projects.

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

Upgrade from a previous version:
```bash
uv tool upgrade ignorescope-docker
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

## What's New in v0.4

### Undo/Redo System (Phase 1)
- **Full state capture** — snapshots now include mount_specs + pushed_files (not just mount_specs)
- **Keyboard shortcuts** — Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z for undo/redo (menu-integrated)
- **Signal infrastructure** — undoPerformed / redoPerformed signals for future UI integration (Phase 2)
- **DRY refactoring** — consolidated pattern operations, extracted state capture helper (~60 LOC saved)

### RMB Menu Logic Refinement
- **Mutual exclusivity fix** — masked folders no longer show both "Unmask" and "Reveal" options
- **Nesting support** — folders revealed by ancestor can now be masked (architecture-compliant)

### Menu Reorganization (v0.4.1)
- **Extensions menu** — new top-level menu separates optional extensions (Claude CLI, Git) from Docker core
- **Terminal preference moved** — terminal shell selection now in Edit menu (persistent user setting)
- **Container menu refined** — groups lifecycle ops (create/update/recreate/remove) + launch terminal + scope config (add sibling, container root name)
- **Launch menu removed** — terminal-related actions consolidated into Container and Edit menus
- **Clearer UI hierarchy** — visual distinction between required Docker operations and optional extensions

### Previous: v0.3
- **Glassmorphism theme** — single consolidated `glassmorphism_v1_theme.json` drives all colors, gradients, and fonts
- **Widget gradient backgrounds** — JSON-driven panel gradients for docks, status bar, config panel
- **Formulaic gradient derivation** — `derive_gradient()` and `derive_file_style()` replace hand-built state definitions
- **Categorical color system** — state classification with deep navy + vivid accent palette
- **Tree highlight fix** — suppress Windows accent bleed in branch indicators, focus rects, and palette
- **Visibility refactor** — pure STATE values (`accessible`, `restricted`, `virtual`) replacing mixed boolean flags
- **New folder states** — `FOLDER_MOUNTED`, `FOLDER_MOUNTED_REVEALED`, `FOLDER_MIRRORED`, `FOLDER_MIRRORED_REVEALED`
- **O(1) state resolution** — replaces O(n*states) gradient matching
- **Config panel collapse/expand** — min/max pin pattern for reliable dock sizing
- **GitHub-primary VCS** — architecture docs moved to `docs/architecture/`, local configs gitignored

## License

MIT
