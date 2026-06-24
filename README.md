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

This installs the `ignorescope-docker` command.

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

## What's New

### v0.7 — Marked Push
- **Unmark for Push (Local Host RMB)** — right-click a marked file in the Local Host tree to remove it from the push set.
- **Marked Push subsystem** — `marked-push` / `marked-staged` queues let you stage files for push *before* the container exists; a single drain engine flushes them on a lifecycle hook.
- **Config-first push** — the CLI gains `push-marked`; the GUI adds a status-bar badge and a review dialog for the pending push set.
- **`pre_pushed` node state** — new MatrixState axis with its own placeholder styling. Reveal now reaches the Local Host tree, and Push is disabled when no container is running.

### v0.6 — Cross-Tree Coordination
- **Independent selection coordinator** — the Local Host and Scope Config trees no longer fight over selection; multi-select survives programmatic expand/collapse cascades.
- **Tracked-path overlay** — a teal outline mirrors the *other* tree's selection, decoupled from the selection model so routine updates don't wipe it.
- **Branch-indicator mirror** — expanding/collapsing a Local Host folder mirrors one-way into the Scope tree.
- **Cursor-primary RMB** — the row under the cursor is the context-menu action target.
- **Fixes** — HCR-residency check skips container-only specs (no more false "not under host container root" after installing an extension); empty compose `volumes:` key omitted; wheel packaging corrected.

### v0.5 — Virtual Mount (per-spec delivery)
- **Per-spec `delivery`** — each mount spec chooses `bind` (host bind-mount), `detached` (`docker cp`-seeded snapshot), or `volume` (named Docker volume), and a single scope can mix them.
- **STENCIL nodes** — synthetic-origin nodes (`host_path` / `content_seed` / `preserve_on_update`) for content that lives only in the container.
- **Unified isolation** — extension-owned volumes fold onto the same per-spec framework under one `vol_*` naming scheme; "isolation" became descriptive vocabulary rather than a separate mode.

See [docs/architecture/EVOLUTION.md](docs/architecture/EVOLUTION.md) for the full mount/isolation design history. Earlier milestones — v0.4 (undo/redo, menu reorganization) and v0.3 (glassmorphism theme system) — live in the git history.

## License

MIT
