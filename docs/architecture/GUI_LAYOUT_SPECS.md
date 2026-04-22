# GUI Layout Specification

> **Purpose:** Build spec for the target GUI layout shell — no logic beyond color theme and layout persistence.
> **Supports:** `DATAFLOWCHART.md` Module Responsibility Map.
> **Layout change:** QSplitter-based fixed layout → QDockWidget-based docking. Panels can be dragged, floated, tabbed, and rearranged at runtime. `QMainWindow.saveState()`/`restoreState()` persists user layout preferences.
>
> **Widget hierarchy and sizing details** → `GUI_STRUCTURE.md`

---

## Section 1: Window Layout (QDockWidget-Based)

> **Widget hierarchy, objectNames, and sizing** → `GUI_STRUCTURE.md` Sections 1–2

### User Capabilities

- Drag any panel to a different dock area (top/bottom/left/right)
- Float a panel as an independent window
- Tab panels together (drag one onto another)
- Close/reopen panels via View menu
- Resize panels via dock splitter handles

### Layout Persistence

```python
# Save layout on close
settings = QSettings("IgnoreScope", "IgnoreScope")
settings.setValue("windowState", self.saveState())
settings.setValue("windowGeometry", self.saveGeometry())

# Restore on startup
if settings.contains("windowState"):
    self.restoreState(settings.value("windowState"))
    self.restoreGeometry(settings.value("windowGeometry"))
```

### View Menu (auto-generated from dock widgets)

```
View
├── "Folder Configuration"     (checkable — show/hide dock)
├── "Scope Configuration"      (checkable)
├── "Configuration (JSON)"     (checkable)
├── "Session History"          (checkable)
├── ─────────
└── "Reset Layout"             (restores default arrangement)
```

Each `QDockWidget.toggleViewAction()` provides a ready-made checkable QAction (4 dock toggles total).

---

## Section 2: MenuBar

### Structure (no action hookups)

```
QMenuBar
├── File
│   ├── "Open Project..."         Ctrl+O
│   ├── "Open Recent"             → submenu (empty)
│   ├── ─────────
│   ├── "Save Configuration"      Ctrl+S
│   ├── ─────────
│   └── "Exit"                    Ctrl+Q
├── Edit
│   ├── "Undo"                    Ctrl+Z
│   └── "Redo"                    Ctrl+Shift+Z
├── Scopes
│   ├── [dynamic scope list]      checkable radio
│   ├── ─────────
│   ├── "+ New Scope"
│   ├── "+ Duplicate Scope"
│   └── "Remove Scope Settings"
├── Docker Container
│   ├── "Create Container"
│   ├── "Update Container"
│   ├── "Recreate Container"
│   ├── ─────────
│   └── "Remove Container"
├── Container Extensions
│   ├── "Install Claude CLI"
│   └── "Install Git"
├── View
│   ├── "Folder Configuration"        checkable (toggleViewAction)
│   ├── "Scope Configuration"         checkable
│   ├── "Configuration (JSON)"        checkable
│   ├── "Session History"             checkable
│   ├── ─────────
│   └── "Reset Layout"               restores default dock arrangement
└── Tools
    ├── "Open Config Location"
    ├── ─────────
    ├── "Launch Container in Terminal"
    ├── "Launch LLM in Container"
    ├── ─────────
    └── "Export Container Structure..."
```

### Context-Sensitive Menus

| Menu / Item | Context Condition | Default State |
|-------------|-------------------|---------------|
| **Scopes** (entire menu) | Project loaded | Hidden |
| Scopes → scope list items | Populated by `list_containers()` | Empty |
| Scopes → "Remove Scope Settings" | Active scope selected | Disabled |
| **Docker Container** → all items | Project loaded + active scope | Disabled |
| **Edit** → Undo | Undo stack has items | Disabled |
| **Edit** → Redo | Redo stack has items | Disabled |
| **File** → "Save Configuration" | Project loaded | Disabled |
| **Tools** → "Open Config Location" | Project loaded | Disabled |
| **Container Extensions** → all items | Running container | Disabled |
| **Tools** → "Launch Container/LLM" | Running container | Disabled |
| **Tools** → "Export Container Structure" | Project loaded | Disabled |

---

## Section 3: Two Panel Sections

> **Widget hierarchy for both panels** → `GUI_STRUCTURE.md` Section 1

- **Left Panel — "Folder Configuration":** QTreeView with 5 columns (Local Host | Mount | Mask | Reveal | Pushed), StyleDelegate(LocalHostDisplayConfig)
- **Right Panel — "Scope Configuration":** QTreeView with 2 columns (Container Scope | Pushed), files + folders, StyleDelegate(ScopeDisplayConfig)

---

## Section 4: Folder Actions Section

> **Widget hierarchy** → `GUI_STRUCTURE.md` Section 1 (FolderActionsPanel removed — sibling management moved to Tools menu)

**Behavior owner:** Logic layer manages sibling add/remove via ConfigManager.
**Signal:** `removeSiblingRequested` on LocalHostView (context menu).

---

## Section 5: Scope Container Actions Section

> **Widget hierarchy** → `GUI_STRUCTURE.md` Section 1 (`configPanel` subtree)

