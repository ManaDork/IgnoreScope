# IgnoreScope

IgnoreScope is a Docker container management tool that uses volume layering to selectively hide directories from your project while allowing individual files to be pushed or pulled at runtime via `docker cp`. It provides both a CLI and a PyQt6 GUI for managing scoped container configurations across multiple projects.

## Requirements

- Python 3.13+
- Docker Desktop
- [uv](https://docs.astral.sh/uv/)

### Installing uv

```bash
# Windows
winget install --id=astral-sh.uv -e

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Install

### From GitHub Release

```bash
uv pip install https://github.com/ManaDork/IgnoreScope/releases/download/v0.1.0/ignorescope_docker-0.1.0-py3-none-any.whl
```

### From Source

```bash
git clone https://github.com/ManaDork/IgnoreScope.git
cd IgnoreScope
uv pip install .
```

## Usage

```bash
# Launch GUI
ignorescope-docker gui

# CLI commands
ignorescope-docker create --project /path/to/project
ignorescope-docker push file1.txt file2.txt
ignorescope-docker pull file1.txt
ignorescope-docker remove --yes
```

## License

MIT