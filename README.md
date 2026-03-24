# IgnoreScope

IgnoreScope is a Docker container management tool that uses volume layering to selectively hide directories from your project while allowing individual files to be pushed or pulled at runtime via `docker cp`. It provides both a CLI and a PyQt6 GUI for managing scoped container configurations across multiple projects.

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

**Windows note:** Docker Desktop uses WSL 2 by default. If prompted, follow the WSL 2 kernel update instructions.

### Python 3.13+

```bash
python --version
# Expected: Python 3.13.x
```

Download from [python.org](https://www.python.org/downloads/) if needed. Ensure "Add to PATH" is checked during install.

### uv (Package Manager)

[uv](https://docs.astral.sh/uv/) is used for installation. Install it first:

```bash
# Windows
winget install --id=astral-sh.uv -e

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
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
