# Technical Design: Deploy P4 MCP Server (Linux) to Container

## Overview

Replace the hardcoded `P4McpInstaller` mount-dependent deployment with three LLM-readable markdown instruction documents. Claude Code reads these documents and executes steps using IgnoreScope's CLI and standard shell commands. The binary is transferred from the host via IgnoreScope's push command (with directory support), eliminating the `/devenv` volume mount dependency.

## Architecture

### Current Flow (mount-dependent)
```
Host: {devenv}/mcp/p4-mcp-server/linux/
  ↓ volume mount
Container: /devenv/mcp/p4-mcp-server/linux/
  ↓ cp -r (inside container)
Container: /usr/local/lib/p4-mcp-server/
  ↓ symlink
Container: /usr/local/bin/p4-mcp-server-linux
```

### New Flow (IgnoreScope CLI)
```
Host: {devenv}/mcp/p4-mcp-server/linux/
  ↓ IgnoreScope push (docker cp, directory support)
Container: /usr/local/lib/p4-mcp-server/
  ↓ chmod + symlink (per SETUP.md)
Container: /usr/local/bin/p4-mcp-server-linux
```

### Document Locations
```
{devenv}/mcp/p4-mcp-server/linux/
├── P4_MCP_LINUX_BUILD.md      ← Build instructions (reference)
├── P4_MCP_LINUX_DEPLOY.md     ← Host-side deployment workflow
├── P4_MCP_LINUX_SETUP.md      ← Container-side setup (pushed with binary)
├── p4-mcp-server              ← Linux ELF binary
└── _internal\                 ← PyInstaller native libs
```

## Dependencies

### Internal
- `IgnoreScope/docker/container_ops.py` — `push_file_to_container()` (needs directory support)
- `IgnoreScope/core/config.py` — `list_containers()` for container discovery
- `IgnoreScope/docker/container_ops.py` — `get_container_info()` for status display
- `IgnoreScope/docker/container_ops.py` — `ensure_container_running()` for auto-start

### External
- Docker Desktop — `docker cp` for file transfer
- `ManaDork/p4mcp-server-linux` — Source repo for building the binary

### Ordering
1. **First:** Extend `push_file_to_container()` to support directories
2. **Then:** Create the three instruction MDs
3. **Future:** GUI menu item once independent install works

## Key Changes

### New
- `{devenv}/mcp/p4-mcp-server/linux/P4_MCP_LINUX_BUILD.md` — Build reference
- `{devenv}/mcp/p4-mcp-server/linux/P4_MCP_LINUX_DEPLOY.md` — Host deploy workflow
- `{devenv}/mcp/p4-mcp-server/linux/P4_MCP_LINUX_SETUP.md` — Container setup steps

### Modified
- `IgnoreScope/docker/container_ops.py` — Relax `is_file()` guard at line 585 to accept directories

### Unchanged (reused as-is)
- `list_containers()` — Container discovery
- `get_container_info()` — Status (running/stopped)
- `ensure_container_running()` — Auto-start on push
- `ensure_container_directories()` — mkdir -p for target paths

## Interfaces & Data

No new Python interfaces. The "interface" is the markdown documents themselves — Claude Code reads them and executes CLI commands.

### DEPLOY.md Workflow Branches
```
Entry → "Deploying" or "Configuring"?
  ├── DEPLOY WORKFLOW → ask for IgnoreScope path → CP WORKFLOW
  └── CONFIG WORKFLOW → ask for .p4config/.p4ignore values → CP WORKFLOW
      └── CP WORKFLOW:
            1. python -m IgnoreScope list (query containers + status)
            2. User selects target container
            3. python -m IgnoreScope push --container <name> <binary_dir> <SETUP.md>
            4. Auto-starts if stopped
```

### SETUP.md Commands (inside container)
```bash
chmod +x /usr/local/lib/p4-mcp-server/p4-mcp-server
ln -sf /usr/local/lib/p4-mcp-server/p4-mcp-server /usr/local/bin/p4-mcp-server-linux
p4-mcp-server-linux --version   # verify
```

## Alternatives Considered

| Approach | Rejected Because |
|----------|-----------------|
| Keep `/devenv` mount dependency | Boundary violation — ties extension to workflow |
| Python installer with `docker cp` | Hardcoded logic; LLM instructions are more flexible and transparent |
| HTTP download of binary | Requires hosting infrastructure; binary is platform-locked PyInstaller build |
| Build in target container | Heavyweight — needs build tools, git clone, ~5 min build time per container |

## Risks

- **Directory push size** — The `linux/` directory is ~170MB. `docker cp` handles this but may be slow on first transfer. Mitigation: acceptable for one-time install.
- **IgnoreScope CLI discoverability** — DEPLOY.md needs to reference IgnoreScope by path or assume it's installed. Mitigation: ask user for path if not in context.
- **Container list command gap** — No dedicated `list` CLI command exists; `list_containers()` is programmatic only. Mitigation: DEPLOY.md may need to instruct Claude to call the Python function directly or use the interactive CLI.
