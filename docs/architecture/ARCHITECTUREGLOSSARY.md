# Architecture Glossary

> Canonical term definitions for the IgnoreScope intended system.
> Based on COREFLOWCHART.md and DATAFLOWCHART.md — describes the target architecture.
>
> DOC-1 through DOC-4 corrections from `post_audit/08_architecture_directed_corrections.md` have been applied. Root GLOSSARY.md removed (moved to `old/`).

---

## State Terms

### mounted

User-configured flag marking a host directory as visible to the container. The directory is bind-mounted at the corresponding container path.

**JSON Field:** `local.mounts[]`
**NodeState Flag:** `mounted: bool`
**UI Column:** "Mount" — LocalHostDisplayConfig column (folders only, checkable)

**Cascade:** Unchecking mount clears masked and revealed for that path and descendants (Phase 7).
**Constraint:** None — any directory can be mounted.

**Domains:** Config, Computation (Layer 1 volumes), Generation (bind mount), Presentation (checkbox)

---

### masked

User-configured flag marking a host directory as hidden from the container. Implemented by a **named** Docker volume that overlays the bind mount. The volume **starts empty** (hiding original content) and **accumulates pushed exception files** written via `docker cp` at runtime.

**Config source:** Non-negated pattern in `mount_specs[].patterns` (e.g., `"vendor/"`)
**NodeState Flag:** `masked: bool` — derived via pathspec evaluation of owning MountSpecPath
**UI Column:** "Mask" — LocalHostDisplayConfig column (folders only, checkable)
**Volume naming:** `mask_{sanitized_rel_path}` (e.g., `mask_src_vendor`)

**Cascade:** Removing a mask pattern also removes descendant patterns (reveals, nested masks) from the owning MountSpecPath (Phase 7).
**Constraint:** Pattern must be within a MountSpecPath (implicit — patterns exist on mounts).
**Persistence:** Mask volumes survive container stop/start. Destroyed by `docker compose down -v`.
**Nesting:** A masked folder can contain revealed subfolders, which can contain re-masked subfolders, to arbitrary depth. Pathspec last-match-wins evaluation resolves nesting.

**Domains:** Config, Computation (interleaved volumes, revealed_parents), Generation (named volume entry), Container Ops (docker cp target, volume_exists check), Presentation (checkbox)

---

### revealed (unmasked)

User-configured flag creating a punch-through bind mount that re-exposes a specific **subdirectory** within a masked area. The revealed directory's host content becomes visible to the container again.

**Config source:** Negated pattern in `mount_specs[].patterns` (e.g., `"!vendor/public/"`)
**NodeState Flag:** `revealed: bool` — derived via pathspec evaluation (path matched by deny BUT overridden by exception)
**UI Column:** "Reveal" — LocalHostDisplayConfig column (folders only, checkable)

**Constraint:** Exception pattern must follow a deny pattern that covers it (validated by `MountSpecPath.validate()`).
**Docker mechanism:** Bind mount declared after the mask volume in pattern order. Docker's last-writer-wins stacking makes revealed content visible despite the mask.

Revealed is for **folders**. Pushed is for **files**. Both make content visible within masked areas — different mechanisms (bind mount vs docker cp).

**Domains:** Config, Computation (interleaved volumes, visibility), Generation (bind mount), Presentation (checkbox)

---

### pushed

A **workflow operation** where host files are temporarily made available inside the container via `docker cp`. Pushed files may target any path under `host_container_root`. Files within masked areas reside in the mask volume. Files outside masked areas receive `NOT_IN_MASKED_AREA` warning but are supported — the file-level counterpart to folder-level revealed.

Files may be **modified** during push via `FileFilter` (e.g., secret redaction, token substitution). Pushed files are explicitly tracked in `config.pushed_files` because the push operation is intentional and repeatable (push/pull/update cycle).

**JSON Field:** `pushed_files[]`
**NodeState Flag:** `pushed: bool`
**UI Column:** "Pushed" — defined by TreeDisplayConfig subclass
  - LocalHostDisplayConfig: files only, symbol_type="pushed_status"
  - ScopeDisplayConfig: files and folders, symbol_type="pushed_status"
**UI Actions:** Push toggle via pushToggleRequested signal (async docker cp). Actions defined by DisplayConfig `file_actions` sets, not view-hardcoded.
**Operations:** Push, Pull, Update (re-push), Remove

Parent directories inside mask volumes are created via `mkdir -p` before push (from revealed_parents). Parent directories outside masks appear in Container Scope via `has_pushed_descendant` ancestry — `_collect_all_paths()` walks ancestors up to `host_project_root`, Stage 3 sets `has_pushed_descendant=True`, and the display filter proxy passes hidden nodes with pushed descendants.

Pushed is for **files**. Revealed is for **folders**.

**Distinction from copied:** Pushed files are tracked, repeatable, and may be filtered. Copied files (see below) are ephemeral and untracked.

**Legacy name:** v1.x configs used `exception_files[]`. Migrated to `pushed_files` on load.

**Domains:** Config, Computation (revealed_parents), Container Ops (docker cp, mkdir -p, rm), Orchestration (push/pull commands), Presentation (ScopeView status)

---

### container_orphaned

Computed flag indicating a pushed file stranded inside a mask volume with no active parent mount. Detected during state application (Phase 3) via MatrixState check. File-only — folders cannot be pushed and therefore cannot be container-orphaned.

**NodeState Flag:** `container_orphaned: bool`
**MatrixState Rule:** `pushed=T, masked=T, mounted=F, revealed=F` → container_orphaned (TTFF)
**Not stored in JSON** — derived at runtime.
**Visibility:** vis=orphaned (container_orphaned is already encoded in the visibility value)

**Cause:** User removed a mount configuration after pushing files. The file physically exists inside the named Docker volume but has no bind mount making its container path accessible — it cannot be pulled back.

**Validation:** `detect_orphan_creating_removals()` in `core/node_state.py` detects config changes that would create container orphans BEFORE the cascade executes, enabling a confirmation dialogue.

**Domains:** Computation (Phase 3), Presentation (ScopeView stale file indicator)

---

### host_orphaned (DEFERRED)

Computed flag indicating a pushed file whose host source no longer exists on disk. The container copy is accessible (can be pulled) but cannot be re-pushed from host.

**NodeState Flag:** `host_orphaned: bool` (not yet implemented)
**Condition:** `pushed=T AND path NOT in scanned host paths`
**Not stored in JSON** — derived at runtime via set difference: `config.pushed_files - scanned_host_paths`.

**Cause:** User deleted or moved the host source file after pushing to the container.
**Impact:** File CAN be pulled (container copy exists) but CANNOT be re-pushed (source gone).

**Priority vs container_orphaned:** container_orphaned dominates (vis=orphaned, file unreachable). host_orphaned only applies when the file is otherwise accessible (vis=masked, pushed=T).

**Status:** Design complete, implementation deferred. Requires scoping decisions about scan coverage (`host_project_root` vs `host_container_root`) before implementation.

**Domains:** Computation (Phase 3, future), Presentation (ScopeView warning indicator, future)

---

### copied

An ephemeral support file transferred as-is into the container via clipboard paste or directory copy (`docker cp`). Copied files are **container-specific** and **not tracked** in `pushed_files`. They are discovered by diffing container scan results against the host filesystem tree.

**JSON Field:** None — diff-discovered, not persisted
**NodeState Flag:** `container_only: bool`
**UI State:** `FILE_CONTAINER_ONLY` / `FOLDER_CONTAINER_ONLY`
**Operations:** Paste (from clipboard), Remove

Copied files from a **masked** Local Host directory must use the Push workflow instead — direct paste is blocked. Masked files are intentionally hidden project files within the mirrored structure; if they're meant to be visible in the container, they should be Pushed. Copy/Paste is for external, non-project files only.

**Distinction from pushed:** Copied files are ephemeral and untracked. Pushed files are tracked, repeatable, and may be filtered via `FileFilter`.

**Domains:** Container Ops (docker cp), Presentation (ScopeView container-only indicator)

---

### container_only

