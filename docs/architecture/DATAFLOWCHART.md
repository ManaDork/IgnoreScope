# GUI Data Flow Chart

> **Communication Reference** — canonical data flow for IgnoreScope GUI.
> All code changes must respect this flow. If reality diverges, update the code, not this chart.
>
> CORE flow reference: `COREFLOWCHART.md` (Phases 7-8 are shared cross-domain concepts; Phases 1-6 are domain-specific pipelines)
> State model: 22 states (14 folder + 8 file) + 2 overrides — see `GUI_STATE_STYLES.md` Section 3

---

## Root Concepts

| Name | Side | Example | Stored In Config |
|------|------|---------|------------------|
| `host_project_root` | Host | `E:\Projects\MyGame\` | Implicit (user opens this folder) |
| `host_container_root` | Host | `E:\Projects\` | Ancestor containing project + siblings — all `relative_to()` base |
| `container_root` | Container | `/Projects` | `scope_docker.json` (default: `/{host_container_root.name}`) |
| `local_host_root` | Host | `E:\Projects\` | Stored reference for future scanning — NOT used for path computation |

> **`local_host_root` vs `host_container_root`:** These may coincide by default (both = `host_project_root.parent`) but serve different purposes. `host_container_root` is the `relative_to()` base for **container path computation** (all volume entries, docker cp paths). `local_host_root` is a **stored reference** for a future "scan all children" feature. Config paths in JSON remain relative to `host_project_root` (Rule 10); `host_container_root` is only used at computation time.

### Constraints
- `host_container_root` MUST be an ancestor of (or equal to) `host_project_root`
- `local_host_root` is NOT scanned by default — only a stored reference
- Default: `host_container_root` = `host_project_root.parent` — project name naturally included in container paths
- `sibling.host_path` is absolute (siblings can be anywhere on the OS)
- No full drive paths in config — `local_host_root` stored as relative path from `host_project_root`
- `.{project}_igsc/` auto-masked to prevent config dir appearing in container

### Root Mapping: Host ↔ Container

```
HOST                                      CONTAINER
─────────────────────────────             ──────────────────────────
E:\Projects\        ← host_container_root /Projects/        ← container_root
│                     (all relative_to()  │                    (default: /{host_container_root.name})
│                      base — mapped      │
│                      into container)    │
├── MyGame\         ← host_project_root   ├── MyGame\       ← {container_root}/{project_offset}
│   ├── src/                              │   ├── src/         project_offset = host_project_root
│   └── lib/                              │   └── lib/           .relative_to(host_container_root)
│                                         │
├── .MyGame_igsc\   ← AUTO-MASKED         │   (hidden — never in container)
│   └── .dev/                             │
│       └── scope_docker.json             │
│                                         │
C:\SharedLibs\      ← sibling.host_path   ├── SharedLib\    ← sibling.container_path
│   └── common/       (absolute, any      │   └── common/     (parallel at top level)
│                      location on OS)    │
                                          └── .claude\      ← virtual (auth volume)

Default: host_container_root = host_project_root.parent, project_offset = host_project_root.name.
```

---

## Data Flow Pipeline

```
PHASE 1: OPEN PROJECT
──────────────────────────────────────────────────────────────

    User opens host_project_root (e.g. via File Dialog)
            │
            ├── Scan adjacent for .{project}_igsc/
            │
            ├── IF scope_docker.json EXISTS:
            │       local_host_root = host_project_root / config.local_host_root
            │       (resolved from relative path in JSON)
            │
            ├── IF NO config:
            │       local_host_root = host_project_root.parent  (default)
            │
            ▼


PHASE 2: SCAN
──────────────────────────────────────────────────────────────

    BY DEFAULT: Only host_project_root is scanned here.
    Siblings are scanned in Phase 3 after config load.
    local_host_root is stored but NOT scanned unless configured.

    GetFilesFromOS(host_project_root)
            │
            ▼
    MountDataTree              ← No State Information Yet                                
                                 


