# Scope: System Tray Phase 2 — Container Discovery + Tray Actions

## Phases

### Phase 2 (This Feature)
Container discovery via Docker label + QSettings cross-reference, per-container action submenus.

### Phase 3 (Future, If Needed)
Async discovery with QTimer-based cache, tray balloon notifications for state changes.

## In Scope

- `list_ignorescope_containers()` function in `docker/container_ops.py`
- `parse_docker_name()` function in `docker/names.py`
- Exports in `docker/__init__.py`
- `_ContainerEntry` dataclass in `system_tray.py`
- `_discover_containers()` hybrid discovery in `system_tray.py`
- Containers submenu with `aboutToShow` dynamic rebuild
- Per-container Start/Stop, Terminal, Copy Terminal Cmd, Claude CLI, Copy Claude Cmd actions
- `_launch_terminal_from_tray()` (Type 2 clone, accepted)
- Unit tests for new Docker functions and discovery algorithm
- Module docstring update for `system_tray.py`

## Out of Scope

- Async/threaded container discovery
- Caching or TTL-based refresh
- Tray balloon notifications for state changes
- Container creation/removal from tray
- Opening project in GUI window from tray
- Extracting terminal launch to shared `utils/terminal.py`

## Task Breakdown

| # | Task | Depends On | Complexity | Files |
|---|------|-----------|------------|-------|
| 0 | Branch setup | — | S | git: `feature/system-tray-phase2` from `main` |
| 1 | `parse_docker_name()` | — | S | `docker/names.py`, `tests/test_docker/test_names.py` (new) |
| 2 | `list_ignorescope_containers()` | — | M | `docker/container_ops.py`, `tests/test_docker/test_container_ops.py` |
| 3 | Export new functions | 1, 2 | S | `docker/__init__.py` |
| 4 | `_ContainerEntry` + `_discover_containers()` | 3 | L | `gui/system_tray.py`, `tests/test_gui/test_system_tray.py` (new) |
| 5 | Containers submenu + `_populate_container_menu()` | 4 | M | `gui/system_tray.py` |
| 6 | Action handlers + `_launch_terminal_from_tray()` | 5 | M | `gui/system_tray.py` |
| 7 | Docstring update | 6 | S | `gui/system_tray.py` |

### Sequencing

```
Task 1 (S) ─────┐
parse_docker_name │
                  ├──→ Task 3 (S) ──→ Task 4 (L) ──→ Task 5 (M) ──→ Task 6 (M) ──→ Task 7 (S)
Task 2 (M) ─────┘    exports         discovery       menu build      handlers        docstring
```

Tasks 1 and 2 can run in parallel. Tasks 3-7 are sequential.

### Task Details

**Task 1: `parse_docker_name()`**
- Location: `docker/names.py` after `build_docker_name()` (line 71)
- `rsplit('__', 1)` → `tuple[str, str] | None`
- Test cases: normal split, last-delimiter split (`"a__b__c"` → `("a__b", "c")`), no delimiter → `None`, empty → `None`

**Task 2: `list_ignorescope_containers()`**
- Location: `docker/container_ops.py` after `get_llm_command()` (line 788)
- `docker ps -a --filter "label=maintainer=IgnoreScope" --format json`
- Parse JSON lines, extract `Names` (strip `/`), `State` → running bool
- Return `list[dict]` with `name`, `status`, `running` keys
- Return `[]` on any error; uses `get_subprocess_kwargs(timeout=5)`
- Test cases: valid JSON, empty output, timeout, nonzero returncode

**Task 3: Exports**
- Add to `docker/__init__.py` imports and `__all__`

**Task 4: Discovery**
- `_ContainerEntry` dataclass (6 fields)
- `_discover_containers()` method with full cross-reference algorithm
- Edge cases: nonexistent paths skipped, corrupt config caught (`ValueError`), empty Docker results
- Tests: mock all dependencies, verify matched/unmatched display names, graceful degradation

**Task 5: Menu build**
- Modify `_setup_tray()` to insert `QMenu("Containers")` with `aboutToShow` signal
- `_populate_container_menu()`: clear, discover, build per-container submenus
- Status indicators: `"● {name}"` running, `"○ {name}"` stopped
- Conditional Start/Stop, fixed Terminal + Claude CLI sections
- Bind via `functools.partial`

**Task 6: Handlers**
- 6 action handlers: `_on_start`, `_on_stop`, `_on_terminal`, `_on_copy_terminal`, `_on_claude`, `_on_copy_claude`
- `_launch_terminal_from_tray()`: Type 2 clone of `container_ops_ui._launch_terminal()` (lines 740-789)
- Platform dispatch: Windows (cmd/powershell/pwsh via QSettings), macOS (osascript), Linux (gnome-terminal/konsole/xterm)
- Success: `_tray_icon.showMessage()` balloon
- Error: `QMessageBox.critical()`

**Task 7: Docstring**
- Update `system_tray.py` module docstring IS/IS NOT to include container discovery and actions

## Testing Strategy

- **Unit:** `parse_docker_name()`, `list_ignorescope_containers()`, `_discover_containers()` — all subprocess/filesystem mocked
- **Integration:** None (Docker dependency)
- **Manual:** 16-point verification checklist (see technical-design.md Risks section for context)

### Manual Verification Checklist

1. Launch `python -m IgnoreScope` — tray icon appears
2. Right-click tray → "Containers" submenu visible between Show/Hide and Exit
3. Hover over Containers → submenu populates with discovered containers
4. Container status indicators (●/○) match Docker state
5. Start a stopped container from tray → balloon notification, status changes on re-hover
6. Stop a running container from tray → balloon notification, status changes on re-hover
7. Terminal action opens terminal with `docker exec -it {name} /bin/bash`
8. Copy Terminal Cmd → clipboard contains correct command
9. Claude CLI on container without Claude → error message at click time
10. Claude CLI on container with Claude → terminal with Claude session
11. Copy Claude Cmd → clipboard contains correct command
12. Containers from recent projects → display as `"MyGame (dev)"`
13. Containers NOT in recent projects → display as `"mygame (dev)"`
14. Docker Desktop stopped → "(Docker not available)" disabled item
15. No IgnoreScope containers → "(No containers found)" disabled item
16. Verify tray menu responsiveness — no noticeable lag on hover

## Estimated Size

~350-450 lines of new code + ~80-120 lines of tests across all tasks.
