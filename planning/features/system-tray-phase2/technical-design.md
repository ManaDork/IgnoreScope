# Technical Design: System Tray Phase 2 — Container Discovery + Tray Actions

## Overview

Expand `SystemTrayManager` (currently 84 lines) to discover IgnoreScope containers via Docker label filter, cross-reference with QSettings recent projects for display-friendly names, and provide per-container action submenus (Start/Stop, Terminal, Claude CLI). Two new functions are added to the Docker layer (`list_ignorescope_containers`, `parse_docker_name`), and the tray module grows by ~200 lines.

## Architecture

### Layer Placement

System tray remains at **L7** in the GUI architecture. New Docker-layer functions sit in the existing `container_ops.py` and `names.py` modules — no new modules needed.

```
L7  system_tray.py  →  docker/container_ops.py  (list, start, stop, ensure, get_cmds)
                    →  docker/names.py           (build_docker_name, parse_docker_name)
                    →  core/config.py            (list_containers, load_config)
                    →  QSettings                 (recentProjects — read-only)
```

### Composition Boundary

`system_tray.py` imports from `docker/` and `core/` directly. It does **NOT** import `gui/container_ops_ui.py`. This boundary is intentional — the tray manager operates independently of the GUI window's container operations handler.

## Container Discovery Algorithm (Plan A)

### Data Sources

```
┌─────────────────────────────────────────────────────────────────────┐
│  SOURCE 1: Docker Engine (live state)                               │
│  docker ps -a --filter "label=maintainer=IgnoreScope" --format json │
│  Returns: [{name, state, running}, ...]                             │
│  Provides: WHAT containers exist + ARE THEY RUNNING                 │
│  Weakness: Names are sanitized/lowercase (lossy transform)          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  SOURCE 2: QSettings "recentProjects" (user history)                │
│  QSettings("IgnoreScope","IgnoreScope").value("recentProjects",[])  │
│  Returns: ["D:\\Projects\\MyGame", "E:\\Work\\Client", ...]         │
│  Provides: Original project PATHS (preserves case, full path)       │
│  Weakness: Only projects the user has opened in GUI                 │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  SOURCE 3: Filesystem .ignore_scope/ (disk state)                   │
│  list_containers(path) → scope names from subdirs                   │
│  load_config(path, scope) → ScopeDockerConfig with container_root   │
│  Provides: Scope names + config data for each project               │
│  Weakness: Only works if project path still exists on disk           │
└─────────────────────────────────────────────────────────────────────┘
```

### Algorithm Flow

```
                    ┌──────────────────────┐
                    │  aboutToShow signal   │
                    │  (user hovers menu)   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  is_docker_running()  │──── False ──→ ┌────────────────────────┐
                    │  (~50ms, cached)      │               │ Show "(Docker not       │
                    └──────────┬───────────┘               │  available)" disabled   │
                               │ True                      └────────────────────────┘
                    ┌──────────▼───────────┐
                    │  Docker Label Query   │
                    │  docker ps -a         │
                    │  --filter label=       │
                    │   maintainer=          │
                    │   IgnoreScope          │
                    │  --format json         │
                    │  (~100-200ms)          │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Parse JSON lines     │
                    │  → docker_containers  │──── Empty ──→ ┌────────────────────────┐
                    │  [{name, running}]    │               │ Show "(No containers   │
                    └──────────┬───────────┘               │  found)" disabled      │
                               │ Has entries               └────────────────────────┘
                    ┌──────────▼───────────┐
                    │  Read QSettings       │
                    │  "recentProjects"     │
                    │  (~1ms, registry)     │
                    └──────────┬───────────┘
                               │
                ┌──────────────▼──────────────┐
                │  For each recent_path:       │
                │                              │
                │  ┌─ Path exists on disk? ──┐ │
                │  │  NO → skip              │ │
                │  │  YES ↓                  │ │
                │  │                         │ │
                │  │  list_containers(path)   │ │
                │  │  → ["dev", "prod", ...] │ │
                │  │     (~1ms, dir listing) │ │
                │  │                         │ │
                │  │  For each scope:        │ │
                │  │    build_docker_name()   │ │
                │  │    → "mygame__dev"       │ │
                │  │    (~instant)            │ │
                │  │                         │ │
                │  │    load_config(p, s)     │ │
                │  │    → .container_root     │ │
                │  │    (~1ms, JSON parse)    │ │
                │  └─────────────────────────┘ │
                │                              │
                │  Build lookup dict:          │
                │  {                            │
                │    "mygame__dev": {           │
                │      path: D:\Projects\MyGame│
                │      scope: "dev"            │
                │      container_root: "/MyGame"│
                │    },                        │
                │    "client__dev": {...}       │
                │  }                            │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Cross-Reference             │
                │                              │
                │  For each docker_container:  │
                │                              │
                │  ┌─ name in lookup? ────────┐│
                │  │                          ││
                │  │  YES (MATCHED):          ││
                │  │   display = "MyGame (dev)"│
                │  │   project_path = D:\...  ││
                │  │   container_root = config││
                │  │                          ││
                │  │  NO (UNMATCHED):         ││
                │  │   parse_docker_name()    ││
                │  │   → ("mygame", "dev")    ││
                │  │   display = "mygame (dev)"│
                │  │   project_path = None    ││
                │  │   container_root = "/"   ││
                │  └──────────────────────────┘│
                │                              │
                │  Sort: running first,        │
                │        then alphabetical     │
                └──────────────┬──────────────┘
                               │
                    ┌──────────▼───────────┐
                    │  → List[_Container-   │
                    │    Entry]              │
                    └──────────────────────┘
```

