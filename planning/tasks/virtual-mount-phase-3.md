# Phase 3: Virtual Mount — Container-only folders + permanent-volume tier + STENCIL rename

**Feature:** Virtual Mount (continuation from Phase 2)
**Branch:** `feature/virtual-mount-phase-3` (off current `main` at `9e39496`)
**Duration Estimate:** 5-8 days

---

## Context

Phase 1 (PR #17, commit `8b34e0d`) shipped per-spec `delivery: "bind" | "detached"` on `MountSpecPath`, the `_detached_init` cp-walk lifecycle, and the LocalHost 5-gesture RMB state machine. Phase 2 (PR #18, commit `9e39496`) shipped the CLI surface + LocalHost header RMB silent-no-op fix.

Phase 3 extends the model two ways — a new delivery tier for named-volume backing, and **container-only** mount specs (no host path) — while introducing a dedicated **Scope Config Tree** RMB surface for folder-creation gestures that have no LocalHost analogue. It also resolves the long-standing "virtual" naming overload flagged in `CLAUDE.md` by renaming synthetic tree-node identifiers to **STENCIL** (UX labels "Virtual Mount" / "Virtual Folder" unchanged — user vocabulary is preserved).

**What Phase 2 explicitly deferred to Phase 3:**
- Per-spec `delivery="volume"` named-volume tier (persists across ordinary container update)
- Container-only folder creation ("Make Folder" family)
- Permanent-folder gestures in the Scope Config Tree RMB
- L4 auth volume rendering in the Scope Config Tree

**What Phase 3 does NOT include (scoped separately):**
- **Container-Diff tool** (menubar `Edit | Select Diff` / `Show Diff`, three-state scan, CLI surface). Logically adjacent — powers the recreate-warning UX — but is its own feature spec.
- Child-aware header RMB expansion (separate from Phase 2's silent-no-op fix).
- Push/pull UX rework for `pushed_files` (stays as-is).

---

## Decisions locked (2026-04-21)

- **Synthetic-node vocabulary → STENCIL.** Internal identifiers renamed from `virtual` root to `stencil` root. UX labels ("Virtual Mount", "Virtual Folder") unchanged — they are the correct user vocabulary.
  - Rationale: `virtual` overloaded four concepts (`visibility.virtual` MatrixState value, `NodeSource.VIRTUAL` origin enum, `get_virtual_paths()` Stage 2 derivation, UX "Virtual Mount" label). `stencil` has zero collision in this codebase and semantically matches all five synthetic-node kinds (mirrored intermediates, detached roots, L4 auth, container-only folders, permanent volumes): "defines structure, not content."
- **Permanent volume schema value = `delivery="volume"`.** Names the Docker mechanism. Reserves "Permanent" for the UX label on `Make Permanent Folder → Volume Mount`.
- **Keep `visibility="virtual"` axis value.** Semi-user-facing (drives tree coloring/glyphs). Renaming it ripples through the Core truth table + every test. Rename *surrounding* code instead.
- **Container-only specs = `host_path: Optional[Path]`.** `None` → container-only. Same `MountSpecPath` schema (no new config entry type). `_detached_init` skips host-read side when `host_path is None` — just emits `docker exec mkdir -p`.
- **Content delivery control = `content_seed: Literal["tree", "folder"]`.**
  - `"tree"` (default for existing detached specs) → existing cp-walk behavior (whole subtree).
  - `"folder"` → mkdir only at the mount root; user fills content via `pushed_files` or manually.
- **Soft permanence = `preserve_on_update: bool = False`.** When `True` on a `delivery="detached"` spec, the update lifecycle cp's contents to a host tmp staging area, recreates the container, and cp's them back. Only applicable when `content_seed="folder"` (tree-seeded specs re-read from host on update anyway).
- **Hard permanence = `delivery="volume"`.** Named volume emitted in compose; survives ordinary update natively. Destroyed only on explicit `docker compose down -v` (recreate path — warn + redirect user to Diff view when available).
- **Gesture surfaces are split by RMB location.**
  - LocalHost tree RMB: host-backed gestures only (Mount, Virtual Mount, Virtual Folder, plus Phase 1 convert/unmount).
  - Scope Config Tree RMB: container-only gestures only (Make Folder, Make Permanent Folder → No Recreate / Volume Mount, Mark Permanent, Unmark Permanent).
- **L4 auth volumes rendered read-only** in Scope Config Tree with a distinct stencil tier glyph. No RMB gestures (extension-owned).

---

## Gesture → schema matrix

| RMB location | Gesture | `delivery` | `content_seed` | `host_path` | `preserve_on_update` |
|---|---|---|---|---|---|
| LocalHost | Mount | `bind` | `tree` | set | n/a |
| LocalHost | Virtual Mount | `detached` | `tree` | set | `False` |
| LocalHost | Virtual Folder *(NEW)* | `detached` | `folder` | set | `False` |
| Scope Config | Make Folder *(NEW)* | `detached` | `folder` | `None` | `False` |
| Scope Config | Make Permanent Folder → No Recreate *(NEW)* | `detached` | `folder` | `None` | `True` |
| Scope Config | Make Permanent Folder → Volume Mount *(NEW)* | `volume` | `folder` | `None` | n/a |
| Scope Config | Mark Permanent *(NEW — on existing detached)* | `detached` | (unchanged) | (unchanged) | flip `False` → `True` |
| Scope Config | Unmark Permanent *(NEW)* | `detached` | (unchanged) | (unchanged) | flip `True` → `False` |

---

## Tasks (ordered by dependency)

### 4.1: STENCIL rename — synthetic-node vocabulary cleanup

**What:** Rename internal identifiers from `virtual` root to `stencil` root where the meaning is "synthetic tree node not on disk." Keep UX-facing strings and the `visibility="virtual"` axis value unchanged. Also align delivery-mode API method names to the `detached` schema value (separate cleanup, same task for batch efficiency).

**Files (non-exhaustive — run global rename):**
- `IgnoreScope/gui/mount_data_tree.py` — `NodeSource.VIRTUAL` → `NodeSource.STENCIL`; `is_virtual` → `is_stencil_node`; `virtual_type` → `stencil_tier`; `toggle_virtual_mounted()` → `toggle_detached_mount()`
- `IgnoreScope/core/node_state.py` — `_compute_virtual_paths_from_config()` → `_compute_stencil_paths_from_config()`; `_cross_reference_virtual()` → `_cross_reference_stencil_paths()`
- `IgnoreScope/core/mount_spec_path.py` — `get_virtual_paths()` → `get_stencil_paths()`
- `IgnoreScope/core/local_mount_config.py` — `add_virtual_mount()` → `add_detached_mount()`; `is_virtual_mounted()` → `is_detached_mounted()`
- `IgnoreScope/gui/mount_data_model.py` — `is_virtual` param/field references
- `IgnoreScope/gui/display_config.py` — `display_virtual_nodes` → `display_stencil_nodes`; `"virtual.{type}"` color key → `"stencil.{tier}"`; `virtual_type="mirrored"` enum usage → `stencil_tier="mirrored"`
- Tests: update all references
- Theme JSON / style files: rename `virtual.*` color keys to `stencil.*` where they refer to stencil tiers (NOT the `visibility.virtual` glyph color)

**Acceptance Criteria:**
- [x] No remaining internal identifiers use `virtual` root for synthetic-node origin/tier concepts.
- [x] UX strings ("Virtual Mount", "Virtual Folder", "Convert to Virtual Mount", "Remove Virtual Mount") unchanged.
- [x] `visibility="virtual"` axis value unchanged in `compute_visibility()` truth table.
- [x] `add_virtual_mount`/`is_virtual_mounted`/`toggle_virtual_mounted` renamed to `detached` forms at all call sites (CLI, GUI, tests).
- [x] All existing tests pass unchanged (rename-only, no behavior change).
- [x] Updated `ARCHITECTUREGLOSSARY.md` — new **STENCIL** entry (origin concept, five-kind taxonomy, relation to `visibility="virtual"`), updated Virtual Mount entry and MountDataNode field table to reference `NodeSource.STENCIL` / `is_stencil_node`.
- [x] Updated `CLAUDE.md` Key Concepts — Mount Delivery Terms block references STENCIL, clarifies UX vs. internal vocabulary split.
- [x] Updated `COREFLOWCHART.md` — Phase 2 stencil-node narrative; MIRRORED_ALGORITHM.md, GUI_STATE_STYLES.md, GUI_LAYOUT_SPECS.md, THEME_WORKFLOW.md function/variable refs renamed to stencil forms.

**Complexity:** MEDIUM (global, but mechanical)

**Dependencies:** None — must land first to unblock schema work.

---

### 4.2: Schema — `host_path: Optional[Path]` + `content_seed` + `preserve_on_update` + `delivery="volume"`

**What:** Extend `MountSpecPath` with three new fields and extend the `delivery` Literal with `"volume"`. Update serialization, validators, and `LocalMountConfig` constructors.

**Files:**
- `IgnoreScope/core/mount_spec_path.py` — field additions, to_dict/from_dict
- `IgnoreScope/core/config.py` — validator updates (check container-only constraints)
- `IgnoreScope/core/local_mount_config.py` — new constructors: `add_stencil_folder(...)` (Make Folder), `add_stencil_volume(...)` (Make Permanent → Volume), helpers for mark/unmark permanent
- Tests: `IgnoreScope/tests/test_core/test_mount_spec_path.py`, `test_local_mount_config.py`

**Acceptance Criteria:**
- [x] `MountSpecPath.host_path` accepts `Optional[Path]`; `None` validates only when `delivery != "bind"`. (Bind specs auto-fill `host_path=mount_root` via `__post_init__` for backward compat with Phase 1/2 construction.)
- [x] `content_seed` defaults to `"tree"` (backward-compat for existing detached specs).
- [x] `preserve_on_update` defaults to `False`; validates only when `delivery="detached" and content_seed="folder"` (tree-seeded specs re-read from host, so flag is meaningless there — error on set).
- [x] `delivery="volume"` accepted; validator requires `content_seed="folder"` (no tree-seeding into a named volume at this phase).
- [x] Serialization round-trip covers all combinations.
- [x] Existing Phase 1/2 specs deserialize without modification (defaults fill the new fields; non-default fields omitted from JSON so legacy configs round-trip unchanged).
- [x] Updated `ARCHITECTUREGLOSSARY.md` Mount Delivery Terms — added `content_seed`, `preserve_on_update`, `delivery="volume"`, and container-only (`host_path: Optional[Path]`) semantics.
- [x] Updated `CLAUDE.md` Key Concepts Mount Delivery Terms — new fields summarized; gesture → schema matrix row count updated.

**Complexity:** MEDIUM

**Dependencies:** 4.1 (clean namespace).

---

### 4.3: Core — `_detached_init` branching on `content_seed` + `host_path is None`

**What:** Extend the detached init walk to branch on the new fields. Behavior:
- `content_seed="tree"` + `host_path` set → existing cp walk (unchanged).
- `content_seed="folder"` + `host_path` set → `docker exec mkdir -p <container_path>`, skip cp walk. `pushed_files` still applies.
- `content_seed="folder"` + `host_path is None` → `docker exec mkdir -p <container_path>`, no cp.

Masks/reveals continue to apply only for `content_seed="tree"` specs (folder-seed has no walk to mask/reveal over).

**Files:**
- `IgnoreScope/docker/container_lifecycle.py` — `_detached_init` branching
- Tests: `IgnoreScope/tests/test_docker/test_detached_init.py`

**Acceptance Criteria:**
- [x] Folder-seed detached specs produce a mkdir'd path in the container without host-read.
- [x] Tree-seed detached specs produce the Phase 1 cp-walked content (regression protection).
- [x] Container-only specs (`host_path is None`) work without host-filesystem access.
- [x] Masks/reveals on folder-seed specs are validator-rejected (or silently no-op'd with a warning — pick one; default: validator reject with clear error).
- [x] Updated `COREFLOWCHART.md` Phase 6a — `_detached_init` branching documented for the three cases (tree/folder × host-backed/container-only); flowchart reflects validator gate on masks/reveals for folder-seed.

**Complexity:** MEDIUM

**Dependencies:** 4.2.

---

### 4.4: Core — `delivery="volume"` compose emit

**What:** Extend the compose generator to emit named volumes for `delivery="volume"` specs. Volume name derivation: `{scope_docker_name}_{spec_index}_{sanitized_container_path}` (or user-provided — pick auto-derived for Phase 3 to keep schema flat).

**Files:**
- `IgnoreScope/core/hierarchy.py` — add `stencil_volume_entries` / `stencil_volume_names` to the hierarchy (parallel to existing `isolation_volume_*`)
- `IgnoreScope/docker/compose.py` — emit named volume mounts and top-level `volumes:` section entries
- Tests: `IgnoreScope/tests/test_docker/test_compose.py`

**Acceptance Criteria:**
- [x] `delivery="volume"` specs emit `<volume_name>:<container_path>` mount lines.
- [x] Top-level `volumes:` section lists all stencil volume names.
- [x] Volume names stable across config round-trip (same spec → same name).
- [x] Named volumes survive `docker compose up` with config changes (empty compose declaration → Docker retains volume across down/up; integration-level verification deferred — pure formatter contract asserted by unit tests).
- [x] Updated `COREFLOWCHART.md` — Phase 6a compose-emit step includes stencil-volume emit path for `delivery="volume"` specs.
- [x] Updated `ARCHITECTUREGLOSSARY.md` volume layering order — explicitly positions `delivery="volume"` stencil volumes relative to L1 bind / L2 mask / L3 reveal / L4 isolation.

**Complexity:** MEDIUM

**Dependencies:** 4.2.

**Implementation notes:**
- `hierarchy.py`: `_derive_stencil_volume_name(spec_index, container_path)` → `stencil_{spec_index}_{sanitized_container_path}`. Cross-scope uniqueness via docker compose project namespacing (no explicit `name:` on the declaration, paralleling mask volumes rather than the auth volume).
- `compose.py`: new `stencil_volume_entries` / `stencil_volume_names` parameters on `generate_compose_with_masks` (both optional); entries emit in services.volumes between L1-L3 and L4, names in top-level `volumes:`. Backward-compatible signature (no call-site changes required for bind-only scopes).
- Validator (Task 4.2) already gates `delivery="volume"` ⇒ `content_seed="folder"`.

---

### 4.5: Core — `preserve_on_update` lifecycle hook

**What:** When the update path runs and any spec has `preserve_on_update=True`, cp that spec's container contents to a host tmp staging area, run the recreate, then cp the contents back. On any cp failure, abort and leave the old container running (fail-safe — don't mid-state the user's container).

**Files:**
- `IgnoreScope/docker/container_lifecycle.py` — new `_preserve_and_recreate()` helper; integrated into `execute_update`
- Tests: `IgnoreScope/tests/test_docker/test_preserve_on_update.py`

**Acceptance Criteria:**
- [x] Specs with `preserve_on_update=True` retain contents across update.
- [x] cp-out failure aborts the update without destroying the old container.
- [x] cp-back failure after successful recreate is logged but non-fatal (contents will regenerate empty; warn user).
- [x] Specs with `preserve_on_update=False` or `delivery="volume"` unaffected (volume survives natively; no-preserve detached gets re-cp'd from host if tree-seeded, or stays empty if folder-seeded).
- [x] Updated `COREFLOWCHART.md` — update-path narrative describes `_preserve_and_recreate` hook, its invariants (abort if cp-out fails; warn if cp-back fails), and which spec combinations trigger it.

**Complexity:** MEDIUM-HIGH (lifecycle orchestration, failure modes)

**Dependencies:** 4.3.

---

### 4.6: GUI — Scope Config Tree RMB gestures

**What:** Build the Scope Config Tree RMB menu (net-new; currently there's no RMB on scope-side). Gestures: Make Folder, Make Permanent Folder (submenu → No Recreate / Volume Mount), Mark Permanent, Unmark Permanent, Remove. Wire through `ConfigManager` to the new `LocalMountConfig` constructors from 4.2.

**Files:**
- `IgnoreScope/gui/scope_view.py` — RMB state machine (ground-up; parallels LocalHost's in structure but simpler — no child-awareness yet)
- `IgnoreScope/gui/config_manager.py` — handler methods
- Tests: `IgnoreScope/tests/test_gui/test_scope_view_rmb.py`

**Acceptance Criteria:**
- [x] RMB on empty/container-only area → full gesture set visible.
- [x] RMB on existing detached-folder spec → Mark/Unmark Permanent visible and reflect current state.
- [x] RMB on existing volume spec → only Remove visible (no tier changes supported at this phase).
- [x] Make Folder prompts for container-side path (simple dialog).
- [x] Make Permanent Folder → Volume Mount triggers `execute_update` recreate confirmation when a container exists.
- [x] Header RMB follows the Phase 2 silent-no-op fix pattern (show disabled "No valid actions" when empty).
- [x] Updated `GUI_LAYOUT_SPECS.md` — new Scope Config Tree RMB section with gesture list, state transitions, and parity notes vs. LocalHost RMB.
- [x] Updated `DATAFLOWCHART.md` — RMB → ConfigManager → MountDataTree signal path documented for the new Scope-side gestures.

**Complexity:** MEDIUM-HIGH

**Dependencies:** 4.2.

---

### 4.7: GUI — LocalHost Virtual Folder gesture (6th gesture)

**What:** Extend the LocalHost 5-gesture RMB state machine to 6 with Virtual Folder. Sets `delivery="detached", content_seed="folder"` on the selected host node.

**Files:**
- `IgnoreScope/gui/local_host_view.py` — gesture addition in `_add_delivery_gestures`
- Tests: extend `IgnoreScope/tests/test_gui/test_delivery_tint.py` or sibling

**Acceptance Criteria:**
- [x] New RMB entry "Virtual Folder" visible when Virtual Mount would also be offered.
- [x] Produces a spec with `content_seed="folder"` (vs Virtual Mount's `"tree"`).
- [x] State-machine covers: no existing spec → both Mount + Virtual Mount + Virtual Folder offered; existing spec → only delivery-flip / unmount as appropriate.
- [x] Updated `GUI_LAYOUT_SPECS.md` — LocalHost RMB gesture bullets updated from 5-gesture to 6-gesture state machine, Virtual Folder entry conditions documented.

**Complexity:** LOW-MEDIUM

**Dependencies:** 4.2.

---

### 4.8: CLI surface for Phase 3 gestures

**What:** Mirror Scope Config gestures in CLI. Also add LocalHost Virtual Folder to existing `add-mount` via new `--seed` flag.

**Files:**
- `IgnoreScope/cli/commands.py`
- `IgnoreScope/cli/__main__.py`
- Tests: `IgnoreScope/tests/test_cli/`

**Commands:**
- `scope add-mount <path> --delivery detached --seed folder` (Virtual Folder)
- `scope add-folder <container_path>` (Make Folder)
- `scope add-folder <container_path> --permanent` (Make Permanent Folder → No Recreate)
- `scope add-folder <container_path> --volume` (Make Permanent Folder → Volume Mount)
- `scope mark-permanent <container_path>` (soft permanent flip)
- `scope unmark-permanent <container_path>`

**Acceptance Criteria:**
- [x] Each command maps to the equivalent GUI gesture's schema output.
- [x] `--permanent` and `--volume` are mutually exclusive.
- [x] Conflicts (e.g., mark-permanent on a `content_seed="tree"` spec) fail with clear message.
- [x] Updated `CLAUDE.md` Agent Zones CLI row — new commands listed, Phase 3 CLI surface no longer marked deferred.
- [x] Updated `ARCHITECTUREGLOSSARY.md` — CLI command names cross-referenced with their equivalent UX gestures in the Mount Delivery Terms block.

**Complexity:** MEDIUM

**Dependencies:** 4.2, 4.6.

**Side fix (Task 4.2 reconciliation):** `MountSpecPath.from_dict` was resolving container-only `mount_root` paths against `host_project_root`, prepending a Windows drive letter (`/api → C:/api`) and breaking exact-match lookup across reload. Container-only specs (no `host_path`, non-bind delivery) now keep `mount_root` as-written. Required for `mark-permanent` / `unmark-permanent` to find specs across `load_config` boundaries; also unblocks the GUI Scope Config gestures shipped in 4.6 across session reload.

---

### 4.9: L4 auth volume rendering in Scope Config Tree

**What:** Render `hierarchy.isolation_volume_entries` as read-only stencil-tier nodes under the Scope Config Tree. Distinct glyph; no RMB gestures. Informational only.

**Files:**
- `IgnoreScope/gui/mount_data_tree.py` — emit stencil nodes for L4 entries
- `IgnoreScope/gui/scope_view.py` — rendering (tier glyph)
- Theme: add `stencil.auth` color key

**Acceptance Criteria:**
- [ ] L4 volume mount points visible in Scope Config Tree.
- [ ] RMB on L4 node shows disabled "Extension-owned" entry (per Phase 2 silent-no-op pattern).
- [ ] Visual tier glyph distinguishes L4 from user-created stencil nodes.
- [ ] Updated `DATAFLOWCHART.md` — L4 isolation volumes rendered under Scope Config Tree (previously invisible in GUI); data flow shows hierarchy → MountDataTree → ScopeView.
- [ ] Updated `THEME_WORKFLOW.md` — new `stencil.auth` color key added to the Mount Delivery Color Mapping, plus any other stencil tier colors introduced (`stencil.folder`, `stencil.volume`, `stencil.mirrored`).
- [ ] Updated `GUI_STRUCTURE.md` — Scope Config Tree node-type hierarchy includes stencil tiers.

**Complexity:** LOW-MEDIUM

**Dependencies:** 4.1 (stencil vocabulary).

---

### 4.10: Emergent-vocabulary reconciliation

**What:** Per CLAUDE.md Feature-Emergence Posture, consume the **deferred-canonicalization list** at end of phase. This task is scoped narrowly — it only handles vocabulary or patterns that **emerged during implementation** and were deferred by earlier tasks. Routine doc updates (glossary terms, flowchart steps, layout specs, color keys) land **inline with the task that produced them** per tasks 4.1-4.9 AC boxes.

Maintain a running `planning/tasks/virtual-mount-phase-3-deferred.md` list during implementation. Each time a DRY audit or implementation pass turns up new vocabulary that doesn't fit an existing glossary term, append an entry. This task consumes that list.

**Files (only those holding emergent terms; typically a subset):**
- `docs/architecture/ARCHITECTUREGLOSSARY.md`
- `docs/architecture/COREFLOWCHART.md`
- `CLAUDE.md` Key Concepts / Agent Zones

**Acceptance Criteria:**
- [ ] Deferred-canonicalization list reviewed item-by-item; each either canonicalized into a blueprint or filed to backlog as a future concept.
- [ ] No conflicting or obsolete references to `virtual` (root form) where `stencil` or `detached` should be used — sweep pass across all blueprints.
- [ ] `planning/tasks/virtual-mount-phase-3-deferred.md` emptied (all items resolved) or archived with resolution notes.
- [ ] **No general doc catch-up occurs here** — if a doc update is missing that belongs to 4.1-4.9, return to that task and close it there.

**Complexity:** LOW-MEDIUM

**Dependencies:** 4.1-4.9 complete with their own doc ACs ticked.

---

### 4.11: Task doc reconciliation

**What:** Tick ACs, file bugs for anything uncovered, update backlog pointers.

**Acceptance Criteria:**
- [ ] All 4.1-4.10 AC boxes ticked.
- [ ] Container-Diff remains in backlog as a distinct feature spec (`planning/backlog/container-diff.md` to be created by this task).
- [ ] Any discovered UX friction filed via `/zev-bug` or `/zev-feedback`.

**Complexity:** LOW

**Dependencies:** 4.1-4.10.

---

## Out of scope (Phase 4 or separate features)

- **Container-Diff** — menubar `Edit | Select Diff` / `Show Diff`, three-state (`unknown/same/different`) scan, CLI, no long-term storage. Separate feature spec. Drives the recreate-warning UX when present.
- **Child-aware header RMB expansion** — Phase 2 fixed the silent-no-op; exposing child-gestures on header RMB is a separate behavior extension.
- **Selection → tree-highlight** (e.g., stencil node click expands the host-side analog) — UX polish, not functional.
- **Retained-volume content migration utilities** (e.g., `scope migrate-volume <path>`) — not needed until users hit the friction.

---

## Success criteria (Phase 3 complete)

- [ ] STENCIL rename lands cleanly; `virtual` only appears in UX strings and the `visibility="virtual"` axis value.
- [ ] Schema supports container-only specs, folder-seed delivery, soft permanence, and named-volume delivery.
- [ ] Scope Config Tree RMB gestures wire through to the new schema end-to-end.
- [ ] LocalHost gains Virtual Folder as 6th gesture.
- [ ] CLI surface mirrors every GUI gesture.
- [ ] L4 auth volumes render in Scope Config Tree.
- [ ] Blueprints reconciled.
- [ ] All tests passing; any pre-existing docker integration failures tracked separately.

---

## Kickoff

```
/zev-start do Phase 3 task 4.1
```

Start from `main` at `9e39496`. Land 4.1 (rename) on its own commit before 4.2 — the rename is mechanical and should NOT be mixed with schema work to keep diffs reviewable.