A visual state for files or folders that exist in the container but not on the host filesystem. Discovered by diffing container scan results (via `scan_container_directory()`) against the host tree. Encompasses both copied files (user-transferred) and container-created files (generated by processes inside the container).

**NodeState Flag:** `container_only: bool`
**Visibility Value:** `"virtual"` — container_only nodes get virtual visibility (Stage 1, highest priority)
**Style:** Dedicated gradient color variable (`visibility.virtual`) with italic font
**File State:** `FILE_CONTAINER_ONLY`
**Folder State:** `FOLDER_CONTAINER_ONLY`

**Not stored in JSON** — derived at runtime from container scan diff.

**Domains:** Computation (Phase 3, diff-based), Presentation (ScopeView Live View Mode)

---

### STENCIL (synthetic node category)

Internal umbrella term for nodes added to the unified tree that are NOT filesystem-backed host entries. Five kinds:

1. **Mirrored intermediates** — directories between a masked root and a revealed descendant, inserted so the container can `mkdir -p` the path (see `mirrored`).
2. **Detached mount roots** — `MountSpecPath` entries with `delivery="detached"` whose container content is cp-delivered (UX label: "Virtual Mount").
3. **L4 auth volume nodes** — per-extension auth mount points injected by container extensions (see `auth volume`).
4. **Container-only folders** — directory entries discovered by container scan diff that have no host counterpart (see `container_only`; distinct bool field, still a stencil category at the tree layer).
5. **Permanent volume nodes** — named-volume stencils for `MountSpecPath` entries with `delivery="volume"` (Phase 3 Task 4.4 shipped). Routed to `FOLDER_STENCIL_VOLUME` via `stencil_tier="volume"`. UX label: "Volume Mount".

**Identifiers (internal — NOT UX):**
- `NodeSource.STENCIL` — MountDataTree source discriminator
- `MountDataNode.is_stencil_node: bool`, `MountDataNode.stencil_tier: str` (values: `mirrored`, `volume`, `auth`)
- `MountSpecPath.get_stencil_paths()` — derives stencil paths from mask/reveal patterns
- `MountSpecPath.owner: str` — `"user"` or `"extension:{name}"`. Discriminates user-authored specs from extension-synthesized specs. Foundation for the unified volume synthesizer, read-only RMB re-key, and volume-name derivation landing in Phase 1 Tasks 1.2–1.10 of `unify-l4-reclaim-isolation-term`. Task 1.1 adds the field; downstream tasks consume it.
- `ExtensionConfig.synthesize_mount_specs() -> list[MountSpecPath]` — unified-synth entrypoint (Phase 1 Task 1.2). Translates `ExtensionConfig.isolation_paths` into container-only named-volume specs (`delivery="volume"`, `content_seed="folder"`, `host_path=None`, `owner="extension:{name}"`). Task 1.3 lands the consumer: `compute_container_hierarchy(extensions=...)` merges the synthesized specs into `mount_specs` at the top of the function, collapsing the inline L4 loop into the existing `_compute_stencil_volumes` pipeline. The `_collect_isolation_paths` helper stays defined (different output shape: `list[tuple[ext_name, path]]`) and retires in Task 1.5 once all internal callers use the `extensions=` kwarg.
- `_compute_stencil_paths_from_config()`, `_cross_reference_stencil_paths()` in `core/node_state.py`
- `display_stencil_nodes: bool` on TreeDisplayConfig
- Theme variables: `stencil.volume`, `stencil.auth`, `inherited.stencil_volume`, `inherited.stencil_auth`, `text_stencil_purple`
- Folder states: `FOLDER_STENCIL_VOLUME`, `FOLDER_STENCIL_AUTH`
- GUI tier routing: `MountDataTreeModel.NodeStencilTierRole` (Qt UserRole+3) returns `node.stencil_tier` for stencil nodes, `"mirrored"` otherwise. `TreeStyleDelegate._resolve_style` reads it and forwards into `resolve_tree_state(state, is_folder, stencil_tier)`.
- L4 auth synthesizer: `MountDataTree._rebuild_l4_stencil_nodes()` (idempotent — drops auth-tier stencils from `root_node.children` then re-emits one per `ExtensionConfig.isolation_paths` entry). Public refresh hook `MountDataTree.set_extensions(list)` for hot install/uninstall.
- Synthetic NodeState injection (GUI-only): for stencil paths CORE never sees, `mount_data_tree._recompute_states` writes `replace(_DEFAULT_NODE_STATE, visibility="virtual")` post-`apply_node_states_from_scope`. Keeps the GUI route through `_resolve_folder_state` without polluting the CORE state pipeline.

**`stencil_tier` taxonomy** (three values; surfaced via `NodeStencilTierRole`, consumed by `resolve_tree_state`):
| Value | Source | Folder state | Theme key |
|---|---|---|---|
| `"mirrored"` | Structural intermediates (CORE Stage 2 — see `mirrored`) | `FOLDER_MIRRORED` family | mirrored stops |
| `"volume"` | `delivery="volume"` mount specs (L_volume tier) | `FOLDER_STENCIL_VOLUME` | `stencil.volume` |
| `"auth"` | Extension `isolation_paths` (L4 — `_rebuild_l4_stencil_nodes`) | `FOLDER_STENCIL_AUTH` | `stencil.auth` |

**Read-only stencil RMB rule (silent-no-op pattern):** Stencil nodes whose lifecycle is owned outside the GUI never expose RMB gestures — the context menu falls through to `_append_fallback_if_empty` ("No valid actions", disabled). Three sites apply this rule today: (a) Project Root Header on LocalHost when no host node is targetable (Phase 2 silent-no-op fix), (b) Project Root Header on Scope Config Tree (Task 4.6), (c) L4 auth stencil nodes in Scope Config Tree (Task 4.9 — container_lifecycle owns the named-volume lifecycle). Mirrored intermediates and `delivery="volume"` stencils route through their normal RMB branches; only auth-tier and header-empty cases short-circuit.

**Distinction from `visibility="virtual"`:** `visibility` is the per-node MatrixState axis returned by `compute_visibility()`; it stays `"virtual"` to preserve the CORE/GUI coloring contract. STENCIL is the category label for *why a node exists*; `visibility="virtual"` is the container-side *state* of that (or any other restricted-with-structure) node. Many stencils end up with `visibility="virtual"`, but the two axes are not interchangeable.

**UX preservation:** User-facing labels keep the word "Virtual" ("Virtual Mount", "Virtual Folders"). Only internal identifiers use `stencil` / `detached`.

**Domains:** Computation (node_state, mount_spec_path), Presentation (MountDataNode, TreeDisplayConfig, theme)

---

### visibility

Computed property representing a node's container-side **STATE** — what the container sees, not how the node got there. METHOD flags (`masked`, `revealed`, `mounted`, etc.) remain on the boolean fields. Visibility is one of exactly 3 values: `accessible`, `restricted`, `virtual`.

**NodeState Field:** `visibility: str`

**Mechanism — ancestor walk:** Raw boolean flags (`mounted`, `masked`, `revealed`) are computed via `is_descendant` checks — walking ancestors to determine if a node falls under a mount, mask, or reveal. These raw flags feed the MatrixState truth table.

**Mechanism — MatrixState truth table:** Derives visibility STATE from raw flag combination (Stage 1, per-node, no tree context needed):

| Value | Condition | Meaning |
|-------|-----------|---------|
| `virtual` | container_only=T, masked=F | Exists in container only — discovered by scan diff |
| `restricted` | container_orphaned=T | Stranded in mask volume, mount removed |
| `accessible` | revealed=T | Content accessible to container via punch-through or mount |
| `restricted` | masked=T AND mounted=T | Content restricted by mask volume overlay |
| `accessible` | mounted=T | Content accessible via bind mount |
| `restricted` | (none of the above) | Not under any mount — not in container |

**Evaluation order:** virtual (container_only) → restricted (orphaned) → accessible (revealed) → restricted (masked+mounted) → accessible (mounted) → restricted (fallback). First match wins.

**Mechanism — descendant walk:** Stage 2 may upgrade `restricted` → `virtual` (config-native queries, no tree walks):