**ContainerRootPanel** — Header frame + collapsible JSON viewer (bottom of scope splitter, 25%).
**Signal:** `openConfigLocationRequested` (RMB context menu on header).

---

## Section 6: Configuration (JSON) Panel

Now a **QDockWidget** instead of custom toggle/frame. The dock system provides show/hide (via View menu or close button), floating, and docking for free.

```python
QDockWidget("Configuration (JSON)")
└── QPlainTextEdit (read-only, objectName="configViewerText")
    ├── lineWrap: NoWrap
    ├── font: Consolas / Monaco / Courier New, 11px
    └── placeholder: "// No configuration loaded"
```

**Default:** Split right of Scope Configuration dock (`splitDockWidget`). User can close, float, or drag to any dock area.

**Public method:** `set_text(text: str)` — sets QPlainTextEdit content. Called by logic layer.

**Replaces:** `ConfigViewerToggleHorizontal` + `ConfigViewerContentHorizontal` — custom toggle mechanism no longer needed since QDockWidget provides native show/hide via View menu and title bar close button.

### Styling

- Dock title bar: styled via QSS `QDockWidget::title` — bg `ui.surface_bg`, text `ui.accent_primary`
- Content: bg `ui.window_bg`, text `ui.text_primary`

---

## Section 7: Status Bar

```python
QStatusBar
└── QLabel("No project loaded")
```

**Updated by logic layer to:** `"Project: {path}  |  Scope: {name}"`

---

## Section 8: Color Theme System

### Files

- `theme.json` — color definitions (6 sections, Nord palette)
- `style_engine.py` — `StyleGui` singleton
- `style_font.py` — font configuration

### theme.json Sections

| Section | Keys | Purpose |
|---------|------|---------|
| `palette` | 16 Nord colors | Base color definitions |
| `state_colors` | mounted, masked, revealed, etc. | Row gradient left stops. **Legacy — being replaced by tree_state_style.json. Retained during migration.** |
| `visibility_colors` | visible, virtual, hidden | Row gradient right stops. **Legacy — being replaced by tree_state_style.json. Retained during migration.** |
| `text` | project, exception, scope | Per-tree text colors. **Legacy — being replaced by tree_state_font.json / list_font.json. Retained during migration.** |
| `delegate` | selection_color/alpha, hover_color/alpha | Overlay colors |
| `ui` | window_bg, panel_bg, surface_bg, border, text_*, accent_* | Application widget colors |

### StyleGui API

| Method | Purpose | Used in Layout Phase? |
|--------|---------|----------------------|
| `instance()` | Singleton accessor | Yes |
| `build_stylesheet()` | QSS from ui tokens | Yes — applied to QMainWindow |
| `create_row_style(RowStyleInput)` | Cached row color computation. **Legacy — replaced by StateStyleClass lookup.** | No — needs trees/delegates |
| `build_gradient(GradientClass, color_vars, width)` | QLinearGradient construction (4-stop universal) | No — needs delegates |
| `selection_color()` | Overlay QColor | No — needs delegates |
| `hover_color()` | Overlay QColor | No — needs delegates |

### Application Stylesheet Coverage

QMainWindow, QDockWidget, QDockWidget::title, QTreeView, QHeaderView, QPushButton, QCheckBox, QLineEdit, QMenu, QMenuBar, QScrollBar, QStatusBar, QToolTip, QPlainTextEdit

### Critical QSS Rule

`QTreeView::item { background: none; }` — allows delegate gradients to show through.

### GradientClass (universal 4-position model)

GradientClass replaces the three legacy gradient types with a single model. Every gradient has exactly 4 positions with blended transitions:

```
GradientClass(pos1, pos2, pos3, pos4)    at positions 0.0, 0.25, 0.50, 0.75
```

Each argument is a **variable name** resolved from a style JSON file at paint time. Legacy types map as follows:

| Legacy Type | GradientClass Equivalent |
|-------------|--------------------------|
| `standard` | `GradientClass(left, left, right, right)` — pos1=pos2, pos3=pos4 |
| `dual_state` | `GradientClass(mounted, mounted, vis_or_state, masked)` — 4-arg, distinct per-state |
| `virtual` | `GradientClass(state, state, visibility, revealed)` — pos3≠pos4 |

See `GUI_STATE_STYLES.md` Section 1 for full specification including variable resolution pipeline.

### EXCEPTION Legacy Mapping

The old EXCEPTION context and its unique states are eliminated in the unified architecture:

- **EXCEPTION files** → now "Pushed" (`NodeState.pushed`). The `exception` flag (intent to push) is replaced by instant `docker cp` execution.
- **EXCEPTION folders** → now "Revealed" (`NodeState.revealed`). Folder state is panel-agnostic.
- **MatrixState** per-node-type states replace the old per-context approach. No `FileState` enum, no `pending_*` staging.

**SCOPE note:** `TreeContext.SCOPE` — defined with text colors in theme.json but currently unused by any view. The enum value and theme colors are retained during migration but not wired into the new style system.

See `GUI_STATE_STYLES.md` Section 8 for full legacy correspondence table.

---

## Section 9: Module Ownership Map

> Aligns with `DATAFLOWCHART.md` Module Responsibility Map. Each module header defines its boundary — what it IS and what it is NOT.

**Implementation rule:** When each `.py` file is created, the IS/IS NOT description below MUST be included as the module-level docstring at the top of the file. This ensures the boundary is enforced at the code level, not just in the spec.

