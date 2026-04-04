# Technical Design: Live View Mode — Scope Configuration

## Overview

Add container filesystem scanning to the Scope Configuration tree. The scan diffs container content against the host tree to identify container-only files, which are rendered as virtual nodes with a CONTAINER-ONLY visual state.

## Architecture

### Data Flow

```
Header RMB → "Scan for New Files"   ← scope_view.py:_show_header_context_menu()
         │                            (enabled when container running, same as Stop)
         ▼
scan_container_directory()          ← docker exec find (already implemented)
         │
         ▼
Container file paths (relative)
         │
         ▼
Diff engine                         ← NEW: compare against host tree paths
         │
    ┌────┴─────┐
    │          │
 BOTH       CONTAINER-ONLY
 (pushed)   (copied/created)
    │          │
    │          ▼
    │    Populate _container_files   ← MountDataTree (field exists, never populated)
    │          │
    │          ▼
    │    Create virtual TreeNodes    ← is_virtual=True (field exists, never used)
    │          │
    └────┬─────┘
         │
         ▼
_recompute_states()                 ← NodeState with container_only=True
         │
         ▼
ScopeView refresh                   ← CONTAINER-ONLY gradient renders
```

## Dependencies

### Internal (already implemented, needs wiring)
| Component | File | Line | Status |
|-----------|------|------|--------|
| `scan_container_directory()` | `docker/container_ops.py` | 672 | Implemented, never called |
| `_container_files: set[Path]` | `gui/mount_data_tree.py` | 159 | Field exists, never populated |
| `is_virtual: bool` | `gui/mount_data_tree.py` | 69 | TreeNode field, never set True |
| `_virtual_nodes: list` | `gui/mount_data_tree.py` | 168 | List exists, never populated |
| `container_only: bool` | `core/node_state.py` | 88 | NEW — added in this branch |
| `FILE/FOLDER_CONTAINER_ONLY` | `gui/display_config.py` | 93/134 | NEW — added in this branch |
| `"container_only"` color | `gui/tree_state_style.json` | 11 | NEW — added in this branch |
| `_show_header_context_menu` | `gui/scope_view.py` | 159 | Has Start/Stop — add Scan here |
| "Scan for New Files" placeholder | `gui/scope_view.py` | 269 | In _build_folder_menu — REMOVE |

### External
- Docker Desktop — `docker exec` for `find` command inside container

## Key Changes

### New
- **Diff engine** in `gui/mount_data_tree.py` or `core/` — compares scan results against host paths
- **Scan trigger** wiring in `gui/scope_view.py` → `gui/file_ops_ui.py`
- **Virtual node builder** in `gui/mount_data_tree.py` — creates TreeNode(is_virtual=True) entries

### Modified
- `gui/scope_view.py` — Add "Scan for New Files" to header context menu (line 175), remove disabled placeholder from `_build_folder_menu` (line 269), add `scanContainerRequested` signal
- `gui/mount_data_tree.py` — Populate `_container_files` and `_virtual_nodes` from scan diff
- `gui/file_ops_ui.py` — Add `on_scan_container()` handler
- `gui/app.py` — Connect scan signal

### Unchanged (reused as-is)
- `scan_container_directory()` — already returns relative file paths
- `to_container_path()` / `resolve_container_path()` — path mapping for diff comparison
- `_recompute_states()` — NodeState computation (will pick up container_only flag)
- Display filter proxy — already handles virtual node filtering via `display_virtual_nodes` config

## Diff Algorithm

```python
def compute_container_diff(host_paths: set[str], container_paths: set[str]) -> set[str]:
    """Return container-only paths (exist in container, not on host)."""
    return container_paths - host_paths
```

Path normalization: both sides must use the same format (POSIX, relative to container_root).
- Host paths: `to_container_path()` converts host absolute → container POSIX
- Container paths: `scan_container_directory()` already returns relative POSIX

## Risks

- **Performance:** `find -type f` on large containers (10k+ files) may be slow. Mitigation: scope scan to mounted paths only, or add timeout.
- **Path normalization:** Cross-platform path comparison (Windows host vs Linux container). Mitigation: normalize both to POSIX before diff.
- **Stale results:** Scan is a snapshot — container content may change after scan. Mitigation: show scan timestamp in UI.