| Upgrade | Condition | Meaning |
|---------|-----------|---------|
| `restricted` → `virtual` | restricted node + has revealed/pushed descendant or mount root below | Structural path — content restricted but directory structure required for container `mkdir` |

`virtual` describes directories whose structure must exist in the container even though their content is restricted. When a masked directory has **revealed** descendants, the intermediate directory structure must be physically constructed in the container via `mkdir` — mirroring the host's folder tree.

Revealed descendants trigger virtual visibility — the intermediate directories need to appear in the Container Scope (ScopeView) so the user can see the structural path to revealed content. Pushed files outside masked areas use a different mechanism: `has_pushed_descendant` ancestry in the proxy filter, not mirrored visibility.

```
Host:                          Container (mask on src/api/):
  src/                           src/
    api/                           api/          ← virtual (mkdir'd, content restricted)
      internal/                      internal/   ← virtual (mkdir'd, content restricted)
        secret.py                      (restricted)
      public/                        public/     ← accessible (bind mount punch-through)
        index.html                     index.html
```

**Note:** masked=T but mounted=F (stale config) falls through to "restricted" (fallback), NOT the masked+mounted row. The `masked` restricted state requires an active mount.

**Implementation status:**
- Stage 1 (`accessible`, `restricted`, `virtual`) → CORE (`core/node_state.py`) via MatrixState in `compute_visibility()`
- Stage 2 (`restricted` → `virtual` upgrade) → CORE (`core/node_state.py`), config-native queries (no tree walks). Controlled by `config.mirrored` toggle. Dual computation: config queries + inverse pattern derivation cross-reference.
- Stage 3 (`has_pushed_descendant`, `has_direct_visible_child`) → CORE (`core/node_state.py`), config-native queries. `has_pushed_descendant` via `LocalMountConfig.has_pushed_descendant()`. `has_direct_visible_child` via single-pass parent collection.

Visibility is NodeState — CORE computes it, GUI reads it as data (Rule 1).

**Domains:** Computation (Phase 3 MatrixState derivation, descendant walk), Presentation (Phase 5 cosmetic feedback)

---

### NodeState

Per-node state model containing all flags that define a filesystem node's identity in the container visibility system. CORE defines rules and computation; GUI hosts runtime instances.

| Field | Type | Source | Scope | Description |
|-------|------|--------|-------|-------------|
| `mounted` | bool | Config (folders) / Ancestor walk (files) | All nodes | Node is under a bind mount |
| `masked` | bool | Config (folders) / Ancestor walk (files) | All nodes | Path is under a mask volume |
| `revealed` | bool | Config (folders) / Ancestor walk (files) | All nodes | User punched through a mask |
| `pushed` | bool | Config | Files only | File was docker cp'd into container |
| `container_orphaned` | bool | MatrixState (TTFF) | Files only | pushed + masked + not mounted + not revealed |
| `visibility` | str | MatrixState + config queries | All nodes | accessible / restricted / virtual (pure STATE) |
| `has_pushed_descendant` | bool | Config query (Phase 3 Stage 3) | Folders only | Any descendant has pushed=True |
| `has_direct_visible_child` | bool | States pass (Phase 3 Stage 3) | Folders only | Immediate child has revealed=True or pushed=True |
| `host_orphaned` | bool | Set difference (DEFERRED) | Files only | pushed=T AND host file missing |

`virtual` derived via config-native queries — CORE (`core/node_state.py`), controlled by `config.mirrored` toggle. No tree walks. GUI uses CORE results only.

Config `mount_specs` are evaluated via pathspec to produce per-node NodeState boolean flags. The mapping is `mount_specs → pathspec eval → (mounted, masked, revealed)`, not a direct 1:1 JSON field mapping.
Full state model: 22 states (14 folder + 8 file) + 2 selected overrides — see `GUI_STATE_STYLES.md` Section 3.

**Domains:** Config (1:1 field mapping), Computation (Phase 3 state application), Presentation (Phase 5 cosmetic rendering)

---

### MatrixState

Design pattern for deriving computed state from NodeState boolean flags. Each flag is computed as **raw data** (independent of other flags), then specific flag combinations are checked as explicit matrix rows rather than cascading if/return chains.

**Principle:** Boolean flags record what IS true about a path. Derived state checks explicit combinations of those flags.

**Container orphan detection matrix:**

```
pushed  masked  mounted  revealed  ->  result
  T       T       F        F          container_orphaned  (stranded in mask volume)
  *       *       *        *          not orphaned
```

**Visibility derivation matrix (pure STATE output):**

```
container_only  container_orphaned  revealed  masked  mounted  ->  state
      T               *               *         F       *          "virtual"
      F               T               *         *       *          "restricted"
      F               F               T         *       *          "accessible"
      F               F               F         T       T          "restricted"
      F               F               F         F       T          "accessible"
      F               F               F         *       F          "restricted"
```

Note: `masked=T, mounted=F` falls through to "restricted" (last row), NOT the masked+mounted row. The `masked` restricted state requires an active mount. Stage 2 may upgrade `restricted` → `virtual` for structural paths.

**Why not cascading if/return:** A flag like `masked` must be raw data (does a mask volume cover this path?) not gated on another flag (`mounted`). Gating at the data level creates contradictions — e.g., `orphaned = pushed AND masked AND NOT mounted` becomes unsatisfiable if `masked` requires `mounted`. The matrix pattern keeps data and derivation separate.

**Upstream step — Pathspec Evaluation:** Before MatrixState, `compute_node_state_from_specs()` evaluates each path against the owning `MountSpecPath`'s gitignore-style patterns using `pathspec`. This cascading, last-match-wins evaluation produces the raw boolean flags (`mounted`, `masked`, `revealed`) that MatrixState then combines. Two patterns, two layers — pathspec evaluation is NOT MatrixState; it feeds INTO it.

**Implementation:** `core/node_state.py` — `compute_node_state_from_specs()` evaluates pathspec → raw flags, `compute_visibility()` reads the matrix.

**Domains:** Computation (Phase 3 state derivation)

---

## Path Terms

### host_ prefix convention

The `host_` prefix denotes a path that lives on the host machine, external to the Docker container. All `host_`-prefixed variables are absolute OS paths. Container-side equivalents omit the prefix (e.g., `host_project_root` on host, `container_root` in container).

### Two Host Roots

The system has exactly **two host roots**. Everything else derives from their relationship.

| Root | Role | Example |
|------|------|---------|
| `host_project_root` | Project directory — IDE root, config anchor, GUI opens here | `E:\Games\MyGame` |
| `host_container_root` | Ancestor directory — contains project AND siblings. All `relative_to()` calls use this as base. | `E:\Games` |

Default: `host_project_root.parent`. The project name is naturally part of the `relative_to()` result, giving clean container paths like `/{parent.name}/MyGame/src`.

```
host_container_root/         →    container_root/
  MyGame/                    →      MyGame/          ← host_project_root (relative offset)
  SharedLib/                 →      SharedLib/        ← sibling
```

**Domains:** Config, Orchestration, Computation (relative path base), Presentation (GUI scanning root)

---

### host_project_root

Main project directory where user code lives. The IDE root directory. Config anchor — sibling config structure (`.{name}_igsc/`) is relative to this. Always within `host_container_root`.

**Derived relationship:** `host_project_root.relative_to(host_container_root)` = project offset inside container.

**Domains:** Config (anchor), Orchestration (entry point), Presentation (LocalHostView scanning root)

---

### host_container_root

Ancestor directory that contains `host_project_root` and all sibling directories. Can be the same as `host_project_root` (flat project, no siblings) or multiple levels above it. Maps 1:1 to `container_root`.

All mount/mask/reveal paths are made relative to `host_container_root` for container path computation.

**Default:** `host_project_root.parent`
**JSON storage:** Relative to `host_project_root` (e.g., `".."`) per DATAFLOWCHART Rule 10
**Constraint:** Must be an ancestor of (or equal to) `host_project_root`.

**Domains:** Config, Computation (relative path base for all volume entries), Generation (bind mount source paths)