---

### Layout Phase

**`app.py`** — Window Assembly
> Creates the QMainWindow, 4 QDockWidgets (local_host_dock, scope_dock, config_json_dock, history_dock), and status bar. Arranges docks using `addDockWidget` + `splitDockWidget` (scope/config_json right-split) and persists user arrangement via QSettings. Applies the application stylesheet from StyleGui. Does NOT contain business logic, signal routing to handlers, config loading/saving, or undo stack management.

**`system_tray.py`** — System Tray Icon
> Creates the QSystemTrayIcon with context menu: Show/Hide toggle and Exit.
> Manages tray-based window visibility toggle and application quit sequence
> (save layout, cleanup placeholder, hide tray, quit). Does NOT override
> QMainWindow.closeEvent (→ app.py), create menu bar entries (→ menus.py),
> or execute Docker operations directly (→ container_ops_ui.py).

**`menus.py`** — MenuBar Structure
> Builds the QMenuBar with File, Edit, Scopes, Docker, View, and Tools menus. Creates QActions with keyboard shortcuts and the View menu's dock toggleViewActions. Does NOT connect actions to handlers, implement context-sensitivity (enable/disable logic), or populate dynamic scope lists.

**`folder_actions.py`** — Folder Actions Panel
> Creates the Folder Actions panel widget: a QWidget containing an "Add Sibling" button and a vertical entries layout for sibling rows. Does NOT implement add/edit/remove handlers, spawn the SiblingDialog modal, scan the filesystem, or manage sibling config state.

**`container_root_panel.py`** — Container Actions Panel
> Creates the Container Root input widget: a label, QLineEdit with placeholder, and Show button in a horizontal layout. Does NOT validate container root values, execute Docker operations, or emit signals to the config manager.

**`style_engine.py`** — Color Theme Engine
> Singleton that loads theme.json, pre-builds QColor lookups for all 6 theme sections, generates the application QSS stylesheet, and constructs GradientClass instances from variable-resolved colors. Provides `build_gradient(GradientClass, color_vars, width)` for 4-stop universal gradient construction. Does NOT define visual states (those live in TreeDisplayConfig.state_styles), create widgets, interact with tree models, or manage application state. This is the ONLY layout-phase module with real logic.

**`style_font.py`** — Font Configuration
> Selects and configures the application font family (Consolas/Monaco/Courier New fallback). Does NOT handle text rendering, color assignment, or widget creation.

**`theme.json`** — Color Definitions (Data)
> Static JSON defining 6 color sections: palette (16 Nord colors), state_colors (row left gradients), visibility_colors (row right gradients), text (per-tree-context), delegate (overlay), ui (application widgets). Is data only — no code, no layout logic, no state.

**`tree_state_style.json`** — Tree Color Variables (Data)
> JSON mapping variable names to hex colors for tree panel GradientClass resolution. Variables: background, mounted, pushed, masked, revealed, visible, virtual, hidden, warning, selected. See `GUI_STATE_STYLES.md` Section 5.1. Is data only — no code, no logic.

**`tree_state_font.json`** — Tree Font Variables (Data)
> JSON mapping font variable names to font properties (weight, italic, text_color) for tree panel FontStyleClass resolution. Variables: default, muted, italic. See `GUI_STATE_STYLES.md` Section 6.1. Is data only — no code, no logic.

**`list_style.json`** — List Color Variables (Data)
> JSON mapping variable names to hex colors for list panel GradientClass resolution. Variables: background, selected, warning, destructive. See `GUI_STATE_STYLES.md` Section 5.2. Is data only — no code, no logic.

**`list_font.json`** — List Font Variables (Data)
> JSON mapping font variable names to font properties for list panel FontStyleClass resolution. Variables: default. See `GUI_STATE_STYLES.md` Section 6.2. Is data only — no code, no logic.

---

### Tree Phase

**`delegates.py`** — Row Painting
> GradientDelegate clears backgroundBrush to prevent Qt from overwriting gradients. StyleDelegate paints row gradients, text colors, and custom checkbox symbols — symbol rendering reads `ColumnDef.symbol_type` ("check", "pushed_status", None). References GradientClass and StateStyleClass from TreeDisplayConfig for state-driven gradient painting. HistoryDelegate (inherits GradientDelegate) paints Session History rows using HISTORY_ StateStyleClass entries from ListDisplayConfig. Does NOT compute state, access business data, or manage models.

**`display_config.py`** — TreeDisplayConfig Base + Subclasses
> TreeDisplayConfig base class with LocalHostDisplayConfig and ScopeDisplayConfig subclasses. Loads color/font variables from JSON files (`tree_state_style.json`, `tree_state_font.json`). Contains `state_styles: dict[str, StateStyleClass]` for MatrixState → visual lookup, `columns: list[ColumnDef]`, content filter booleans, and `undo_scope`. Subclasses override columns, filters, and undo_scope. Each config CAN point to different JSON files. See Section 10 for full specification. Does NOT store state, render UI, or interact with CORE.

**`mount_data_model.py`** — Qt Model Adapter
> Wraps MountDataTree + TreeDisplayConfig as a QAbstractItemModel for QTreeView. Translates Qt model API (index, data, flags, setData) to tree operations. Does NOT own state, compute visibility, or render — it's a pass-through adapter.