### Timing Budget

| Step | Time | Notes |
|------|------|-------|
| `is_docker_running()` | ~50ms | `docker info`, timeout=5s ceiling |
| Docker label query | ~200ms | `docker ps -a --filter`, timeout=5s ceiling |
| QSettings read | ~1ms | Windows registry lookup |
| Per-project disk scan | ~2ms x N | `list_containers()` = directory listing |
| Per-scope config load | ~1ms x M | JSON file read |
| `build_docker_name()` | ~instant | String sanitization |
| Cross-reference + sort | ~instant | Dict lookup |
| **Total (10 projects, 2 scopes each)** | **~280ms** | Acceptable for hover menu |

## Architecture Decisions

**AD-1: Synchronous discovery on UI thread.**
`docker ps --filter` takes 50-200ms. Same pattern as `menus.py:update_docker_menu_states()` which calls `container_exists()` (a `docker inspect` subprocess) synchronously on menu state refresh. `get_subprocess_kwargs(timeout=5)` provides a safety ceiling. If latency proves unacceptable in practice (measured, not speculated), Phase 3 could add a QTimer-based cache with TTL.

**AD-2: Claude CLI check at click-time, not menu-build time.**
`ClaudeInstaller.is_installed()` runs `docker exec` (~500ms per container). Checking N containers at menu build adds N x 500ms. Instead, the Claude CLI action is always shown; the handler checks at click time and shows an error if not installed. This matches the existing `launch_llm_in_container()` pattern.

**AD-3: Distinguish Docker unavailable from no containers.**
Call `is_docker_running()` before the label query. This is fast (~50ms) and provides a clear user-facing distinction: "(Docker not available)" vs "(No containers found)".

## Dependencies

### Internal (Existing — Reused As-Is)

| Function | File | Used For |
|----------|------|----------|
| `is_docker_running()` | `docker/container_ops.py:71` | Pre-check before discovery |
| `start_container()` | `docker/container_ops.py:210` | Tray start action |
| `stop_container()` | `docker/container_ops.py:226` | Tray stop action |
| `ensure_container_running()` | `docker/container_ops.py` | Pre-terminal/LLM launch |
| `get_terminal_command()` | `docker/container_ops.py:760` | Terminal command string |
| `get_llm_command()` | `docker/container_ops.py:772` | Claude CLI command string |
| `build_docker_name()` | `docker/names.py:56` | Cross-reference: project+scope → expected name |
| `list_containers()` | `core/config.py:322` | Discover scope names from disk per project |
| `load_config()` | `core/config.py:342` | Load `container_root` for LLM commands |
| `get_subprocess_kwargs()` | `utils/subprocess_helpers.py` | Subprocess timeout/encoding |
| `ClaudeInstaller.BINARY_PATH` | `container_ext/claude_extension.py` | Binary path for `get_llm_command()` |
| Docker label `maintainer=IgnoreScope` | `docker/compose.py:54,108` | Already set in both Dockerfile generators |
| QSettings `"recentProjects"` | `gui/menus.py:391` | Managed by menu system |

### Internal (New)