---

### container_root

Base path inside the Docker container where `host_container_root` content is mounted.

**Default:** Mirrored-aware derivation:
  - mirrored=True → `/{host_container_root.name}`
  - mirrored=False → `/workspace` (DEFAULT_CONTAINER_ROOT)
**JSON Field:** `container_root` (overridable)

```
/Games/                  ← container_root (= /{host_container_root.name})
  MyGame/                ← project offset (= host_project_root relative to host_container_root)
    src/
  SharedLib/             ← sibling (same level as project)
  .claude/               ← auth volume mount point
```

When `host_container_root` = `host_project_root` (no siblings):
```
/MyGame/                 ← container_root (= /{host_project_root.name})
  src/                   ← project content directly under root
  .claude/
```

**Domains:** Config, Computation, Generation (WORKDIR, volume targets), Container Ops (docker cp targets)

---

### container path formula

The formula for computing a container-side path from a host-side path:
```
{container_root}/{rel_path}
```
Where `rel_path = host_path.relative_to(host_container_root)`

Example (with siblings): `/Games/MyGame/src/core/player.py`
Example (flat project): `/MyGame/src/core/player.py`

The project name is **not a separate parameter** — it's naturally included in `rel_path` when `host_container_root` is above `host_project_root`.

**Plan layout mapping:** When Phase 1 configures `host_container_root = host_project_root.parent`, the container path formula produces `/{parent.name}/{project_name}/...`. The flow chart's `/{Project}/` layout is the common case where `host_container_root.name` becomes the container root and the project name is the first path segment underneath. Example: `host_container_root = E:\Games` → `container_root = /Games` → project at `/Games/MyGame/`.