**`local_host_view.py`** — Left Panel (Folder Configuration)
> Sets up the QTreeView inside the Folder Configuration dock: assigns MountDataTreeModel + StyleDelegate(LocalHostDisplayConfig), configures header columns, and provides two RMB surfaces:
>
> - **Project Root Header RMB** (`_show_header_context_menu`) — targets `host_project_root` only. Exposes the Mount Delivery six-gesture state machine (see glossary → Mount Delivery Terms): Mount, Virtual Mount, Virtual Folder, Unmount, Convert to Virtual Mount / Convert to Mount, Remove Virtual Mount, Remove But Keep Children, and container-dependent actions (Remove Folder from Container, Remove Folder Tree from Container) when a container exists. Menu is always non-empty when a scope is loaded — at minimum Mount + Virtual Mount + Virtual Folder are offered when the root has no mount set.
> - **Tree Node RMB** (`_show_context_menu`) — targets selected node(s). Same six-gesture state machine as Project Root Header, scoped to the selected path(s). Mount / Virtual Mount / Virtual Folder visible only when `can_mount(path)` passes (no ancestor or descendant overlap with existing mount specs). Shift-select supports batch Remove across multiple Virtual Mount entries.
>
> Does NOT own the data model, manage state, or load configs.

**`scope_view.py`** — Right Panel (Scope Configuration)
> Sets up the QTreeView inside the Scope Configuration dock: assigns MountDataTreeModel + StyleDelegate(ScopeDisplayConfig), configures header columns, and provides file operations RMB menu. Does NOT own the data model, execute push/pull commands, or manage state.

**`session_history.py`** — Session History Panel
> Creates the Session History panel: QListView + HistoryModel (QAbstractListModel) + HistoryDelegate. References ListDisplayConfig for HISTORY_ state styles and color/font variable resolution. Displays chronological undo/redo entries from both panels interleaved. Each HistoryEntry carries `description`, `entry_type` (HistoryEntryType enum), and `is_current` (undo cursor position). Delegate reads entry_type + is_current → MatrixState resolution → HISTORY_ StateStyleClass. See Section 12 for full specification. Does NOT manage undo state, execute docker operations, or own the data — receives entries from undo.py.

**`list_display_config.py`** — List Panel Configuration
> ListDisplayConfig for Session History panel. Loads color/font variables from JSON files (`list_style.json`, `list_font.json`). Contains `state_styles: dict[str, StateStyleClass]` for HISTORY_ state lookup. See Section 12 for full specification. Does NOT store state, render UI, or interact with CORE.

---

### State Phase

**`mount_data_tree.py`** — Runtime State Host
> Hosts all runtime state: `_states` (mutable checkbox flags for editing), `_core_states` (frozen CORE NodeState cache with visibility), pushed/container file tracking, and sibling/virtual node subtrees. Emits `stateChanged` signal on mutation. Delegates visibility computation to CORE `node_state.py`. Does NOT render UI, create widgets, or interact with Qt views — it's a pure data model consumed by the Qt adapter.

---

### Logic Phase

**`config_manager.py`** — Orchestrator
> Coordinates project open, scope switch, and config save lifecycle. Connects signals between views, data tree, and CORE config. Manages busy dialogs during loading. Does NOT own state, render UI, or compute visibility.

**`container_ops_ui.py`** — Docker Operations UI
> Provides UI dialogs for container create/update/recreate/remove. Collects user confirmation and displays progress. Does NOT execute Docker commands directly (delegates to CORE container operations).

**`file_ops_ui.py`** — File Operations UI
> Handles file push/pull/remove signal routing from ScopeView's context menu. Does NOT execute `docker cp` directly — delegates to CORE file operations.

**`export_structure.py`** — Container Structure Export
> Generates indented text representation of container directory structure with visibility annotations. Pre-computes CORE states for all paths, then walks the tree. Does NOT interact with GUI widgets or manage state.

**`new_scope_dialog.py`** — New Scope Dialog
> Modal dialog that collects a scope name from the user. Validates against existing scope names. Does NOT create configs, write files, or switch scopes.

**`sibling_dialog.py`** — Sibling Edit Dialog
> Modal dialog for adding/editing sibling mounts: host path input (with browse), container path input, and a directory tree preview. Does NOT manage sibling state, save configs, or modify the data tree.

**`undo.py`** — Edit History (Two-Tier Model)
> Two-tier undo system. `undo_scope=full` (Folder Configuration): full undo/redo stack for Mount/Mask/Reveal checkbox state mutations, stores snapshots of `_states` dict before/after each edit action. `undo_scope=selection_history` (Scope Configuration): saves selection queues that had Push/Pull actions performed, does NOT reverse docker operations — destructive actions that triggered warning dialogs are not reversible. Does NOT handle config persistence or widget creation.

---

### Build Order

1. **Layout phase** — app.py (docks + persistence), menus.py (incl. View menu), folder_actions.py, container_root_panel.py + theme files + JSON data files (tree_state_style.json, tree_state_font.json, list_style.json, list_font.json)
2. **Tree phase:**
   - [x] delegates.py
   - [x] display_config.py
   - [x] mount_data_model.py
   - [x] local_host_view.py
   - [x] scope_view.py
   - [x] session_history.py
   - [x] list_display_config.py
