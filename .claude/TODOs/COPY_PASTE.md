# Plan: ScopeView RMB Context Menu — New Folder, Copy Path, Paste

## Context

The ScopeView (right panel, container perspective) has limited RMB actions: files get Push/Sync/Pull/Remove, folders get only Expand/Collapse/Scan(disabled). Users need:
- **New Folder** — create container-only directories via `docker exec mkdir`
- **Copy Path Container / Copy Path Host** — clipboard copy of either path representation
- **Paste** — paste host files/folders from clipboard into a container folder (acts like Push)

These are container-interaction actions that complement the existing Push/Pull workflow.

**Terminology:**
- **Pushed Files** = workflow operation, tracked in `pushed_files`, repeatable push/pull/update cycle
- **Copied Files** = ephemeral, untracked, transferred as-is via paste or `cp` command
- See `ARCHITECTUREGLOSSARY.md` for full definitions.

---

## Step 0: Prerequisite — Directory Push Support

**File:** `IgnoreScope/docker/container_ops.py`
**Status:** DONE — `is_file()` guard at line 585 relaxed to accept `is_dir()`.

The `push_file_to_container()` function now accepts both files and directories. `docker cp` handles directory transfer natively. This enables:
- GUI Paste of directories from clipboard
- CLI `cp` command for directory transfer
- P4 MCP binary directory deployment (see `planning/features/deploy-p4mcp-linux/`)

---

## Paste Safeguard — Masked Directory Check

**Where:** Step 4b `on_paste_files()` in `file_ops_ui.py`

Before executing paste, check if any source path is under a masked directory. If so, **block the paste** and show a warning directing the user to the Push workflow.

```python
# SAFEGUARD: Check if source is under a masked directory
for host_path in host_paths:
    if self._is_under_masked(host_path):
        QMessageBox.warning(
            self._app,
            "Cannot Paste from Masked Directory",
            f"'{host_path.name}' is inside a masked directory.\n\n"
            "Masked files are intentionally hidden project files.\n"
            "Use the Push workflow from Local Host Configuration "
            "to make them visible in the container.\n\n"
            "Copy/Paste is for external, non-project files only.",
        )
        return
```

**Why:** Masked files are intentionally hidden project files within the mirrored structure. If they're meant to be visible in the container, they should be Pushed — the Push workflow handles mask-volume file placement correctly and tracks them for sync. Copy/Paste is for external, non-project files only.

**Check method:** Walk `host_path` ancestors against `_mount_data_tree._masked` set.

---

## Files Modified

| File | Change |
|------|--------|
| `gui/mount_data_tree.py` | Add `_host_container_root` field, `host_container_root` property, `to_container_path()` method |
| `gui/scope_view.py` | 2 new signals, 4 new RMB actions, `_container_running` flag, helper methods |
| `gui/file_ops_ui.py` | `on_create_folder()` and `on_paste_files()` handlers |
| `gui/app.py` | 2 new signal→slot connections (line ~342) |

---

## Step 1: `mount_data_tree.py` — Expose `host_container_root` + path helper

**Why:** ScopeView needs to compute container paths for Copy Path and New Folder. Currently `host_container_root` is only available by loading config from disk (`file_ops_ui.py:105`). Storing it on the tree centralizes access.

### 1a. Add field in `__init__` (after line 161)
```python
self._host_container_root: Optional[Path] = None
```

### 1b. Add property (near `container_root` property, line 366)
```python
@property
def host_container_root(self) -> Optional[Path]:
    return self._host_container_root or (
        self._host_project_root.parent if self._host_project_root else None
    )
```

### 1c. Set in `load_config()` (after line 571)
```python
self._host_container_root = getattr(config, 'host_container_root', None)
```

### 1d. Clear in `clear()` (line 625) and `set_host_project_root()` (line 303)
```python
self._host_container_root = None
```

### 1e. Add convenience method
```python
def to_container_path(self, host_path: Path) -> str:
    """Convert host path to container-side POSIX path. Returns '' if unconfigured."""
    if not self._container_root or not self.host_container_root:
        return ""
    from ..core.hierarchy import to_container_path
    return to_container_path(host_path, self._container_root, self.host_container_root)
```

**Reuses:** `core.hierarchy.to_container_path()` (line 21) — existing path translation function.

---