| Function | File | Purpose |
|----------|------|---------|
| `list_ignorescope_containers()` | `docker/container_ops.py` | Docker label query for all IgnoreScope containers |
| `parse_docker_name()` | `docker/names.py` | Reverse parse container name on last `__` delimiter |

### External

None — all dependencies are internal.

### Ordering

Tasks 1-2 (new Docker functions) can be built in parallel. Task 3 (exports) depends on both. Tasks 4-6 (tray expansion) are sequential.

## Key Changes

### New

- `_ContainerEntry` dataclass in `system_tray.py` — bundles per-container data for the discovery-to-menu pipeline
- `_discover_containers()` method — hybrid cross-reference algorithm
- `_populate_container_menu()` method — dynamic submenu builder
- 6 action handlers: `_on_start`, `_on_stop`, `_on_terminal`, `_on_copy_terminal`, `_on_claude`, `_on_copy_claude`
- `_launch_terminal_from_tray()` — platform-aware terminal launcher
- `list_ignorescope_containers()` in `docker/container_ops.py`
- `parse_docker_name()` in `docker/names.py`
- Test files: `test_docker/test_names.py`, `test_gui/test_system_tray.py`

### Modified

- `system_tray.py:_setup_tray()` — insert Containers submenu between Show/Hide and Exit
- `system_tray.py` module docstring — update IS/IS NOT
- `docker/__init__.py` — add exports

## Interfaces & Data

### `_ContainerEntry` (private dataclass)

```python
@dataclass
class _ContainerEntry:
    display_name: str          # "MyGame (dev)" or "mygame (dev)"
    docker_name: str           # Actual Docker container name
    running: bool              # Current Docker state
    project_path: Path | None  # Original path if matched from QSettings
    scope_name: str            # Scope name (from config or parsed)
    container_root: str        # Container working dir; "/" if unmatched
```

### `list_ignorescope_containers()` (public function)

```python
def list_ignorescope_containers() -> list[dict]:
    """Query Docker for all IgnoreScope containers (running + stopped).
    Returns: list of {name: str, status: str, running: bool}
    Returns empty list on any error.
    """
```

### `parse_docker_name()` (public function)

```python
def parse_docker_name(docker_name: str) -> tuple[str, str] | None:
    """Parse IgnoreScope container name into (project_part, scope_part).
    Splits on LAST '__' delimiter. Returns None if no delimiter.
    """
```

### Tray Menu Structure

```
Right-click tray:
├── Show / Hide                    (existing)
├── ─────────
├── Containers ►                   (submenu, rebuilt on hover)
│   ├── ● MyGame (dev) ►          (● = running, ○ = stopped)
│   │   ├── ■ Stop                [shown if running]
│   │   │   — OR —
│   │   ├── ▶ Start               [shown if stopped]
│   │   ├── ─────────
│   │   ├── Terminal
│   │   ├── Copy Terminal Cmd
│   │   ├── ─────────
│   │   ├── Claude CLI
│   │   └── Copy Claude Cmd
│   ├── ○ client (dev) ►
│   │   └── ...
│   └── (No containers found)     [disabled, if empty]
├── ─────────
└── Exit                           (existing)
```

## DRY Audit

| Clone | Files | Type | Decision |
|-------|-------|------|----------|
| Terminal Popen logic | `container_ops_ui._launch_terminal` / `system_tray._launch_terminal_from_tray` | Type 2 | Accepted — different error context (QMessageBox vs statusBar), composition boundary. Extract to `utils/terminal.py` if third callsite appears. |
| QSettings `"recentProjects"` read | `menus.py._load_recent_menu` / `system_tray._discover_containers` | Type 3 | Different purposes (menu population vs cross-reference). Add cross-reference comments. |
| `get_llm_command()` call pattern | `container_ops_ui` / `system_tray` | Type 2 | 3-line pattern, no extraction needed. |

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Docker subprocess latency on `aboutToShow` | Medium | `timeout=5` ceiling; add `logger.debug` timing; async is Phase 3 if measured as needed |
| Container removed between discovery and click | Low | Action functions already handle "not found" gracefully, return `(False, message)` |
| `load_config()` failure for recent project | Medium | `try/except ValueError`, skip that scope, log warning |
| QSettings key `"recentProjects"` drift | Low | Same literal in both files; add cross-reference comments in both locations |
| Docker `--format json` output variation | Low | Strip leading `/` from `Names`; stable in Docker 20.10+ |
| Type 2 clone drift | Low | Document clone relationship in both docstrings; extract if third callsite appears |