3. **State phase** — [x] mount_data_tree.py (with CORE wiring)
4. **Logic phase** — config_manager.py, all operation/dialog modules, undo.py

---

## Section 10: DisplayConfig Specification

### A. Architecture: TreeDisplayConfig with Subclasses

TreeDisplayConfig is a base class. Per-panel variance lives in subclasses (LocalHostDisplayConfig, ScopeDisplayConfig). Each config loads color/font variables from JSON, contains a `state_styles` dict for MatrixState → visual lookup, and defines columns + filters.

```
TreeDisplayConfig (base)
├── state_styles: dict[str, StateStyleClass]
├── columns: list[ColumnDef]
├── content filters (booleans)
├── undo_scope: str
├── _color_vars: dict  ← from tree_state_style.json
├── _font_vars: dict   ← from tree_state_font.json
├── One-off color variables (class-level, not in gradient JSON):
│   ├── text_primary:    #ECEFF4  ← font text color for visible/active
│   ├── text_dim:        #616E88  ← font text color for hidden/muted
│   ├── text_warning:    #D08770  ← font text color for orphaned
│   ├── hover_color:     #4C566A  ← delegate hover overlay
│   ├── hover_alpha:     60       ← delegate hover overlay alpha
│   └── selection_alpha: 100      ← delegate selection overlay alpha
│
├── LocalHostDisplayConfig
│   └── overrides: columns, filters, undo_scope="full"
│
└── ScopeDisplayConfig
    └── overrides: columns, filters, undo_scope="selection_history"
```

One-off variables are hex colors used in rendering that don't correspond to gradient state variables. Font JSONs reference them by name (variable indirection). JSON storage format for these variables is deferred — first pass stores them as class-level definitions. See `GUI_STATE_STYLES.md` Section 6.3.

One-off values live in subclasses. Each config CAN point to different JSON files.

```
Panel (dock widget)
└── QTreeView
    ├── MountDataTreeModel(data_tree, config)
    │                          │
    │                  LocalHostDisplayConfig or ScopeDisplayConfig
    │                  ├── state_styles dict (MatrixState → StateStyleClass)
    │                  ├── _color_vars / _font_vars (from JSON)
    │                  ├── content filters (booleans)
    │                  └── columns: list[ColumnDef]
    │
    └── StyleDelegate(config)
```

### B. ColumnDef Fields

| Field | Type | Purpose |
|-------|------|---------|
| `header` | str | Column heading text |
| `visible` | bool | Column shown/hidden |
| `width` | int \| "stretch" | Fixed pixels or stretch to fill |
| `checkable` | bool | Interactive checkbox (True) or display-only (False) |
| `check_field` | Optional[str] | NodeState field name bound to checkbox |
| `enable_condition` | Optional[str] | Method name on data tree for enable/disable validation |
| `cascade_on_uncheck` | list[str] | Fields to auto-clear when this column unchecked |
| `files_only` | bool | Checkbox restricted to file nodes |
| `symbol_type` | Optional[str] | Visual symbol: "check", "pushed_status", None |

### C. Content Filtering Flags

| Flag | Type | Description |
|------|------|-------------|
| `display_files` | bool | Show file nodes |
| `display_hidden` | bool | Show nodes with visibility=hidden |
| `display_non_mounted` | bool | Show folders with no mount ancestor |
| `display_masked_dead_branches` | bool | Show masked folders with no revealed content |
| `display_stencil_nodes` | bool | Show stencil nodes (auth volume, LLM configs) |
| `display_orphaned` | bool | Show orphaned nodes (pushed + masked + mount removed) |

### D. Per-Panel Defaults

| Setting | Folder Configuration | Scope Configuration |
|---------|---------------------|---------------------|
| config_class | `LocalHostDisplayConfig` | `ScopeDisplayConfig` |
| display_files | False | True |
| display_hidden | True | False |
| display_non_mounted | True | False |
| display_masked_dead_branches | True | False |
| display_stencil_nodes | False | True |
| display_orphaned | True | True |
| undo_scope | full | selection_history |

### E. Column Definitions

**Folder Configuration:**

| Col | header | width | checkable | check_field | enable_condition | cascade_on_uncheck | symbol_type |
|-----|--------|-------|-----------|-------------|------------------|--------------------|-------------|
| 0 | "Local Host" | stretch | False | — | — | — | — |
| 1 | "Mount" | 70 | True | "mounted" | can_check_mounted | masked, revealed | "check" |
| 2 | "Mask" | 70 | True | "masked" | can_check_masked | revealed | "check" |
| 3 | "Reveal" | 70 | True | "revealed" | can_check_revealed | — | "check" |

**Scope Configuration:**

| Col | header | width | checkable | check_field | enable_condition | cascade_on_uncheck | symbol_type |
|-----|--------|-------|-----------|-------------|------------------|--------------------|-------------|
| 0 | "Container Scope" | stretch | False | — | — | — | — |
| 1 | "Push" | 80 | True | "pushed" | can_push | — | "pushed_status" |

### F. GradientClass

Universal 4-position gradient model used by all tree states:

```
GradientClass(pos1, pos2, pos3, pos4)    at positions 0.0, 0.25, 0.50, 0.75
```

