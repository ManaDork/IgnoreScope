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
SINGLE FILE FLOW (Push — the marked-push inversion):

User RMB clicks file in ScopeView
    │
    ▼
Context menu: Push / Update / Pull / Remove
    │
    ▼
ScopeView emits pushToggleRequested → app._on_push_toggle
    │
    ▼
FileOperationsHandler.on_push(path)
    │
    ├── CORE: add_marked_push(host_project_root, scope, [path])   ← config-first: enqueue NOW, any container state
    │
    ├── GUI: get_container_info(docker_name)
    │     ├── missing / stopped? → statusBar "Marked {name} for push — will be pushed on next
    │     │                          Create/Update Container (or run push-marked)" — STOP (no docker cp)
    │     └── running? → drain now ↓
    │
    ├── GUI: drain_marked_push_now()
    │     ├── QProgressDialog (progress wired to the drain's progress(i, total) callback)
    │     ├── CORE: drain_marked_push(host_project_root, scope, on_stale=_confirm_stale, progress=…)
    │     │         (config=None here → the drain loads + saves scope_docker_desktop.json itself)
    │     │     ├── per queued file: mkdir -p parent + docker cp → add to pushed_files, dequeue (on success)
    │     │     │                     cp failure → noted, left queued
    │     │     └── host file ≥ container copy (stale)? → _confirm_stale dialog:
    │     │           [Replace] cp anyway · [Skip] leave queued · [Skip and Unmark] drop from queue AND pushed_files
    │     └── GUI: ConfigManager.reload_current_scope()   ← resync the tree (drain saved config out-of-band)
    │
    └── GUI: statusBar "Pushed {name}" | "Unmarked {name} — host older" | QMessageBox.warning("Push Not Completed", …)

(on_update / on_pull / on_remove unchanged — direct execute_push / execute_pull / execute_remove on a tracked file.)


BATCH FILE FLOW (multi-select or folder) — unchanged wiring:

scope_view._batch_toggle ─(begin_batch)→ pushToggleRequested (one per path)
                          → app._on_push_toggle → FileOperationsHandler.on_push(path)  ─(end_batch)→

    Each path runs the single-file flow above — N enqueue+drain cycles; the running-case drain
    processes whatever is queued, so the net result equals one big batch. begin_batch/end_batch
    still wraps the toggles (matters only once a pending visual state lands).


SCOPE-LOAD PROMPT (non-empty queue on project open / scope switch):

ConfigManager.switch_scope / open_project   (after refresh; busy dialog closed)
    │
    ▼
ConfigManager._post_scope_load()
    ├── load_marked_push(host_project_root, scope) empty? → STOP
    └── QMessageBox "N file(s) marked for push — push now?"   [Now] / [Delay]
          ├── [Now]   → file_ops_handler.drain_marked_push_now()
          └── [Delay] → statusBar "N file(s) still queued — reload to be re-prompted, or use Push / push-marked"


CLI EQUIVALENT:

cmd_push(host_project_root, scope_name, files, force=False)
    │
    ├── with files: validate each (exists + under host_container_root) → add_marked_push(...)
    │               (any invalid path → print errors + exit, nothing enqueued)
    ├── CORE: drain_marked_push(host_project_root, scope, on_stale=("replace" if force else "skip"))
    └── Print the drain summary + per-file notes

cmd_push_marked(host_project_root, scope_name, force=False)   ← cmd_push with no files: drain the queue only
```

### Marked-push dialogs (push / dump / drain phases)

Canonical catalog of every prompt/notification the marked-push feature surfaces, by phase.
"—" = no dialog (status-bar message only). CLI has **no** dialogs — `push` / `push-marked` print
the drain summary + per-file notes to stdout; `cmd_create` prints `OpResult.details` only on failure.

| Phase / trigger | Dialog (code site) | Buttons → action |
|---|---|---|
| **Scope opened / switched** — marked-push or marked-staged queue non-empty | `QMessageBox` (Question), title "Files Marked for Push", text "{N} file(s) marked for push — push now?" (N = host + staged) — `ConfigManager._post_scope_load` | **[Now]** → `drain_marked_push_now()` (progress dialog + per-file stale prompts; drains both queues) · **[Delay]** → leave queued; status "{N} still queued — reload the project to be re-prompted, or use Push / push-marked" |
| **Create Container** | — (no pre-confirm; a fresh create risks nothing) — `ContainerOperations.create_container` | n/a |
| **Recreate Container** | `QMessageBox.question`, title "Recreate Container": "…All data in the container will be lost. Files marked as pushed will be re-pushed from the host after recreate (a snapshot of the list is saved to `.ignore_scope/<scope>/pushed_files_<timestamp>.txt`); in-container edits to those files will be lost. Continue?" — `ContainerOperations.recreate_container` | **[Yes]** → auto-dumps `pushed_files` to `.ignore_scope/<scope>/pushed_files_<ts>.txt`, `add_marked_push(config.pushed_files)`, then `execute_remove_container -v` + `execute_create` (clears `pushed_files`; drains the re-queued host entries so successes re-promote) · **[No]** → cancel |
| **Update Container** | — (no pre-confirm; `execute_update` keeps named volumes and re-pushes the still-on-disk `pushed_files`; a tracked file whose host source is gone is dropped and listed in the success box) — `ContainerOperations.update_container` | n/a |
| **During a drain** — host file mtime ≥ container copy (host stale); fires per file on the manual-Push / scope-load `[Now]` drains only (`drain_marked_push(on_stale=…)`; lifecycle uses `on_stale="replace"` and a fresh container never trips it) | `QMessageBox` (Question), title "Stale Host File", text "{name} is older than the container's copy.", informative "Replace it, skip this push, or skip and unmark the file?" — `FileOperationsHandler._confirm_stale` | **[Replace]** → `docker cp` anyway → drained, tracked · **[Skip]** (default) → leave queued (re-prompts next drain) · **[Skip and Unmark]** → remove from queue AND from `pushed_files` (stops being asked) |
| **During a drain** — progress | `QProgressDialog` "Pushing marked files…", application-modal, no Cancel, 400 ms before it shows — `FileOperationsHandler.drain_marked_push_now` | n/a (auto-closes; quick pushes never flash) |
| **After a manual GUI Push** — file still queued (cp failed, or `[Skip]` on a stale file) | `QMessageBox.warning`, title "Push Not Completed": "{name} is still queued for push.\n\n{drain details/message}" — `FileOperationsHandler.on_push` | **[OK]** |
| **After a manual GUI Push** — drained OK / unmarked / no container | — status bar: "Pushed {name}" · "Unmarked {name} — host file is older than the container's copy" · "Marked {name} for push — will be pushed on next Create/Update Container (or run push-marked)" | n/a |
| **After Create / Update / Recreate** | success: `QMessageBox.information`, title "Container Created/Updated/Recreated", body = orchestrator message (incl. "{N} marked-push drain note(s)" / "{N} tracked file(s) dropped (host source gone)"). failure: `QMessageBox` (Critical) "Operation Failed" — first line as text, rest as `setDetailedText`. — `ContainerOperations._on_operation_finished` | **[OK]** — `ContainerWorker` forwards only `(success, message)`, so the per-file drain `details` list is summarized as a count, not shown line-by-line |
| **Container → Save Pushed-Files List** | `QFileDialog.getSaveFileName` "Save Pushed-Files List" (default `{scope}_pushed_files.txt`); `QMessageBox.information` "No Pushed Files" if the scope has none; `QMessageBox.critical` "Config Error" / "Save Failed" on errors; status bar on success — `ContainerOperations.save_pushed_files_list(auto=False)`. Recreate uses `save_pushed_files_list(auto=True)` (no dialog) and writes a timestamped snapshot under `.ignore_scope/<scope>/`. | save-dialog OK/Cancel; info/error boxes [OK] |

**Open / proposed enhancements** (not yet implemented):
- Recreate dialog: now auto-dumps + re-queues automatically (Phase 3 of the marked-push consolidation). The historic **[Export & Continue]** proposal is obsolete.
- Stale-host prompt: add **[Replace All]** / **[Skip All]** so a batch of stale files isn't prompted N times (drain caches the answer).
- "Push Not Completed" warning: add **[Retry]** → re-run `drain_marked_push_now()`.
- Lifecycle success box: surface the drain `details` list (have `ContainerWorker` forward it; show via `setDetailedText`) instead of only the count.
- Scope-open prompt: optional **"Don't ask again this session"** checkbox.

### Scope Config Tree RMB — Stencil Gesture Flow

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
- **Extension auth stencil nodes** are read-only in the GUI — `_show_context_menu` short-circuits when `node.is_stencil_node and node.stencil_tier == "auth"`, leaving the menu empty so the silent-no-op fallback is the only entry. Container_lifecycle owns the lifecycle of named extension-owned volumes; the GUI only renders their container-side mount points.

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
    └── _rebuild_extension_stencil_nodes()  ← Extension auth stencils from extensions
          One synthetic MountDataNode per spec returned by
            ExtensionConfig.synthesize_mount_specs() (container-only
            delivery="volume" + content_seed="folder" + host_path=None):
            is_stencil_node=True, stencil_tier="auth",
            source=NodeSource.STENCIL, container_path=str
          Appended to root_node.children; never lazy-loads
          (children_loaded=True on construction)

          Post-install extension refresh routes through this same generic
          intake path — container_ops_ui._track_extension calls
          tree.load_config(config), then _local_host.refresh() +
          _scope_view.refresh(). There is one tree-rebuild call path for
          both scope loads and post-install refreshes.

          NodeState for each stencil path is produced by CORE's
            apply_node_states_from_scope — GUI merges synthesized
            specs into a temporary LocalMountConfig before the CORE call.
            compute_node_state derives container_only=True from
            spec.host_path is None; compute_visibility emits "virtual"
            without any GUI-side direct-write to _states.

          CORE-side consumer (cross-ref → COREFLOWCHART.md Phase 6a,
            ARCHITECTUREGLOSSARY.md → "volume layering order"): the same
            ExtensionConfig.synthesize_mount_specs() helper is also
            consumed by compute_container_hierarchy(extensions=...) at
            compose-generation time. Extension specs merge into
            mount_specs and emit through the unified L_volume tier under
            vol_{owner_segment}_{path} — a single compose-emission path
            for user-authored and extension-owned isolation volumes alike.
            GUI calls synthesize at load time (above); CORE calls it at
            compute time — both paths route through the same MountSpecPath
            shape.
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
                         Roles: NodeStateRole, NodeIsFileRole, NodeStencilTierRole, NodePathRole
display_config.py     → View Rules  (columns, filtering, checkbox behavior)
local_host_view.py    → Left Panel  (widget + RMB menu + undo)
                         Signals: nodeSelected, selectionCleared, selectionChangedPaths,
                                  folderExpanded, folderCollapsed
scope_view.py         → Right Panel (widget + RMB menu + file ops signals)
                         Methods: set_tracked_paths, expand_path, collapse_path
file_ops_ui.py        → File Op UI  (thin layer: preflight dialog → CORE execute → tree refresh)
                         Calls docker/file_ops.py orchestrators, shows dialogs, updates tree
container_ops_ui.py   → Container UI (thin layer: CORE execute_create/remove → progress → refresh)
                         Calls docker/container_lifecycle.py, no CLI imports
config_manager.py     → Orchestrator (open/switch/save project+scope)
app.py                → Wiring      (creates shared tree, connects signals)
selection_coordinator.py → Cross-Tree (TreeSelectionCoordinator + _ClickAwareTreeView)
                         Symmetric single-context selection: clicking either tree
                         clears the sibling. Empty-space click clears both.
style_engine.py       → Rendering   (StyleGui: gradients, colors, consolidated *_theme.json)
container_root_panel.py → Config UI (header + pattern list + JSON viewer, themed via config_panel section)
delegates.py          → Paint       (GradientDelegate base, TreeStyleDelegate with
                                     Layer-4 tracked-path outline, HistoryDelegate)
view_helpers.py       → Shared Helpers (configure_tree_view, apply_header_config,
                                        resolve_action_target — cursor-primary RMB)
```

---

## Cross-Tree Coordination

LocalHostView and ScopeView each own a `_ClickAwareTreeView` (subclass of
`QTreeView` that emits `userRowClicked` and `emptySpaceClicked` from
`mousePressEvent`, distinguishing user gestures from programmatic
selection changes). Two layers compose orthogonally:

1. **Selection layer (single-context):** `TreeSelectionCoordinator`
   wires `userRowClicked` so that clicking either tree clears the
   sibling's `selectionModel`. Empty-space click clears both. Driven
   by user gestures only — programmatic `clearSelection()` does not
   re-trigger the coordinator. RMB context menus read
   `selectionModel.selectedRows(0)` for multi-select extension via
   `view_helpers.resolve_action_target` (cursor-primary).

2. **Tracked-paths overlay (cross-view visual cue):** when LocalHost's
   selection set changes (`selectionChangedPaths(list[Path])` signal,
   driven by `selectionModel.selectionChanged` so it fires on every
   set change including programmatic clears), `ScopeView.set_tracked_paths`
   stores the set in `TreeStyleDelegate._tracked_paths` and walks the
   tree expanding ANCESTORS only — never the matched folder itself.
   The delegate paints a teal outline (Layer 4, on top of selection)
   for every row whose path is in the set. Independent of `selectionModel`,
   so Scope's user multi-select and RMB context survive every LocalHost
   click. `_validate_tracked_path` wired to `tree.structureChanged`
   drops stale paths on project / scope switch.

3. **Branch-indicator mirror chain (one-way LocalHost → Scope):**
   `LocalHostView` emits `folderExpanded(path)` / `folderCollapsed(path)`
   when the user toggles a folder's branch indicator (driven by
   `QTreeView.expanded` / `.collapsed`). `app.py` wires these to
   `ScopeView.expand_path` / `collapse_path` so Scope mirrors the
   toggle. Files and stencil nodes do not emit. Loop-prevention is
   trivial because Scope's `expanded`/`collapsed` signals are not
   wired anywhere.

## Provenance

Domain prose above is timeless. Feature-rollout history (Task X.Y, PR #N, commit hashes, branch names) lives here so the body stays canonical. Full project chronology: `docs/architecture/EVOLUTION.md`.

- **Virtual Mount Phase 3 GUI gesture flow (Scope Config Tree RMB stencil gestures, recreateRequested signal):** shipped via PRs #21–#29 and #51–#54 (2026-04-21 – 2026-05-01). Established the Scope Config Tree RMB → `_add_scope_config_gestures` → `MountDataTree._mount_specs` mutation flow documented above.
- **Unify L4 / reclaim-isolation-term (CORE-driven synthetic states + post-install extension refresh through generic intake):** shipped via PRs #30–#56 (2026-04-22 – 2026-05-02). The `apply_node_states_from_scope` synthetic-state path and the unified `tree.load_config(config)` post-install refresh route described in this document come from this phase chain.
- **Architecture Blueprint timeless-prose policy:** Phase/Task/PR identifiers are removed from domain prose and parked in this footer. Reference: CLAUDE.md `Feature-Emergence Posture` and `_workbench/_evaluations/project-cleanup-2026-05-02.md` Wave 2-2.