**Edge case:** When `host_container_root` is a drive root (e.g., `E:\`), `host_container_root.name` is empty, producing `container_root = "/"` and paths like `//Project/...`. POSIX treats `//` as `/` — functionally correct but unclean.

Prescribed as a single centralized function by Rule 5.

**Domains:** Config (centralized function), Computation (volume entries), Generation (YAML strings), Container Ops (docker cp paths), Orchestration (push/pull paths), Presentation (GUI push/pull paths)

---

### local_host_root

Ancestor directory of `host_project_root`, stored as a reference for future "scan all children" feature. NOT scanned by default — only `host_project_root` and declared siblings are scanned.

**JSON:** Stored as relative path from `host_project_root` (e.g., `".."`)
**Default:** `host_project_root.parent`
**Constraint:** Must be an ancestor of `host_project_root` (DATAFLOWCHART Rule 2).

**Domains:** Config, Presentation (future scanning root)

---

### host_path

Absolute path on the host machine for SiblingMount source directories. Siblings use absolute paths because they can be anywhere on the OS, including different drives.

**JSON:** Stored as absolute (exception to DATAFLOWCHART Rule 10).
**Relative base:** Made relative to `host_container_root` for container path computation.

**Domains:** Config (SiblingMount field)

---

### igsc

Abbreviation for "IgnoreScope Containers." Suffix for sibling config directories: `.{project}_igsc/`.

```
{parent}/
├── MyGame/                ← host_project_root
└── .MyGame_igsc/          ← config root
    ├── .dev/              ← scope config
    │   └── scope_docker.json
    └── .prod/
```

Auto-masked to prevent config directory appearing in container (DATAFLOWCHART Rule 11).

**Domains:** Config (path helpers)

---

## Docker Terms

### auth volume

Named Docker volume that persists LLM credentials across container rebuilds. Mounted at `/root/.claude`.

**Naming:** `{docker_name}-claude-auth`
**Persistence:** Survives stop/start and `docker compose up/down`. Destroyed by `down -v`.

**Domains:** Generation (docker-compose.yml volumes section)

---

### mask volume

Named Docker volume that overlays a bind-mounted directory, hiding its original content. Starts empty (this is what makes masking work). Accumulates pushed exception files at runtime via `docker cp`.

**Naming:** `mask_{sanitized_rel_path}` (e.g., `mask_src_vendor`)
**Persistence:** Same as auth volume — survives stop/start, destroyed by `down -v`.

Two volume types hold persistent data:

| Volume | Contents | Loss Impact |
|--------|----------|-------------|
| Auth volume | LLM credentials | Must re-authenticate |
| Mask volume(s) | Pushed exception files | Pushed files lost, must re-push |

**Domains:** Computation (Layer 2 volume entries), Generation (docker-compose.yml), Container Ops (volume_exists check, docker cp target), Utility (volume name sanitization)

---

### volume layering order

Docker-compose volumes are applied in declaration order. Later volumes overlay earlier ones (last-writer-wins). Volumes are generated **per MountSpecPath in pattern order**, enabling interleaved mask/reveal at arbitrary depth:

```
For each MountSpecPath:
  1. Layer 1 — emitted iff delivery == "bind":
       Bind mount (mount_root)                  — base visibility, live host link
     (If delivery == "detached", Layer 1 is NOT emitted.
      Content is cp'd into the container at init time instead — container-only copy.
      If delivery == "volume", Layer 1 is NOT emitted.
      A named Docker volume is emitted in the L_volume tier instead.)
  2. For each pattern in order (applies to bind + detached delivery):
     - Non-negated (e.g., "vendor/")            — named mask volume (hides)
     - Negated (e.g., "!vendor/public/")        — bind mount punch-through (reveals)
     - Non-negated (e.g., "vendor/public/tmp/") — named mask volume (re-hides)
  ...
For each Sibling (same pattern-order structure)
L_volume: Stencil volumes                        — named Docker volumes for
                                                    delivery="volume" specs,
                                                    emitted in mount_specs order
                                                    after L1-L3 and before L4
Final:    Isolation volumes                      — persistent, container-owned (Layer 4)
```

Pattern order = volume declaration order = correct nested layering. A reveal after a mask re-exposes content; a mask after a reveal re-hides a subfolder within it.

**Detached delivery mechanics:** masks within a detached mount are enforced post-cp via `docker exec rm -rf` of the masked subtree; reveals are included in the initial cp walk. See **Mount Delivery Terms** for the full gesture set.

**Stencil volumes (L_volume):** Named volumes backing `delivery="volume"` specs (the Permanent Folder → Volume Mount UX tier). Volume naming: `stencil_{spec_index}_{sanitized_container_path}`. `spec_index` is the position of the spec within `mount_specs` (in-scope ordering), giving stable names across config round-trip. Cross-scope uniqueness comes from docker compose project namespacing (no explicit `name:` on the declaration — matches the mask-volume pattern, not the auth-volume pattern). `content_seed="folder"` is required; tree-seed into a named volume is not supported at this phase.

**Isolation (Layer 4):** Named volumes backing extension install paths (e.g., `/root/.local` for Claude). Declared via `ExtensionConfig.isolation_paths` and — from Phase 1 Task 1.3 onward — materialized through the unified-synth pipeline: `ExtensionConfig.synthesize_mount_specs()` emits owner-tagged `delivery="volume"` specs that `compute_container_hierarchy` merges into `mount_specs` and renders via `_compute_stencil_volumes`. L4 output therefore surfaces on `ContainerHierarchy.stencil_volume_entries` / `stencil_volume_names` under the interim `stencil_{idx}_{path}` naming scheme (Task 1.4 renames to `vol_{owner_segment}_{path}`). The legacy `isolation_volume_entries` / `isolation_volume_names` fields and the `iso_{ext}_{path}` naming stay as zero-populated vestiges pending formal removal in Task 1.4. Nothing punches through isolation — it is the final overlay. Orthogonal to user-authored mount_specs delivery modes — L4 volumes are emitted regardless.

**Domains:** Computation (core/hierarchy.py computes ordering), Generation (docker/compose.py formats into YAML)

---

### MountSpecPath

Dataclass representing a single mount root with an ordered list of gitignore-style patterns controlling which subdirectories are masked (hidden) or unmasked (revealed) within that mount, plus a `delivery` mode selecting how the content reaches the container.

**Module:** `core/mount_spec_path.py`
**Fields:**
- `mount_root: Path` — absolute path to the mount root. Interpreted as a host path when `host_path` is set; interpreted as a container-logical path when `host_path is None` (container-only specs produced by the Scope Config "Make Folder" family).
- `patterns: list[str]` — ordered gitignore-style patterns, relative to mount_root
- `delivery: Literal["bind", "detached", "volume"] = "bind"` — how content is delivered to the container. `"bind"` emits a live bind-mount (host changes propagate). `"detached"` emits no bind-mount and instead cp's the content at container create (container-only copy, no live host link; destroyed on recreate unless `preserve_on_update`). `"volume"` emits a named Docker volume (survives ordinary recreate; destroyed only via `docker compose down -v`). See **Mount Delivery Terms** section.
- `host_path: Optional[Path] = None` — host-side source for content. `None` = container-only (no host read side). Required when `delivery == "bind"` — auto-filled from `mount_root` by `__post_init__` for legacy Phase 1/2 construction.
- `content_seed: Literal["tree", "folder"] = "tree"` — controls initial container-side content for non-bind specs. `"tree"` cp-walks the whole subtree from host (Phase 1 behavior). `"folder"` only `mkdir -p`'s the mount root; content is filled via `pushed_files` or inside-container writes.
- `preserve_on_update: bool = False` — if `True`, the update lifecycle cp's this spec's container contents to a host tmp staging area across recreate. Only valid when `delivery == "detached"` and `content_seed == "folder"` (tree-seed specs re-read from host; `delivery="volume"` survives natively).
- `owner: str = "user"` — provenance tag. `"user"` for user-authored specs (default). `"extension:{name}"` (e.g. `"extension:claude"`) for extension-synthesized specs. Load-bearing for unified volume naming, GUI read-only RMB gating, and Scope Config header signal derivation across Phase 1 Tasks 1.2–1.10 of `unify-l4-reclaim-isolation-term`. Validated to `"user"` or `"extension:{non-empty-name}"` format; no other shapes permitted. Round-trippable as a flat string (extension name embedded) so the spec stays self-describing.

**Pattern syntax (gitignore native, applies to both delivery modes):**
- `"vendor/"` — mask (deny) the vendor directory
- `"!vendor/public/"` — unmask (exception) vendor/public
- `"vendor/public/tmp/"` — re-mask vendor/public/tmp

**Evaluation:** Uses `pathspec` library with `gitignore` mode. Last matching pattern wins.
**Methods:** `add_pattern()`, `remove_pattern()`, `move_pattern()`, `is_masked(path)`, `is_unmasked(path)`, `get_masked_paths()`, `get_revealed_paths()`, `get_stencil_paths()`, `validate()`, `validate_no_overlap(specs)`

**Mount overlap rule:** No mount root can be a descendant of another mount root, regardless of delivery. Hard block validated by `validate_no_overlap()`.

**Cross-field validator constraints (Phase 3):**
- `host_path is None` → `delivery != "bind"` (bind needs a host source)
- `delivery == "volume"` → `content_seed == "folder"` (no tree-seeding into a named volume at this phase)
- `preserve_on_update == True` → `delivery == "detached"` and `content_seed == "folder"` (meaningless elsewhere)
- `owner` format: `"user"` or `"extension:{non-empty-name}"` (no other shapes accepted)

**JSON format:**
```json
"mount_specs": [
  {"mount_root": "src", "patterns": ["vendor/", "!vendor/public/"], "delivery": "bind"},
  {"mount_root": "src/generated", "patterns": [], "delivery": "detached"},
  {"mount_root": "/container/scratch", "patterns": [], "delivery": "detached", "content_seed": "folder", "preserve_on_update": true},
  {"mount_root": "/container/cache", "patterns": [], "delivery": "volume", "content_seed": "folder"},
  {"mount_root": "/root/.claude", "patterns": [], "delivery": "volume", "content_seed": "folder", "owner": "extension:claude"}
]
```

`delivery` defaults to `"bind"` on read (backward-compatible with pre-0.5 configs). `host_path`, `content_seed`, `preserve_on_update`, and `owner` are omitted from JSON when at their defaults, so Phase 1/2 configs round-trip unchanged.

**Domains:** Config (mount_spec_path.py), Computation (node_state.py pathspec eval, hierarchy.py volume generation), Presentation (future rule list panel)

---

## Mount Delivery Terms

Per-spec `delivery` mode on `MountSpecPath` (`"bind"`, `"detached"`, or `"volume"`; default `"bind"`) selects how mount content reaches the container. Introduced in 0.5 to replace the earlier scope-level `container_mode` binary; extended in Phase 3 with the `"volume"` tier and container-only (`host_path is None`) specs. A single scope may mix delivery modes across its mount_specs — each spec is independent.

**Seed & persistence fields (Phase 3):**
- `host_path: Optional[Path]` — host-side source. `None` = container-only (produced by Scope Config "Make Folder" family).
- `content_seed: Literal["tree", "folder"]` — `"tree"` cp-walks the whole host subtree (Phase 1 behavior); `"folder"` only `mkdir -p`'s the mount root. Non-bind specs only.
- `preserve_on_update: bool` — soft-permanent flag for `delivery="detached" + content_seed="folder"` specs. Update lifecycle cp's contents to a host tmp stage across recreate. Meaningless (and validator-rejected) on other combinations.

### Mount (delivery="bind")

The default delivery. Live bind-mount declared in `docker-compose.yml`. Host changes propagate into the container immediately; container-side edits (where not masked) write through to the host. Masks (named volumes) and reveals (bind punch-throughs) layer over the bind in pattern order.

**UX label:** "Mount" (RMB gesture). No visible delivery modifier — "Mount" always means bind.
**Persistence:** Nothing to replay on container recreate — the bind re-attaches host state.

**Domains:** Generation (compose L1 bind entry), Lifecycle (no init step)

---

### Virtual Mount (delivery="detached")

Detached-snapshot delivery. No bind-mount is emitted for the mount_root; the content is cp'd into the container's filesystem at create time and lives in the container's writable layer. Host edits after create do NOT affect the container. Container edits do NOT flow back to the host.

**UX label:** "Virtual Mount" (RMB gesture). The term "virtual" aligns with `visibility.virtual` in `NodeState` — container-only content — but the underlying field value is `delivery="detached"`. Internal synthetic-node identifiers use `stencil` (`NodeSource.STENCIL`, `MountSpecPath.get_stencil_paths()`, `MountDataNode.is_stencil_node`) so that only the `visibility="virtual"` MatrixState axis retains the `virtual` vocabulary.
**Persistence:** Container writable-layer content is lost on recreate. `_detached_init` replays the cp walk on every create; `pushed_files` replay follows.
**Masks inside:** post-cp `docker exec rm -rf` of masked subtree. Reveals inside: included in the cp walk.
**Overlap:** same `validate_no_overlap` rule as bind — no ancestor/descendant overlap with any other mount_spec regardless of delivery.

**Domains:** Generation (compose — no L1 emitted), Lifecycle (`_detached_init_cp` walk at create + recreate), Config (delivery field on MountSpecPath)

---

### Virtual Folder (delivery="detached", content_seed="folder")

Folder-seeded variant of Virtual Mount. No cp walk — just `docker exec mkdir -p <container_path>` at create. `pushed_files` still applies (users populate content explicitly via push or inside-container writes). Can be host-backed (LocalHost "Virtual Folder" gesture, `host_path` set) or container-only (Scope Config "Make Folder" gesture, `host_path is None`).

**UX label:** "Virtual Folder" (LocalHost tree RMB) / "Make Folder" (Scope Config tree RMB).
**Persistence:** Same as Virtual Mount — container-layer content lost on recreate unless `preserve_on_update=True`.
**Masks/reveals:** Not applicable — folder-seed specs have no walked tree to mask. Validator rejects patterns on folder-seed specs.

**Domains:** Generation (compose — no L1, no cp walk), Lifecycle (`_detached_init` emits mkdir only), Config (`add_stencil_folder()` constructor on LocalMountConfig)

---

### Permanent Folder — No Recreate (delivery="detached", content_seed="folder", preserve_on_update=True)

Soft-permanent variant. Update lifecycle cp's folder contents to a host tmp staging area before recreate, then cp's them back after the new container is up. Survives ordinary `execute_update`, destroyed only if cp-out fails (fail-safe: old container stays running) or user explicitly removes.

**UX label:** "Make Permanent Folder → No Recreate" (Scope Config RMB) or "Mark Permanent" gesture on an existing Virtual Folder.
**Persistence:** Lifecycle-preserved. Lost on explicit Remove.
**Tradeoff vs. volume tier:** cheaper (no volume bookkeeping), but cp-copy overhead on every update.

**Domains:** Lifecycle (`_preserve_detached_folders` hook), Config (`preserve_on_update` field)

---

### Permanent Folder — Volume Mount (delivery="volume", content_seed="folder")

Hard-permanent variant. Backed by a Docker named volume emitted in compose. Survives `docker compose up` with arbitrary config changes; content is stored by Docker outside the container layer. Destroyed only by explicit `docker compose down -v` (recreate path warns and redirects user to the Diff view when available).

**UX label:** "Make Permanent Folder → Volume Mount" (Scope Config RMB). Container-only (no host_path). Does not support host-backed volume-tier specs in Phase 3.
**Persistence:** Native Docker volume persistence.
**Constraints:** `content_seed` must be `"folder"` — no tree-seeding into a named volume at this phase. `preserve_on_update` is meaningless (volume survives natively) and validator-rejected.
**Volume naming:** `stencil_{spec_index}_{sanitized_container_path}` — `spec_index` is the position within `mount_specs`, `sanitized_container_path` is the container-logical path with slashes flattened and sanitized via `sanitize_volume_name`. Names are stable across config round-trip. Cross-scope uniqueness comes from docker compose project namespacing (no explicit `name:` on the declaration). See also **volume layering order → Stencil volumes (L_volume)**.

**Domains:** Generation (compose — named volume entry + top-level `volumes:`), Config (`add_stencil_volume()` constructor)

---

### CLI surface (mount delivery)

Phase 3 Task 4.8 surfaces every Mount Delivery gesture on the `python -m IgnoreScope` CLI. Each command mirrors a GUI gesture and persists via `save_config` only — no implicit container recreate. Container-affecting gestures append a recreate hint to the success message when a container exists.

| UX gesture | CLI invocation |
|---|---|
| Mount | `add-mount <host_path>` (default `--delivery bind --seed tree`) |
| Virtual Mount | `add-mount <host_path> --delivery detached` |
| Virtual Folder | `add-mount <host_path> --delivery detached --seed folder` |
| Make Folder | `add-folder <container_path>` |
| Make Permanent Folder → No Recreate | `add-folder <container_path> --permanent` |
| Make Permanent Folder → Volume Mount | `add-folder <container_path> --volume` |
| Mark Permanent (existing detached folder) | `mark-permanent <container_path>` |
| Unmark Permanent | `unmark-permanent <container_path>` |
| Convert to Mount / Virtual Mount | `convert <host_path> --to {bind,detached}` |

`--permanent` and `--volume` are mutually exclusive on `add-folder`. `--seed folder` requires `--delivery detached` on `add-mount`. `mark-permanent` / `unmark-permanent` reject any spec that is not `delivery="detached" + content_seed="folder"` with a clear message — volume specs and tree-seed specs cannot be flipped.

**Persistence parity:** Container-only `mount_root` paths (`host_path is None`) are stored as-written and round-trip correctly through `MountSpecPath.from_dict` (no host-path resolution that would prepend a Windows drive letter). This parity is required for `mark-permanent` / `unmark-permanent` to find the spec across reload boundaries.

**Domains:** CLI (commands.py + interactive.py wrappers), Config (delegates to LocalMountConfig constructors)

---

### Six RMB gestures (tree node + Project Root Header)

The RMB action set at both the tree-node level and the Project Root Header depends on the current state of the target path:

| State | Container exists? | Actions available |
|---|---|---|
| Neither Mount nor Virtual Mount set | — | **Mount**, **Virtual Mount**, **Virtual Folder** |
| Mount | no | **Unmount**, **Convert to Virtual Mount** |
| Mount | yes | **Unmount**, **Convert to Virtual Mount** ⚠️ recreates container |
| Virtual Mount | no | **Remove Virtual Mount**, **Convert to Mount**, **Remove But Keep Children** |
| Virtual Mount | yes | **Remove Virtual Mount**, **Convert to Mount**, **Remove But Keep Children**, **Remove Folder from Container** (transient), **Remove Folder Tree from Container** (permanent) |

**Convert gestures** toggle `delivery` on the existing `MountSpecPath` entry. When a container exists, a recreate-confirmation dialog fires (Docker has no hot-attach/detach for volumes — conversion requires `execute_update`'s recreate pipeline).

**Remove But Keep Children** — a Virtual-Mount-only restructuring gesture. Enumerates direct host children of the current `mount_root`, replaces the parent entry with N child entries (each a Virtual Mount of the corresponding child), preserving the existing pattern engine on each child. Used when the user wants finer-grained tracking than a single parent entry.

**Remove Folder from Container (transient)** — `docker exec rm -rf <container_path>` only. Config unchanged. Next recreate replays the detached cp, restoring the folder.

**Remove Folder Tree from Container (permanent)** — `docker exec rm -rf` plus delete the config entry. Folder is permanently absent from the scope.

Shift-select supports batch Remove across multiple Virtual Mount entries.

**Domains:** Presentation (local_host_view RMB + Project Root Header RMB), Config (toggle/remove on LocalMountConfig), Lifecycle (convert triggers recreate)

---

### Mount Delivery header cue

The Project Root Header in the GUI tints to indicate the active scope's dominant delivery mode across its `mount_specs`:
- All specs `delivery="bind"` → `config.mount` theme color (Mount-consistent)
- All specs `delivery="detached"` → `visibility.virtual` theme color (container-only-consistent)
- Mixed (some bind, some detached) → majority-by-spec-count wins. Ties resolve to `config.mount`.
- Empty scope (no mount_specs) → default panel-header color.

Selection mechanism and QSS details are an implementation concern of `gui/local_host_view.py` and the theme stylesheet.

**Domains:** Presentation (GUI theme), Config (delivery read)

---

### Detached symlink placeholder (guidance)

Detached delivery uses a conservative policy for host symlinks and Windows junctions inside a scoped mount: create the container-side directory stub at the symlink's location, but do not traverse into the symlink target. The directory appears in the container's listing so downstream tooling sees the expected structure; populating it is left to the user via manual `docker cp` / `scope push` later.

**Rationale:** Scoped trees often contain Perforce/UE5 junctions that could silently deref gigabytes if followed. Skip-and-stub is safe by default; users opt in to content by pushing explicitly.

**Deferred Presentation (Phase 2+):** a dedicated deferred-style node state can indicate a placeholder directory that exists in the container but has not been populated. Not shipped in Phase 1.

**Domains:** Lifecycle (detached init), Presentation (future deferred-style state for symlink nodes)

---

### Update lifecycle (`execute_update` phases)

Container update flow recreates the container while preserving content for `preserve_on_update` specs and the named-volume L_volume tier. Numbered phases from `docker/container_lifecycle.py` (canonical numbering — narrative descriptions in `COREFLOWCHART.md` may use prose names alongside these numbers):

- **Phase 4b — `_preserve_detached_folders`** — fail-safe stage. Iterates `mount_specs` for `delivery="detached" + content_seed="folder" + preserve_on_update=True` entries; cp's contents from old container to a host tmp staging area. **Aborts the entire update on cp-out failure** — the old container is left running so no data is destroyed.
- **Phase 8b — `_restore_detached_folders`** — restore stage. Re-cp's the staged contents into the freshly recreated container via `push_directory_contents_to_container`. Failure here is **non-fatal**: warns the user, leaves the new container running with empty content for that spec. Tmp staging is cleaned up in a `finally` block whether restore succeeds or not.

**Soft-permanent vs hard-permanent tier:**
- *Soft-permanent* — `delivery="detached" + content_seed="folder" + preserve_on_update=True`. Survives `execute_update` recreate via the Phase 4b/8b cp staging hop. Destroyed by `docker compose down`. UX label: "Make Permanent Folder → No Recreate" / "Mark Permanent".
- *Hard-permanent* — `delivery="volume" + content_seed="folder"`. Survives recreate natively (Docker named volume). Destroyed only by `docker compose down -v`. UX label: "Make Permanent Folder → Volume Mount".

**Domains:** Lifecycle (`docker/container_lifecycle.py`), Config (`MountSpecPath.preserve_on_update` validator)

---

### `push_directory_contents_to_container` (`/.` merge idiom)

`docker/container_ops.py` primitive used by Phase 8b restore (and any other "merge contents into existing container directory" path). Wraps `docker cp <src>/. <container>:<dst>` — the trailing `/.` tells Docker to copy directory **contents** rather than the directory itself, so the destination merges with existing children instead of nesting under a same-named subdirectory. Distinct from `push_file_to_container` (single file) and `_detached_init`'s tree cp (whole-subtree initial seeding).

**Domains:** Lifecycle (`docker/container_ops.py`)

---

### `recreateRequested` signal

Qt signal emitted by `ScopeView` when a Scope Config Tree gesture (Task 4.6) produces a config change that requires container recreate (e.g., "Make Permanent Folder → Volume Mount" on a scope with an existing container). The host application connects it to the existing recreate-confirmation dialog. Decouples config mutation from lifecycle invocation — config writes are immediate; recreate is gated on user confirm.

**Domains:** Presentation (`gui/scope_view.py` emit, host app slot)

---

## Container Extensions / CLI Deployment Terms

### Claude CLI

The Claude Code command-line client, installed at `/root/.local/bin/claude` inside the container. Connects to Anthropic's cloud API — no local model runs in the container. Installed via `curl -fsSL https://claude.ai/install.sh | bash`.

**Binary:** `/root/.local/bin/claude`
**Auth:** Persisted via named Docker volume at `/root/.claude` (see auth volume)
**Lifecycle:** Binary is ephemeral (in container writable layer, lost on removal). Auth volume persists across rebuilds.

**Domains:** Container Extensions (ClaudeInstaller), Container Ops (docker exec installation), Presentation (menu actions)

---

### GitInstaller

Installs Git inside a running container via `docker exec`. Follows the same `ExtensionInstaller` abstract base class pattern as `ClaudeInstaller`.

**Domains:** Container Extensions (git_extension.py), Container Ops (docker exec installation), Presentation (menu actions)

---

### Runtime Install

Deployment method that installs a CLI tool into an already-running container via `docker exec`. The production pipeline — wired to the "Install Claude CLI" / "Install Git" menu actions.

**Flow:** `deploy_llm_to_container()` → `DeployWorker` → `ClaudeInstaller.deploy_runtime(method=FULL)`
**Steps:** Install curl/ca-certificates → run installer script → verify binary
**Counterpart:** MINIMAL (assumes deps present) — SHELVED, not called from production code.

**Domains:** Container Extensions (install_extension.py, claude_extension.py, git_extension.py), Presentation (container_ops_ui.py)

### Extension Reconciliation

Post-start verification loop that compares desired state (`config.extensions`) against actual state (binary presence in container) and takes corrective action.

**Extension state values:** `"" | "deploy" | "installed" | "remove"`
- `""` (empty) — not extension-managed (default for project/sibling configs)
- `"deploy"` — user requested install, pending execution
- `"installed"` — successfully deployed and verified
- `"remove"` — user requested uninstall, pending execution (Phase 5)

**State matrix:**

| Config State | Binary Present | Binary Missing |
|---|---|---|
| `deploy` | → state becomes `installed` | → `deploy_runtime()` → `installed` |
| `installed` | → no-op | → `deploy_runtime()` (recreate recovery) → `installed` |
| `remove` | → no-op (Phase 5) | → no-op (Phase 5) |
| `""` | → skipped | → skipped |

**Flow:** `reconcile_extensions(container_name, config)` → for each extension: `get_installer()` → `verify()` → state matrix → mutate config in-place
**Called from:** `execute_create()`, `execute_update()` (post-start, non-fatal)
**Key property:** Caller saves config — reconcile only mutates in-place.

**`get_installer(installer_class: str)`** — resolves `ExtensionConfig.installer_class` string to a default-constructed `ExtensionInstaller` instance via `_INSTALLER_REGISTRY` dict in `container_ext/__init__.py`. Returns `None` for unknown class names. Single source of truth for config→runtime installer lookup.

**Domains:** Docker Layer (container_lifecycle.py), Container Extensions (get_installer in __init__.py)

---

## Configuration Terms

### scope

Named container configuration namespace. Each scope has a config directory (`.{project}_igsc/.{scope_name}/`) and optionally a Docker container instance.

**GUI:** "Scopes" menu
**CLI:** `--container NAME` argument

A scope is the configuration identity. A Docker container is the runtime instance. Multiple scopes can exist; each scope may or may not have a running Docker container.

**Domains:** Config, Orchestration (scope switching, creation, deletion), Presentation (Scopes menu)

---

### Scope vs Container (Naming Convention)

| Context | Term | Example |
|---------|------|---------|
| GUI (panels, headers, menus) | Scope | "Container: dev -running" |
| CLI (`--container` argument) | Container | `--container dev` |

Both resolve to the same `scope_docker.json` config and Docker instance.

---

### container (Ambiguous — Three Meanings)

Context-dependent term with three distinct meanings:

| Context | Meaning | Example | Disambiguation |
|---------|---------|---------|----------------|
| Docker runtime | Running/stopped Docker instance | "start the container" | Use "Docker container" |
| Config namespace | Named configuration set | `--container dev` | Use "scope" (GUI) or "container config" (CLI) |
| Container path | Mount point inside Docker | `container_root` | Use "container path" or "container root" |

COREFLOWCHART uses "container" for Docker runtime. DATAFLOWCHART uses "scope" for GUI config namespace.

---

### container_files

Set of file paths discovered inside the container that were NOT pushed from the host. Files created by container processes at runtime (log files, cache files, build artifacts).

**JSON Field:** `container_files[]`

Feature not yet wired. Discovery function exists as utility; ScopeView has a disabled "Scan for New Files" action.

**Domains:** Config, Container Ops (discovery utility), Presentation (future ScopeView display)

---

### dev_mode

Safety toggle for pull operations. When enabled, pulled files are written to a timestamped subdirectory instead of overwriting originals.

**JSON Field:** `dev_mode`
**Default:** `True` (safe mode)

| Mode | Pull destination | Risk |
|------|-----------------|------|
| True | `{host_project_root}/Pulled/{timestamp}/{rel_path}` | None — originals untouched |
| False | `{host_project_root}/{rel_path}` (overwrite) | Overwrites host files |

**Domains:** Config, Orchestration (pull output path), Presentation (GUI pull output path)

---

### mirrored

Config toggle controlling Stage 2 visibility computation and intermediate directory creation in masked areas.

**JSON Field:** `mirrored`
**Default:** `True`
**ScopeDockerConfig field:** `mirrored: bool = True`

| Mode | Stage 2 visibility | Container mkdir | Effect |
|------|-------------------|----------------|--------|
| True | Masked dirs with **revealed** descendants → `"virtual"` | Intermediate dirs between mask roots and reveals get `mkdir -p` | Container directory tree mirrors host structure within masked areas |
| False | Stage 2 skipped — restricted stays `"restricted"` | No mirrored mkdir — only pushed file parents get `mkdir -p` | Reveals still work (Docker bind mounts) but intermediate dirs absent |

**Implementation:**
- Stage 2 visibility: `core/node_state.py` — `find_mirrored_paths()`, called by `apply_node_states_from_scope()`
- Mirrored mkdir: `core/hierarchy.py` — `_compute_mirrored_parents()`, called by `compute_container_hierarchy()`

**Domains:** Config, Computation (Stage 2 visibility + hierarchy mkdir)

---

## Presentation Terms

### MountDataNode

Per-node data object in the unified tree. Represents a single filesystem entry (file or folder).

| Field | Type | Description |
|-------|------|-------------|
| `is_file` | bool | True for files, False for folders |
| `is_stencil_node` | bool | True for stencil entries (synthetic, not filesystem-backed) |
| `source` | NodeSource | PROJECT, SIBLING, or STENCIL |
| `container_path` | str | Target path in container (sibling nodes) |

Column availability per node is controlled by ColumnDef guards (`files_only`, `folders_only`), not by node type directly.

**Domains:** Presentation (tree data layer)

---

### MountDataTree

Single shared data model (QObject) backing both LocalHostView and ScopeView. Hosts config data (mount_specs, pushed_files), sibling nodes, and state computation. Currently maintains internal flat sets (`_mounts`, `_masked`, `_revealed`) as a transition bridge — future Phase 4a will convert to native mount_specs. Two MountDataTreeModel instances wrap the same tree with different TreeDisplayConfig subclasses.

**Domains:** Presentation (unified data layer), Computation (delegates to CORE for state)

---

### TreeDisplayConfig (+ subclasses)

Configuration object controlling per-view behavior of the unified tree. Base class `TreeDisplayConfig` inherits `BaseDisplayConfig`.

| Subclass | Panel | Columns | File Actions |
|----------|-------|---------|-------------|
| LocalHostDisplayConfig | Left dock | Local Host, Mount, Mask, Reveal, Push | push, remove |
| ScopeDisplayConfig | Right dock | Container Scope, Push | push, remove, update, pull |

Controls: column definitions (ColumnDef), display filter booleans, file_actions set, state_styles dict.

**Domains:** Presentation (view configuration)

---

### ColumnDef

Dataclass defining a single tree column. Used by TreeDisplayConfig subclasses.

Key fields: `header`, `width`, `check_field`, `files_only`, `folders_only`, `symbol_type`, `enable_condition`, `cascade_clear`.

**Domains:** Presentation (column rendering, checkbox guards)

---

### Project Root Header

The `QHeaderView` band atop the `localHostTree` QTreeView in `LocalHostView`. Provides its own RMB context menu (`_show_header_context_menu`) distinct from the node-level RMB. Targets `host_project_root` only — the folder configured as the project root.

**Actions follow the six-gesture state machine** documented in `Mount Delivery Terms`. The header RMB offers the same gesture set as a tree-node RMB, scoped to `host_project_root`:

- No mount set on root → **Mount**, **Virtual Mount** (both apply to the entire project)
- Mount set on root → **Unmount**, **Convert to Virtual Mount**
- Virtual Mount set on root → **Remove Virtual Mount**, **Convert to Mount**, **Remove But Keep Children**, plus container-dependent actions when a container exists

The header never hides when a scope is loaded — gestures always include at least Mount/Virtual Mount when the root has no mount set. Menu is only fully empty when no scope is loaded.

**Contrast with tree node RMB:** Node RMB checks the same gate flags per selected node; header RMB always targets `host_project_root`. Multi-select (shift-click in the tree) does not apply to the header.

**Domains:** Presentation (LocalHostView header interaction)  
**See:** `Mount Delivery Terms § Six RMB gestures`, `local_host_view.py → _show_header_context_menu`, `GUI_LAYOUT_SPECS.md § Module Ownership Map`

---

## Historical Note

Prior to v2.0, the codebase used "shadow/light" terminology. Unified to "masked/revealed." All production APIs use unified terms. Documentation cleanup complete (CC-6).

| Old Term | New Term |
|----------|----------|
| shadow | masked |
| light | revealed |
| exception_file | pushed_files |

---

## Operation Result Types

### OpResult

Standardized return type for all CORE file and container operations. Replaces ad-hoc `(bool, str)` tuples with structured error/warning information.

**Module:** `core/op_result.py`

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether the operation completed successfully |
| `message` | str | Human-readable status message |
| `error` | OpError or None | Blocking error enum if operation failed precondition |
| `warnings` | list[OpWarning] | Confirmable warnings from preflight |
| `details` | list[str] | Additional detail lines (e.g., validation error list) |

**Domains:** Orchestration (all file ops + container lifecycle), Presentation (GUI dialog selection), CLI (output formatting)

---

### OpError

Enum of blocking errors. Operation cannot proceed regardless of `--force` or user confirmation.

**Module:** `core/op_result.py`

| Value | Context | Meaning |
|-------|---------|---------|
| `HOST_FILE_NOT_FOUND` | push | Nothing to push |
| `PARENT_NOT_MOUNTED` | push | Would create orphan (TTFF) |
| `INVALID_LOCATION` | push/pull | Path not under host_container_root |
| `CONTAINER_NOT_RUNNING` | push/pull/rm | Docker cp needs running container |
| `FILE_NOT_IN_CONTAINER` | pull | Nothing to pull |
| `CONTAINER_NOT_FOUND` | rm-container | Container doesn't exist |
| `DOCKER_NOT_RUNNING` | create | Daemon unavailable |
| `PROJECT_IN_INSTALL_DIR` | create | Safety guard |
| `VALIDATION_FAILED` | create | details[] has error list |
| `NO_PROJECT` | all | No host_project_root |
| `CONFIG_LOAD_FAILED` | all | Bad scope_docker.json |
| `NO_PUSHED_FILES` | push-batch | Nothing configured |
| `NO_MATCHING_FILES` | push-batch | Filter matched nothing |

**Domains:** Orchestration (preflight checks)

---

### OpWarning

Enum of confirmable warnings. GUI shows dialog, CLI requires `--force`.

**Module:** `core/op_result.py`

| Value | Context | Dialog |
|-------|---------|--------|
| `FILE_ALREADY_TRACKED` | push | "Already tracked. Overwrite in container?" |
| `FILE_IN_CONTAINER_UNTRACKED` | push | "Container has this file (not from host). Overwrite?" |
| `NOT_IN_MASKED_AREA` | push | "Not in masked area — push may have no effect. Continue?" |
| `LOCAL_FILE_EXISTS` | pull | "Overwrite local file?" |
| `DESTRUCTIVE_REMOVE` | rm-file | "Cannot be undone. Continue?" |
| `CONTAINER_DATA_LOSS` | rm/recreate | "All volumes and data lost. Continue?" |

**Domains:** Orchestration (preflight checks), Presentation (GUI WARNING_DIALOGS map)

---

### BatchFileResult

Categorized results from batch preflight. Allows callers to show complete error/warning summaries before any execution.

**Module:** `core/op_result.py`

| Field | Type | Description |
|-------|------|-------------|
| `errors` | dict[Path, OpResult] | Files that cannot proceed (blocking) |
| `warnings` | dict[Path, OpResult] | Files that need user confirmation |
| `clean` | list[Path] | Files ready to execute (no issues) |

**Batch flow:** `preflight_*_batch(paths)` -> show errors -> confirm warnings -> `execute_*_batch(clean + confirmed)`

**Domains:** Orchestration (batch file ops)

---

## Design Patterns

### preflight/execute

Two-phase pattern for all file and container operations. Separates validation from execution for clean error handling and batch support.

**Phase 1 — Preflight:** Validates all preconditions without side effects. Returns `OpResult` with:
- `error` (blocking) — operation cannot proceed
- `warnings` (confirmable) — user can approve to continue
- `success=True` with no error — ready to execute

**Phase 2 — Execute:** Performs the actual operation (docker cp, docker exec rm, compose up, etc.). Returns `OpResult` with success/failure.

**Consumer patterns:**

| Consumer | Errors | Warnings | Execute |
|----------|--------|----------|---------|
| GUI single | Error dialog, STOP | Confirm dialog per warning | `execute_*(force=True)` |
| GUI batch | Error summary dialog | Warning summary + single confirm | `execute_*_batch(force=True)` |
| CLI | Print + exit | Print + "Use --force" | `execute_*_batch(force=True)` |

**Modules:** `docker/container_ops.py` (file operations), `docker/container_lifecycle.py` (container operations)

**Domains:** Orchestration (Phase 7)