Each argument is a **variable name** resolved from the config's `_color_vars` (loaded from `tree_state_style.json`). Blended transitions between all 4 positions. Replaces the old `standard`/`dual_state`/`virtual` gradient type branching.

See `GUI_STATE_STYLES.md` Section 1 for full specification.

### G. StateStyleClass + FontStyleClass

```
StateStyleClass(GradientClass, FontStyleClass)
```

Complete visual recipe for one node state. GradientClass defines the 4-stop background gradient, FontStyleClass defines text weight/italic/color. Stored in `TreeDisplayConfig.state_styles` dict keyed by state name.

**Selected override:** When a node is selected, pos2 and pos3 of its GradientClass are replaced with the `selected` variable. pos1 and pos4 retain the base state's values, preserving node identity.

See `GUI_STATE_STYLES.md` Section 2 for full specification.

### H. State Enumeration

22 tree states (14 folder + 8 file) + 2 selected overrides. Each state has a GradientClass and FontStyleClass, derived from visibility STATE + boolean METHOD flags.

Folder states resolved by `_resolve_folder_state()`: visibility + masked + revealed + is_mount_root + stencil_tier + has_visible_descendant.
File states resolved by `_resolve_file_state()`: visibility + container_only + container_orphaned + revealed + pushed + host_orphaned + masked.
GUI uses if/elif resolution chains — no tree walking.

See `GUI_STATE_STYLES.md` Section 3 for the full state tables.

**User-confirmed example:**

```
FOLDER_MASKED_REVEALED = StateStyleClass(
    GradientClass(masked, masked, hidden, revealed),
    FontStyleClass(default)
)
```

### I. JSON File References

| File | Purpose | Variable Count |
|------|---------|---------------|
| `tree_state_style.json` | Color variables for tree GradientClass resolution | 10 (background, mounted, pushed, masked, revealed, visible, virtual, hidden, warning, selected) |
| `tree_state_font.json` | Font variables for tree FontStyleClass resolution | 3 (default, muted, italic) |

See `GUI_STATE_STYLES.md` Sections 5–6 for full variable → hex tables.

### J. Variable Resolution Flow

```
NodeState (per-node + tree-context fields)
    → Truth table lookup → state name
        Folders: visibility + has_pushed_descendant + has_direct_visible_child
        Files:   visibility + pushed + host_orphaned
    → TreeDisplayConfig.state_styles[state_name] → StateStyleClass
        ├── GradientClass(var1, var2, var3, var4)
        │       → _color_vars[var] → hex → QColor
        │       → QLinearGradient(0.0, 0.25, 0.50, 0.75)
        │
        └── FontStyleClass(font_var)
                → _font_vars[font_var] → weight, italic, text_color
```

See `GUI_STATE_STYLES.md` Section 7 for the full paint-time pipeline diagram.

---

## Section 11: Unified Interaction Model

### A. Design Principle: BehaviorsVisible == ColumnVisual

Checkboxes ARE the state actions. Each checkable column directly toggles the NodeState field it's bound to. The old RMB duplicate actions (Mount/Mask/Reveal, Push/Pull/Update/Remove) are replaced by checkbox interaction.

### B. Checkbox States (3 Visual Modes)

| Visual | State | Interaction |
|--------|-------|-------------|
| ☑ / ☐ | Valid | Normal checkbox — click to toggle |
| Greyed ☐ | Invalid (single) | Disabled — enable_condition returns False. Cannot interact. |
| Muted red [x] | Invalid (multi-select) | NOT a checkbox. Visual marker showing this action conflicts with current selection. Cannot interact. |

### C. Checkbox Validation Flow

```
User clicks checkbox (or selects multiple then clicks)
    ↓
For each selected node:
    ├── Checking ON: validate enable_condition → reject if False
    └── Unchecking OFF: always allow (user must be able to fix invalid state)
    ↓
Apply state change + cascade_on_uncheck
    ↓
stateChanged signal → both panels refresh
```

Universal rule: validate on check, skip validation on uncheck.

### C2. Destructive Action Confirmation

Unchecking a Push checkbox triggers file deletion from the container. This requires a confirmation dialog:

```
Dialog Title: "Warning:Push"
Dialog Body:  "Delete Push Files"
Buttons:      [Delete] [Cancel]
```

Rule: Any checkbox uncheck that triggers a destructive docker operation (file removal) shows a warning dialog. The operation only proceeds on explicit "Delete" confirmation.

### C3. Two-Tier Undo Model

| Panel | undo_scope | Behavior |
|-------|-----------|----------|
| Folder Configuration | `full` | Full undo/redo stack for Mount/Mask/Reveal state changes |
| Scope Configuration | `selection_history` | Saves selection queues that had actions performed (what was pushed/pulled). Does NOT reverse docker operations. Destructive actions that triggered warning dialogs are not reversible. |

Purpose of selection_history: Allows user to recall which nodes had Push/Pull performed, supporting re-selection and awareness without implying the docker operation itself can be undone.

### D. Multi-Selection Checkbox Behavior

1. User selects multiple nodes (Ctrl/Shift click)
2. Validation runs across ALL selected nodes
3. Checkbox columns show state for multi-selection:
   - All selected nodes have it checked → ☑
   - All selected nodes have it unchecked → ☐
   - Mixed → indeterminate
   - Any node in selection can't accept this action → muted red [x] for that column

