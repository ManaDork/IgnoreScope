# System Tray — Phase 2: Container Discovery + Tray Actions

## Context

Phase 1 (completed) extracted `SystemTrayManager` to its own module. Phase 2 adds container discovery and per-container action submenus to the tray, enabling Run/Stop, Terminal, and Claude CLI actions for ANY IgnoreScope container — without requiring a project to be loaded in the GUI.

**Discovery strategy (user-specified hybrid):**
- **Plan B**: Query Docker via `docker ps -a --filter label=maintainer=IgnoreScope` — the label already exists in both Dockerfile generators (`compose.py:54`, `compose.py:106`)
- **Plan A**: Cross-reference with QSettings `recentProjects` (list of absolute path strings) to recover display-friendly names + scope names, since `sanitize_volume_name()` is a lossy transform (can't reverse `mygame` → `MyGame`)

---

## Tray Menu Structure

```
Right-click tray:
├── Show / Hide                    (existing)
├── ─────────
├── Containers ►                   (submenu, rebuilt on hover via aboutToShow)
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
│   ├── ○ Client (dev) ►
│   │   └── ...
│   └── (No containers found)     [disabled item, if empty]
├── ─────────
└── Exit                           (existing)
```

**Status indicators**: `●` running, `○` stopped — prefixed on each container submenu title.

**Claude CLI actions**: Always shown (no `is_installed()` check at menu-build time — that would add ~500ms per running container). Handler checks at click time and shows error if not installed, consistent with existing `launch_llm_in_container()` pattern.

---

## Step 1 — `container_ops.py`: Add `list_ignorescope_containers()`

Location: `IgnoreScope/docker/container_ops.py` — Terminal Command Construction section.

```python
def list_ignorescope_containers() -> list[dict]:
    """Query Docker for all IgnoreScope containers (running + stopped).

    Uses label filter: LABEL maintainer="IgnoreScope" (set in compose.py).

    Returns:
        List of dicts: {name: str, status: str, running: bool}
        Empty list if Docker not available or no containers found.
    """
```

**Implementation**: `docker ps -a --filter "label=maintainer=IgnoreScope" --format json`
- Parse JSON lines (one per container)
- Extract: `Names` → name, `State` → status/running
- Return empty list on any error (Docker not running, timeout)
- Follows existing `_run_docker_simple()` / `get_subprocess_kwargs()` patterns

## Step 2 — `names.py`: Add `parse_docker_name()`

Location: `IgnoreScope/docker/names.py` — after `build_docker_name()`.

```python
def parse_docker_name(docker_name: str) -> tuple[str, str] | None:
    """Parse IgnoreScope container name into (project_part, scope_part).

    Splits on LAST '__' delimiter. Returns sanitized (lowercase) parts only —
    cannot recover original case or special characters.

    Returns None if name contains no '__' (not IgnoreScope format).
    """
```

**Split on LAST `__`**: Scope names are simple (`dev`, `prod`), project names may contain underscores.

## Step 3 — `docker/__init__.py`: Export new functions

Add `list_ignorescope_containers` and `parse_docker_name` to the import list.

## Step 4 — `system_tray.py`: Expand with container discovery + actions

### 4a. Add `_ContainerEntry` dataclass

```python
@dataclass
class _ContainerEntry:
    display_name: str          # "MyGame (dev)" or "mygame (dev)" if unmatched
    docker_name: str           # Actual Docker container name
    running: bool              # Current Docker state
    project_path: Path | None  # Original path if matched from recent projects
    scope_name: str            # Parsed or derived scope name
    container_root: str        # For LLM -w flag; from config or "/"
```

### 4b. Add `_discover_containers()` — hybrid cross-reference

```
Flow:
1. list_ignorescope_containers()        → Docker containers (label-filtered)
2. QSettings("recentProjects")          → recent project paths
3. For each recent project:
   a. list_containers(project_path)     → scope names from disk (.ignore_scope/)
   b. build_docker_name(path, scope)    → expected docker name
   c. load_config(path, scope)          → container_root for LLM commands
4. Cross-reference: match Docker names to expected names
   - Matched → display_name = "{project_path.name} ({scope})", with container_root from config
   - Unmatched → parse_docker_name() for display, container_root = "/"
```

### 4c. Modify `_setup_tray()` — add Containers submenu

Insert between existing Show/Hide and Exit:
```python
self._containers_menu = QMenu("Containers", self._app)
self._containers_menu.aboutToShow.connect(self._populate_container_menu)
tray_menu.addMenu(self._containers_menu)
tray_menu.addSeparator()
```

The Containers submenu rebuilds its contents via `aboutToShow` — fires on hover, so discovery runs only when the user actually opens it.

### 4d. Add `_populate_container_menu()`

Clears `self._containers_menu`, calls `_discover_containers()`, builds per-container submenus with action items.

### 4e. Add action handlers

| Method | What it does |
|--------|-------------|
| `_on_start(docker_name)` | `start_container()` → tray notification on error |
| `_on_stop(docker_name)` | `stop_container()` → tray notification on error |
| `_on_terminal(docker_name)` | `ensure_container_running()` → `get_terminal_command()` → `_launch_terminal_from_tray()` |
| `_on_copy_terminal(docker_name)` | `get_terminal_command()` → clipboard |
| `_on_claude(entry)` | `ensure_container_running()` → `get_llm_command(name, root, binary)` → `_launch_terminal_from_tray()` |
| `_on_copy_claude(entry)` | `get_llm_command()` → clipboard |

### 4f. Add `_launch_terminal_from_tray()`

Simplified copy of `container_ops_ui._launch_terminal()`:
- Same `subprocess.Popen` logic per platform (Windows cmd/powershell/pwsh, macOS, Linux)
- Reads `QSettings("terminal_preference")` for Windows terminal choice
- Errors via `QMessageBox` (no statusBar access from tray)

**DRY note**: Type 2 clone of `container_ops_ui._launch_terminal()`. Acceptable because:
- Tray manager must not import `container_ops_ui` (composition boundary)
- Error reporting differs (no statusBar)
- If a third callsite appears, extract to `utils/terminal.py`

---

## Files Modified

| File | Change |
|------|--------|
| `IgnoreScope/docker/container_ops.py` | **Add** `list_ignorescope_containers()` |
| `IgnoreScope/docker/names.py` | **Add** `parse_docker_name()` |
| `IgnoreScope/docker/__init__.py` | **Add** exports for new functions |
| `IgnoreScope/gui/system_tray.py` | **Expand** — dataclass, discovery, container submenu, action handlers, terminal launch |

## Existing Functions Reused (no new code needed)

| Function | File | Used For |
|----------|------|----------|
| `build_docker_name()` | `docker/names.py` | Cross-reference: project+scope → expected docker name |
| `list_containers()` | `core/config.py` | Discover scope names from disk per project |
| `load_config()` | `core/config.py` | Load `container_root` for LLM commands |
| `start_container()` | `docker/container_ops.py` | Tray start action |
| `stop_container()` | `docker/container_ops.py` | Tray stop action |
| `ensure_container_running()` | `docker/container_ops.py` | Pre-terminal/LLM launch |
| `get_terminal_command()` | `docker/container_ops.py` | Terminal command string |
| `get_llm_command()` | `docker/container_ops.py` | Claude CLI command string |
| `ClaudeInstaller.BINARY_PATH` | `container_ext/claude_extension.py` | Binary path for `get_llm_command()` |

## DRY Audit

| Clone | Files | Type | Action |
|-------|-------|------|--------|
| Terminal Popen logic | `container_ops_ui._launch_terminal` ↔ `system_tray._launch_terminal_from_tray` | Type 2 | Acceptable — different error context, composition boundary |
| QSettings read | `menus.py` ↔ `system_tray._discover_containers` | Type 3 | Different purposes, no extraction needed |
| `get_llm_command()` call | `container_ops_ui` ↔ `system_tray` | Type 2 | 3-line pattern, no extraction needed |

## Documentation Updates

### `GUI_LAYOUT_SPECS.md` — Section 9 (system_tray.py entry)

Update IS/IS NOT docstring to include container discovery:
> IS: QSystemTrayIcon lifecycle, tray context menu (Show/Hide, Containers submenu, Exit),
> tray-based window visibility toggle, container discovery via Docker label filter +
> QSettings cross-reference, per-container actions (start/stop, terminal, Claude CLI),
> application quit sequence.

### `DATAFLOWCHART.md` — Module map (system_tray.py entry)

Update: `system_tray.py → Tray Icon (tray menu: show/hide, container discovery + actions, exit; quit sequence)`

## Verification

1. `docker ps -a --filter "label=maintainer=IgnoreScope" --format json` — verify label filter works for stopped containers
2. Launch app: `python -m IgnoreScope` — tray icon appears
3. Right-click tray → Containers submenu populates with discovered containers
4. Container status indicators (●/○) match Docker state
5. Start/Stop actions toggle container state, submenu reflects change on re-hover
6. Terminal action opens terminal with `docker exec -it {name} /bin/bash`
7. Copy Terminal Cmd → clipboard contains correct command
8. Claude CLI action launches Claude in terminal (or shows error if not installed)
9. Copy Claude Cmd → clipboard contains correct command
10. Containers from recent projects show display-friendly names: `"MyGame (dev)"`
11. Containers NOT in recent projects show parsed names: `"mygame (dev)"`
12. Docker not running → Containers submenu shows "(Docker not available)"