## Step 2: `scope_view.py` — Signals + `_container_running` flag

### 2a. New signals (after line 85)
```python
createFolderRequested = pyqtSignal(str)      # container_path for mkdir
pasteFilesRequested = pyqtSignal(list, str)   # [host Paths], container_target_dir
```

### 2b. Add imports
Add `QApplication`, `QInputDialog` to existing PyQt6 imports.

### 2c. `_container_running` flag in `__init__`
```python
self._container_running: bool = False
```

### 2d. Cache in `refresh()` (after `show_pushed` is computed, ~line 131)
```python
self._container_running = show_pushed
```

---

## Step 3: `scope_view.py` — RMB menu additions

### 3a. `_build_file_menu()` — append after existing actions
```
separator
Copy Path Container    (always, if container_path computable)
Copy Path Host         (always)
```

### 3b. `_build_folder_menu()` — append after Scan placeholder
```
separator
Copy Path Container
Copy Path Host
separator
New Folder             (enabled only when _container_running)
Paste                  (enabled when _container_running AND clipboard has file URLs)
```

### 3c. Helper methods

**`_copy_to_clipboard(text)`** — `QApplication.clipboard().setText(text)`

**`_clipboard_has_files()`** — checks `QApplication.clipboard().mimeData().hasUrls()`

**`_on_new_folder(node)`**:
1. `QInputDialog.getText()` for folder name
2. Compute: `self._tree.to_container_path(node.path) + "/" + name`
3. Emit `createFolderRequested(container_path)`

**`_on_paste(node)`**:
1. Read `QApplication.clipboard().mimeData().urls()` → filter to files
2. Compute target: `self._tree.to_container_path(node.path)`
3. Emit `pasteFilesRequested(host_paths, target_container_path)`

---

## Step 4: `file_ops_ui.py` — New handlers

### 4a. `on_create_folder(container_path: str)`
```python
ctx = self._get_container_context()
container_name = ctx[0]
ensure_container_directories(container_name, [container_path])
# statusBar message on success, QMessageBox on failure
```

**Reuses:** `docker.container_ops.ensure_container_directories()` (line 641)

### 4b. `on_paste_files(host_paths: list, target_container_dir: str)`
```python
ctx = self._get_container_context()
container_name = ctx[0]
ensure_container_directories(container_name, [target_container_dir])
for host_path in host_paths:
    file_target = f"{target_container_dir}/{host_path.name}"
    push_file_to_container(container_name, host_path, file_target)
# statusBar summary: "Pasted N file(s)"
```

**Reuses:** `docker.container_ops.push_file_to_container()` (line 565), `ensure_container_directories()` (line 641)

**Paste is ephemeral** — files are NOT tracked in `pushed_files` (they may be from outside the project root). Container-only content, lost on recreate.

---

## Step 5: `app.py` — Wire signals (after line 342)

```python
self._scope_view.createFolderRequested.connect(fo.on_create_folder)
self._scope_view.pasteFilesRequested.connect(fo.on_paste_files)
```

---

## Menu Structure After Changes

```
ScopeView File RMB:
  Push / Sync / Pull / Remove    (existing, state-dependent)
  ─────────────
  Copy Path Container            (NEW)
  Copy Path Host                 (NEW)

ScopeView Folder RMB:
  Expand / Collapse              (existing)
  Expand All                     (existing)
  ─────────────
  Scan for New Files             (existing, disabled placeholder)
  ─────────────
  Copy Path Container            (NEW)
  Copy Path Host                 (NEW)
  ─────────────
  New Folder                     (NEW, needs running container)
  Paste                          (NEW, needs running container + clipboard files)
```

---

## Verification

1. Launch IgnoreScope, open project with running container
2. **Copy Path Container**: RMB file → Copy Path Container → paste in terminal → path is `/Projects/...` format
3. **Copy Path Host**: RMB file → Copy Path Host → paste → path is `E:\...` format
4. **New Folder**: RMB folder → New Folder → enter "test_dir" → statusbar confirms → `docker exec ls` shows folder
5. **Paste**: Copy file in Windows Explorer → RMB folder in ScopeView → Paste → statusbar confirms → file visible in container
6. **Disabled states**: Stop container → RMB folder → New Folder and Paste are grayed out
7. **No container**: Scope with no container created → Copy Path still works, New Folder/Paste disabled