PHASE 3: CONFIG
──────────────────────────────────────────────────────────────

    MountConfig = LoadConfig(scope_docker.json)
            │
            │   Siblings are NOT known until JSON is read.
            │   Virtual volumes are NOT known until JSON is read.
            │
            ├── FOR EACH sibling in JSON:
            │       MountDataTree.append(
            │           GetFilesFromOS(sibling.host_path)
            │       )                     ← each sibling scanned from its absolute path
            │
            ├── MountDataTree.append(
            │       GetVirtualNodes(MountConfig)
            │   )                         ← auth volume, future LLM configs
            │
            ▼


PHASE 4: BUILD (state markup + visibility — no actions taken)
──────────────────────────────────────────────────────────────

    MountDataTree = BuildDataTree(ProjectHostStructure, MountConfig)
            │
            │   MARKS UP nodes with ALL NodeState from config.
            │   This is state tagging only — no Docker actions,
            │   no cosmetic rendering, no side effects.
            │
            │   What happens here:
            │     - Tags nodes with state flags from scope_docker.json
            │       (mounted, masked, revealed, pushed, orphaned)
            │     - Stage 1: Computes per-node visibility via MatrixState
            │       (orphaned / revealed / masked / visible / hidden)
            │       See: core/node_state.py — compute_visibility()
            │     - Stage 2: Computes tree-aware visibility via descendant walk
            │       (virtual = effectively masked + has revealed descendant)
            │       See: COREFLOWCHART.md Phase 3
            │     - Populates _states: Dict[Path, NodeState]
            │     See: COREFLOWCHART.md Phase 3 (Apply Node State)
            │     See: ARCHITECTUREGLOSSARY.md (NodeState definition)
            │
            │   What does NOT happen here:
            │     - No Docker volumes created
            │     - No cosmetic rendering (gradients, colors — that's Phase 5)
            │     - No files pushed/pulled
            │
            ▼


PHASE 5: DISPLAY (cosmetic feedback from NodeState)
──────────────────────────────────────────────────────────────

    Phase 4 NodeState (including visibility) MUST cover all inputs
    required by the cosmetic feedback system.
    Phase 5 does NOT compute visibility — it reads it from NodeState.
    Phase 5 derives COSMETIC rendering only: gradients, text colors,
    checkbox enable/disable.
    See: GUI_STATE_STYLES.md Section 3 (state truth tables)
    See: COREFLOWCHART.md (domain ownership — UI vs CORE)

    DisplayDataTree uses displayConfig to filter and apply displayed
    information from Node.States (mounted, masked, revealed, visible,
    hidden, pushed, orphaned). Derives cosmetic UX feedback from
    Node.states matrix: gradients, text colors, checkbox enable/disable.

    ONE shared MountDataTree
            │
            ├──────────────────────────┐
            ▼                          ▼
    DisplayDataTree(               DisplayDataTree(
      MountDataTree,                 MountDataTree,
      LocalHostDisplayConfig)        ScopeDisplayConfig)
            │                          │
            ▼                          ▼
    ┌─────────────────────┐    ┌──────────────────────────┐
    │  Local Host Panel   │    │  Scope Container Panel   │
    │  (Left)             │    │  (Right)                 │
    │                     │    │                          │
    │  project_root +     │    │  Filtered by config:     │
    │  declared siblings  │    │  - Hidden nodes removed  │
    │  Folders only       │    │  - Files shown           │
    │  No virtual nodes   │    │  - Virtual nodes shown   │
    │                     │    │                          │
    │  Columns:           │    │  Columns:                │
    │  Name|Mount|Mask|   │    │  Container View|Pushed   │
    │      Reveal         │    │                          │
    └─────────────────────┘    └──────────────────────────┘
```
---

## State Change Flow (Phase 7 → Phase 8 detail)

```
User clicks checkbox (LocalHostView)
    │
    ▼
MountDataTreeModel.setData()
    │
    ▼
DisplayConfig.handle_set_data(tree, node, col_def, checked, state)
    │
    ├── Validates: enable_condition (can_check_mounted, etc.)
    ├── Mutates: MountSpecPath pattern operations (mounted/masked/revealed)
    ├── Cascades on uncheck:
    │     Mount removed → remove entire MountSpecPath (all patterns)
    │     Mask removed  → remove deny pattern + filter descendant patterns
    │     Reveal removed → remove exception pattern only
    │
    ▼
MountDataTree.stateChanged.emit()        ← SINGLE BROADCAST
    │
    ├──► LocalHostView refreshes          ← same tree, different filter
    ├──► ScopeView refreshes              ← same tree, different filter
    └──► ConfigViewer updates             ← JSON preview
```

---

## File Operations Flow (Phase 7 → Phase 8 detail, ScopeView)

> File operations flow through CORE orchestrators in `docker/file_ops.py`.
> Types: `core/op_result.py` (OpError, OpWarning, OpResult, BatchFileResult).
> GUI and CLI are consumers — CORE owns validation, path resolution, and docker calls.

### Target Architecture (CORE Orchestrator)

File operations use a **preflight/execute** two-phase pattern:
1. **Preflight** — validate all preconditions, return errors (blocking) and warnings (confirmable)
2. **Execute** — perform the docker cp / rm, return success/failure

Types defined in `core/op_result.py`: `OpError` (blocking), `OpWarning` (confirmable), `OpResult` (standardized return).

```
SINGLE FILE FLOW:

User RMB clicks file in ScopeView
    │
    ▼
Context menu: Push / Update / Pull / Remove
    │
    ▼
ScopeView emits signal (pushRequested, pullRequested, etc.)
    │
    ▼
FileOperationsHandler.on_push(path)
    │
    ├── GUI: _get_container_context()         ← resolve names from app state
    │
    ├── CORE: preflight_push(path, ...)       ← validates ALL preconditions
    │     │
    │     ├── Errors? → GUI shows error dialog, STOP
    │     └── Warnings? → GUI shows confirm dialog per warning
    │           └── User declines? → STOP
    │
    ├── CORE: execute_push(path, ..., force=True)
    │     │
    │     ├── Resolves: container_path via resolve_container_path()
    │     ├── Ensures: parent dirs via ensure_container_directories()
    │     ├── Executes: docker cp host_path container:container_path
    │     └── Returns: OpResult (success/failure + message)
    │
    ├── GUI: MountDataTree.add_pushed(path)   ← state refresh (GUI owns tree instances)
    ├── GUI: ConfigManager.save_config()      ← persist
    └── GUI: statusBar message                ← UX feedback


BATCH FILE FLOW (multi-select or folder):

User RMB clicks selection/folder in ScopeView
    │
    ▼
FileOperationsHandler.on_push_batch(paths)
    │
    ├── CORE: preflight_push_batch(paths, ...)   ← validate ALL files upfront
    │     │
    │     └── Returns: BatchFileResult
    │           ├── errors: {path: OpResult}      ← blocked files (show summary)
    │           ├── warnings: {path: OpResult}    ← confirmable files
    │           └── clean: [path]                 ← ready to execute
    │
    ├── GUI: show error summary (if any)
    ├── GUI: show warning summary + confirm (if any)
    │
    ├── CORE: execute_push_batch(confirmed_paths, ..., force=True)
    │     └── Returns: {path: OpResult}           ← per-file results
    │
    ├── GUI: batch tree update + single save_config()
    └── GUI: status summary


CLI EQUIVALENT:

cmd_push(host_project_root, scope_name, files, force=False)
    │
    ├── CORE: preflight_push_batch(paths, ...)
    │     ├── Errors → print + exit
    │     └── Warnings + no --force → print + "Use --force to override"
    │
    ├── CORE: execute_push_batch(paths, ..., force=True)
    ├── Update config: pushed_files.add() + save_config()
    └── Print results
```

### Scope Config Tree RMB — Stencil Gesture Flow (Phase 3 Task 4.6)

The Scope Config Tree RMB mutates `MountDataTree._mount_specs` directly (parallel to LocalHost's `toggle_mounted` / `toggle_detached_mount` flow) rather than going through a Handler class. Empty-area clicks and stencil-spec clicks both dispatch via `ScopeView._add_scope_config_gestures`.

```
User RMB on empty area or stencil spec node in ScopeView
    │
    ▼
ScopeView._show_context_menu(pos)
    ├── indexAt(pos) invalid? → _add_scope_config_gestures(node=None)
    └── single folder + spec exists? → _add_scope_config_gestures(node=<spec-node>)
         │
         ▼
    State machine picks menu entries based on spec.delivery / content_seed / preserve_on_update:
         │
         ├── Empty area → Make Folder / Make Permanent Folder ▸ (No Recreate | Volume Mount)
         ├── detached+folder+!preserve → Mark Permanent | Remove
         ├── detached+folder+preserve  → Unmark Permanent | Remove
         └── volume                    → Remove
    │
    ▼
User triggers gesture
    │
    ├── Make Folder / No Recreate / Volume Mount
    │     │
    │     ├── QInputDialog.getText → container-side Path (cancel/empty = no-op)
    │     ├── (Volume Mount + container exists) → QMessageBox.question recreate gate
    │     ├── MountDataTree.add_stencil_folder(path, preserve_on_update=...)
    │     │     or .add_stencil_volume(path)
    │     │         │
    │     │         ├── overlap guard → False (no-op) on collision with existing spec
    │     │         ├── aboutToMutate.emit()  ← undo snapshot
    │     │         ├── append MountSpecPath(delivery=..., host_path=None, ...)
    │     │         ├── _recompute_states()   ← CORE apply_node_states_from_scope
    │     │         └── mountSpecsChanged.emit()
    │     │
    │     └── (Volume Mount only) ScopeView.recreateRequested.emit()
    │           └── App.on_recreateRequested → execute_update pipeline
    │
    ├── Mark Permanent / Unmark Permanent
    │     └── MountDataTree.mark_permanent(path) / .unmark_permanent(path)
    │           (aboutToMutate → flip flag → recompute → mountSpecsChanged)
    │
    └── Remove
          └── MountDataTree.remove_spec_at(path)
                (aboutToMutate → pop spec → recompute → mountSpecsChanged)

    │
    ▼
ConfigManager (listens to MountDataTree.mountSpecsChanged)
    └── scopeConfigChanged.emit()  ← app-level persist trigger
```

**Key invariants for scope-side RMB:**

- Mutations always emit `aboutToMutate` before changing state (undo snapshot guarantee).
- `host_path=None` is the single indicator of container-only provenance — enforced by `add_stencil_folder` / `add_stencil_volume`, cross-checked by validators in `MountSpecPath.validate`.
- Volume Mount is the only scope-side gesture that emits `recreateRequested`; all others are config-only mutations that downstream execute paths (container refresh, compose regen) handle natively.
- Header RMB and empty-area RMB both fall back to a disabled "No valid actions" entry when the state machine contributes no gestures (Phase 2 silent-no-op fix extended to scope side).
- **L4 auth stencil nodes (Task 4.9)** are read-only in the GUI — `_show_context_menu` short-circuits when `node.is_stencil_node and node.stencil_tier == "auth"`, leaving the menu empty so the silent-no-op fallback is the only entry. Container_lifecycle owns the lifecycle of named isolation volumes; the GUI only renders their container-side mount points.

### Preflight Checks

| Check | Returns | Op |
|-------|---------|-----|
| Host file missing | `OpError.HOST_FILE_NOT_FOUND` | push |
| Path not under host_container_root | `OpError.INVALID_LOCATION` | push/pull |
| Container not running | `OpError.CONTAINER_NOT_RUNNING` | push/pull/rm |
| Parent not mounted (TTFF risk) | `OpError.PARENT_NOT_MOUNTED` | push |
| File already tracked | `OpWarning.FILE_ALREADY_TRACKED` | push |
| Container has file (untracked) | `OpWarning.FILE_IN_CONTAINER_UNTRACKED` | push |
| Not in masked area | `OpWarning.NOT_IN_MASKED_AREA` | push |
| Local file exists (non-dev pull) | `OpWarning.LOCAL_FILE_EXISTS` | pull |
| Remove cannot be undone | `OpWarning.DESTRUCTIVE_REMOVE` | rm |

### File Filter Hook (Placeholder)

Between host read and container write, an optional `file_filter` hook transforms content:
```
Host file → file_filter(path) → filtered temp file → docker cp → container
```
Default: `passthrough` (returns input path unchanged). See `docker/file_filter_ops.py`.

### Pull / Remove follow same pattern

Same preflight/execute structure with operation-specific checks.
Pull additionally uses `resolve_pull_output()` for dev_mode destination.
Remove calls `docker exec rm` instead of `docker cp`.

---

## Phases 7-8: User Action & Refresh

For the canonical CORE-side Phase 7-8 flow (action filtering, CORE state changes, cascade rules, file operations), see: `COREFLOWCHART.md` Phase 7 and Phase 8.

GUI-specific Phase 7-8 behavior is documented above in:
- **State Change Flow** — signal routing through `setData → stateChanged → views refresh`
- **File Operations Flow** — CORE preflight/execute with GUI dialog layer via `file_ops_ui.py`

### Phase 8: Refresh (GUI-specific)

```
After Phase 7 completes, event triggers return to
the appropriate phase for status update:

State toggle (mount/mask/reveal checkbox):
    → Return to PHASE 4 (re-apply node state + visibility)
    → GUI refreshes from updated NodeState (Phase 5 cosmetic re-render)

File operation (push/pull/remove):
    → Update pushed/orphaned flags in NodeState
    → GUI refreshes affected nodes

Config reload (switch container, reopen project):
    → Return to PHASE 1 (full re-read from scope_docker.json)
```

---

## Config Persistence Flow

```
SAVE (GUI → JSON)
─────────────────
MountDataTree.get_config_data()       ← project paths only (filters out siblings)
MountDataTree.get_sibling_configs()   ← extracts sibling state from shared _states
    │
    ▼
ScopeDockerConfig.to_dict()           ← converts absolute → relative paths
    │
    ▼
scope_docker.json                     ← written to .{project}_igsc/.{container}/

Fields in JSON:
    local_host_root: ".."             ← relative to host_project_root (no absolute paths)
    container_root: "/Projects"       ← container-side path (default: /{host_container_root.name})
    siblings[].host_path: absolute    ← EXCEPTION: siblings keep absolute paths
                                        (they can be anywhere on the OS)


LOAD (JSON → GUI)
─────────────────
scope_docker.json
    │
    ▼
load_config(host_project_root, scope_name)
    │
    ▼
ScopeDockerConfig.from_dict()         ← converts relative → absolute paths
    │                                    local_host_root resolved: host_project_root / ".."
    ▼
MountDataTree.load_config(config)
    ├── Clear all state
    ├── Apply project states (mount_specs → mounts/masked/revealed via @property)
    ├── Set file tracking (pushed_files, container_files)
    ├── Add siblings (scan filesystem + apply sibling states)
    └── _rebuild_extension_stencil_nodes()  ← L4 auth stencils from extensions
          One synthetic MountDataNode per spec returned by
            ExtensionConfig.synthesize_mount_specs() (container-only
            delivery="volume" + content_seed="folder" + host_path=None):
            is_stencil_node=True, stencil_tier="auth",
            source=NodeSource.STENCIL, container_path=str
          Appended to root_node.children; never lazy-loads
          (children_loaded=True on construction)

          Unify L4 Task 1.11: container_ops_ui._track_extension routes
          post-install refresh through this same generic intake path —
          tree.load_config(config) then _local_host.refresh() +
          _scope_view.refresh(). The dedicated set_extensions shortcut
          was retired; there is now one tree-rebuild call path.

          Unify L4 Task 1.9: NodeState for each stencil path is produced by
            CORE's apply_node_states_from_scope — GUI merges synthesized
            specs into a temporary LocalMountConfig before the CORE call.
            compute_node_state derives container_only=True from
            spec.host_path is None; compute_visibility emits "virtual"
            without any GUI-side direct-write to _states.

          CORE-side consumer (cross-ref → COREFLOWCHART.md Phase 6a,
            ARCHITECTUREGLOSSARY.md → "volume layering order"): the same
            ExtensionConfig.synthesize_mount_specs() helper is also
            consumed by compute_container_hierarchy(extensions=...) at
            compose-generation time. Extension specs merge into
            mount_specs and emit through the L_volume tier under
            vol_{owner_segment}_{path}. There is no separate Layer 4
            emission tier post Unify L4 Phase 1 Task 1.3. GUI calls
            synthesize at load time (above); CORE calls it at compute
            time — both paths route through the same MountSpecPath shape.
```

---

## Key Invariants (Data Flow Rules)

### Rule 1: Single Source of Truth
`MountDataTree` is the ONLY place state lives at runtime. Views read from it. Config serializes from it.

### Rule 2: Scan Targets (Default)
Only TWO things are scanned by default:
1. `host_project_root` — always scanned on open
2. Each declared `sibling.host_path` — scanned after config load

`local_host_root` is NOT scanned unless explicitly configured. It is a stored reference for future "scan all children" feature.

### Rule 3: Scan Order
Filesystem scanning happens in strict order:
1. Project root scanned first (always)
2. Config loaded second (provides sibling paths + virtual definitions)
3. Siblings scanned third (one per sibling, appended to tree)
4. Virtual nodes added last (no filesystem scan)

### Rule 4: One Tree, Two Views
Both panels share the SAME `MountDataTree` instance. `DisplayConfig` controls what each panel shows. Never duplicate state across views.

### Rule 5: State Scoping
State queries (`is_effectively_mounted`, etc.) must walk ancestors to the correct root:
- Project nodes → walk to `host_project_root`
- Sibling nodes → walk to `sibling.host_path`
- Virtual nodes → no state inheritance

### Rule 6: Display Filtering
`LocalHostDisplayConfig`: folders only, all nodes visible, no virtuals, HOST perspective.
`ScopeDisplayConfig`: files + folders, hidden nodes removed, virtuals shown, CONTAINER perspective.

### Rule 7: Hybrid Context in ScopeView
ScopeView uses TWO rendering styles on the same tree:
- Folders → scope-style rendering (green/yellow/muted based on mount/mask/reveal state)
- Files → exception-style rendering (bright/dim based on push state)

### Rule 8: Cascade Direction
Checkbox cascades flow DOWN the hierarchy:
- Mount unchecked → clears Mask, Reveal
- Mask unchecked → clears Reveal
- Reveal unchecked → no cascade

### Rule 9: Config Round-Trip
`save_config(build_config())` then `load_config()` must produce identical tree state. Paths convert: absolute ↔ relative at the JSON boundary only.

### Rule 10: No Absolute Host Paths in Config
All host paths in `scope_docker.json` are relative to `host_project_root`, EXCEPT `sibling.host_path` which must be absolute (siblings can be anywhere on the OS, including different drives).

### Rule 11: Auto-Mask Config Directory
`.{project}_igsc/` is automatically masked. It must never appear as visible content inside the container.

---

## Module Responsibility Map

```
mount_data_tree.py    → Runtime State Host (hosts NodeState instances from core/node_state.py)
                         CORE defines NodeState dataclass and computation rules.
                         GUI hosts runtime instances and Stage 2 (mirrored) descendant walk.
                         See: COREFLOWCHART.md Phase 3 for computation rules.
mount_data_model.py   → Qt Adapter  (MountDataTreeModel wraps tree + DisplayConfig)
display_config.py     → View Rules  (columns, filtering, checkbox behavior)
local_host_view.py    → Left Panel  (widget + RMB menu + undo)
scope_view.py         → Right Panel (widget + RMB menu + file ops signals)
file_ops_ui.py        → File Op UI  (thin layer: preflight dialog → CORE execute → tree refresh)
                         Calls docker/file_ops.py orchestrators, shows dialogs, updates tree
container_ops_ui.py   → Container UI (thin layer: CORE execute_create/remove → progress → refresh)
                         Calls docker/container_lifecycle.py, no CLI imports
config_manager.py     → Orchestrator (open/switch/save project+scope)
app.py                → Wiring      (creates shared tree, connects signals)
style_engine.py       → Rendering   (StyleGui: gradients, colors, consolidated *_theme.json)
container_root_panel.py → Config UI (header + pattern list + JSON viewer, themed via config_panel section)
delegates.py          → Paint       (GradientDelegate base, TreeStyleDelegate, HistoryDelegate)
```