### E. Unified RMB Menu (Shared Code, Both Panels)

RMB content is derived from selection type, NOT from panel identity.

**Gate rule:** If `display_files=False`, all file-interactive behaviors are disabled in that panel, including "Pull All Files from Folder(s)".

**Exception:** Even with `display_files=False`, orphan validation still runs. If an action would create orphaned files (pushed + masked + mount removed), a Deletion Warning Dialog is shown regardless of the display_files setting.

```
Selection analysis:
├── only_folders: bool
├── only_files: bool
├── display_files: bool (from TreeDisplayConfig)
├── has_pushed_or_orphaned_in_folders: bool
└── has_pushed_files: bool

Menu construction:
├── If only_folders:
│   ├── "Expand"
│   ├── "Collapse"
│   └── If display_files AND has_pushed_or_orphaned_in_folders:
│       └── "Pull All Files from Folder(s)"
│
└── If only_files AND display_files:
    └── "Pull File(s)"
```

One menu builder. Both panels. RMB never duplicates checkbox actions.

### F. Per-Panel RMB Behavior (Naturally Derived)

| Panel | display_files | Typical Selection | RMB Shows |
|-------|--------------|-------------------|-----------|
| Folder Configuration | False | Folders | Expand, Collapse (no file actions) |
| Scope Configuration (folder) | True | Folders | Expand, Collapse, [Pull All if pushed inside] |
| Scope Configuration (file) | True | Files | Pull File(s) |

### G. LocalHost Tree RMB — Six-Gesture Delivery State Machine (Phase 3 Task 4.7)

The LocalHost Tree RMB and Project Root Header RMB share a single helper, `_add_delivery_gestures(menu, path)`, keyed off `is_in_raw_set("mounted", path)` / `is_in_raw_set("detached_mounted", path)`. Header invocation falls back to a disabled "No valid actions" entry when the gesture set is empty (Phase 2 silent-no-op fix).

Gesture matrix (NONE state offers all three host-backed creation gestures; existing-spec states surface tier conversions and removals):

| State | Predicate | Gestures Offered | Schema Effect |
|---|---|---|---|
| NONE | `not is_bind and not is_detached` and `can_mount(path)` | Mount • Virtual Mount • Virtual Folder | `toggle_mounted` (bind/tree) • `toggle_detached_mount` (detached/tree) • `toggle_detached_folder_mount` (detached/folder, host-backed) |
| BIND_MOUNTED | `is_bind` | Unmount • Convert to Virtual Mount | `toggle_mounted(path, False)` • `convertDeliveryRequested.emit(path, "detached")` |
| DETACHED_MOUNTED | `is_detached` | Remove Virtual Mount • Convert to Mount • Remove But Keep Children • (container-only) Remove Folder from Container • Remove Folder Tree from Container | `toggle_detached_mount(path, False)` • `convertDeliveryRequested.emit(path, "bind")` • `remove_but_keep_children` • container removal signals |

Virtual Folder produces a host-backed folder-seed spec (`delivery="detached", content_seed="folder", host_path=mount_root`). The container side mkdir's at create time without a cp walk; content is filled via `pushed_files` or inside-container writes. Distinct from Scope Config "Make Folder" (Section H), which is container-only (`host_path=None`).

### H. Scope Config Tree RMB — Stencil Gesture State Machine (Phase 3 Task 4.6)

The Scope Config Tree RMB surfaces container-only folder gestures with no LocalHost analogue. Parallels the LocalHost six-gesture state machine but is keyed off the `MountSpecPath.delivery` + `content_seed` + `preserve_on_update` triple rather than host-backed tier checks. Header RMB follows the Phase 2 silent-no-op fix pattern (disabled "No valid actions" when empty).

Gesture matrix:

| Click Target | Gestures Offered | Schema Effect |
|---|---|---|
| Empty viewport area | Make Folder, Make Permanent Folder ▸ (No Recreate / Volume Mount) | `add_stencil_folder` (→ detached/folder) or `add_stencil_volume` (→ volume/folder) |
| Non-spec folder node | Same as empty area | Same as empty area |
| Existing detached+folder spec (`preserve_on_update=False`) | Mark Permanent • Remove | `mark_permanent` flips flag; `remove_spec_at` drops the spec |
| Existing detached+folder spec (`preserve_on_update=True`) | Unmark Permanent • Remove | `unmark_permanent` flips flag; `remove_spec_at` drops the spec |
| Existing volume spec (`delivery="volume"`) | Remove | `remove_spec_at` drops the spec — no mid-tier transitions supported in Phase 3 |
| File node | File gestures (Push/Sync/Pull/Remove) — unchanged | — |

Dialog contracts:

- **Make Folder / No Recreate / Volume Mount**: `QInputDialog.getText` prompts for the container-side absolute path; empty / whitespace / cancel → no-op.
- **Volume Mount when container exists**: `QMessageBox.question` recreate-confirmation gate. On Yes, spec is appended and `ScopeView.recreateRequested` signal fires for the app layer to call `execute_update`.

Parity notes vs LocalHost RMB:

- LocalHost gestures run in `_add_delivery_gestures(menu, path)` keyed off `is_in_raw_set("mounted", path)` / `is_in_raw_set("detached_mounted", path)`. ScopeView gestures run in `_add_scope_config_gestures(menu, node)` keyed off `self._tree.get_spec_at(node.path)` — exact-match only at the `mount_root` boundary.
- Both views append disabled "No valid actions" via a `_append_fallback_if_empty` / equivalent helper so RMB is always discoverable.
- ScopeView exposes a new `recreateRequested` signal (no LocalHost analogue — bind/detached conversions use the existing `convertDeliveryRequested` path). Volume Mount is the only scope-side gesture that triggers a container recreate.

---

## Section 12: Session History Panel

### A. Widget Architecture

```
history_dock (QDockWidget "Session History")
└── QListView
    ├── HistoryModel (QAbstractListModel)
    │   └── items: list[HistoryEntry]
    │       ├── description: str
    │       ├── entry_type: HistoryEntryType enum
    │       └── is_current: bool (undo cursor position)
    │
    └── HistoryDelegate (inherits GradientDelegate)
        └── reads entry_type + is_current → selects gradient state
```

### B. Widget Choice

QListView + custom delegate (not QPlainTextEdit). Rationale: per-row gradient painting requires delegate control. Follows existing GradientDelegate pattern from tree views.

### C. HISTORY_ State Declarations (GradientClass + StateStyleClass)

5 states using the universal GradientClass model. Each variable name resolves via `list_style.json`.

```python
HISTORY_NORMAL = StateStyleClass(
    GradientClass(background, background, background, background),
    FontStyleClass(default)
)  # No undos in queue, or entry outside undo range

HISTORY_UNDO_CURRENT = StateStyleClass(
    GradientClass(selected, selected, background, background),
    FontStyleClass(default)
)  # Non-destructive entry at current undo cursor

HISTORY_REDO_AVAILABLE = StateStyleClass(
    GradientClass(warning, background, background, background),
    FontStyleClass(default)
)  # Entry above cursor (available for redo)

HISTORY_DESTRUCTIVE = StateStyleClass(
    GradientClass(background, background, destructive, destructive),
    FontStyleClass(default)
)  # Destructive action (Push uncheck, file removal), not at cursor

HISTORY_DESTRUCTIVE_SELECTED = StateStyleClass(
    GradientClass(selected, background, destructive, destructive),
    FontStyleClass(default)
)  # Destructive action at current cursor position
```

These ARE the full spec — HISTORY_ states are inline here, not in `GUI_STATE_STYLES.md` (which also lists them for cross-reference). The 4-stop positions are 0.0, 0.25, 0.50, 0.75 with blended transitions.

### D. ListDisplayConfig + JSON Files

ListDisplayConfig replaces the old `history_gradients` theme.json section. Color and font variables live in dedicated JSON files, matching the tree panel pattern.

```
ListDisplayConfig
├── state_styles: dict[str, StateStyleClass]   ← 5 HISTORY_ states from Section 12C
├── _color_vars: dict   ← from list_style.json
├── _font_vars: dict    ← from list_font.json
└── One-off color variables (class-level):
    └── text_primary: #ECEFF4  ← font text color for history entries
```

**list_style.json:**

```json
{
    "background":   "#3B4252",
    "selected":     "#5E81AC",
    "warning":      "#EBCB8B",
    "destructive":  "#BF616A"
}
```

**list_font.json:**

```json
{
    "default": { "weight": "normal", "italic": false, "text_color": "text_primary" }
}
```

All `text_color` values use **variable indirection** — the string `"text_primary"` is resolved via ListDisplayConfig's base class variables, not used as a direct hex.

**Migration from old dotted-path references:**

| Old Reference | New Variable | Hex |
|---------------|-------------|-----|
| `ui.panel_bg` | `background` | #3B4252 |
| `ui.accent_secondary` | `selected` | #5E81AC |
| `palette.yellow` | `warning` | #EBCB8B |
| `palette.red` | `destructive` | #BF616A |

### E. Interaction with Two-Tier Undo

**MatrixState resolution** (entry_type × is_current × cursor position → HISTORY_ state):

| entry_type | is_current | above_cursor | → State |
|------------|-----------|-------------|---------|
| normal | False | False | `HISTORY_NORMAL` |
| normal | True | — | `HISTORY_UNDO_CURRENT` |
| normal | False | True | `HISTORY_REDO_AVAILABLE` |
| destructive | False | False | `HISTORY_DESTRUCTIVE` |
| destructive | True | — | `HISTORY_DESTRUCTIVE_SELECTED` |
| destructive | False | True | `HISTORY_REDO_AVAILABLE` |

**Source panel mapping:**

| Source Panel | Entry Type | HISTORY_ States Available |
|-------------|------------|--------------------------|
| Folder Configuration (`undo_scope=full`) | Mount/Mask/Reveal changes | HISTORY_NORMAL, HISTORY_UNDO_CURRENT, HISTORY_REDO_AVAILABLE |
| Scope Configuration (`undo_scope=selection_history`) | Push/Pull actions | HISTORY_DESTRUCTIVE, HISTORY_DESTRUCTIVE_SELECTED, HISTORY_REDO_AVAILABLE |

Session History displays entries from BOTH panels interleaved chronologically. Each entry carries its source panel so the delegate knows which entry_type applies.
