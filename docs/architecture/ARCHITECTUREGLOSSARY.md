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
  1. Bind mount (mount_root)                    — base visibility
  2. For each pattern in order:
     - Non-negated (e.g., "vendor/")            — named mask volume (hides)
     - Negated (e.g., "!vendor/public/")        — bind mount punch-through (reveals)
     - Non-negated (e.g., "vendor/public/tmp/") — named mask volume (re-hides)
  ...
For each Sibling (same pattern-order structure)
Final: Isolation volumes                         — persistent, container-owned
```

Pattern order = volume declaration order = correct nested layering. A reveal after a mask re-exposes content; a mask after a reveal re-hides a subfolder within it.

**Isolation:** Named volumes backing extension install paths (e.g., `/root/.local` for Claude). Declared via `ExtensionConfig.isolation_paths`. Volume naming: `iso_{sanitized_ext_name}_{sanitized_path}`. Nothing punches through isolation — it is the final overlay.

**Domains:** Computation (core/hierarchy.py computes ordering), Generation (docker/compose.py formats into YAML)

---

### MountSpecPath

Dataclass representing a single bind mount root with an ordered list of gitignore-style patterns controlling which subdirectories are masked (hidden) or unmasked (revealed) within that mount.

**Module:** `core/mount_spec_path.py`
**Fields:**
- `mount_root: Path` — absolute path to the bind mount root on the host
- `patterns: list[str]` — ordered gitignore-style patterns, relative to mount_root

**Pattern syntax (gitignore native):**
- `"vendor/"` — mask (deny) the vendor directory (named Docker volume)
- `"!vendor/public/"` — unmask (exception) vendor/public (bind mount punch-through)
- `"vendor/public/tmp/"` — re-mask vendor/public/tmp (named Docker volume)

**Evaluation:** Uses `pathspec` library with `gitignore` mode. Last matching pattern wins.
**Methods:** `add_pattern()`, `remove_pattern()`, `move_pattern()`, `is_masked(path)`, `is_unmasked(path)`, `get_masked_paths()`, `get_revealed_paths()`, `validate()`, `validate_no_overlap(specs)`

**Mount overlap rule:** No mount root can be a descendant of another mount root. Hard block validated by `validate_no_overlap()`.

**JSON format:**
```json
"mount_specs": [
  {"mount_root": "src", "patterns": ["vendor/", "!vendor/public/"]}
]
```

**Domains:** Config (mount_spec_path.py), Computation (node_state.py pathspec eval, hierarchy.py volume generation), Presentation (future rule list panel)

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
| `is_virtual` | bool | True for virtual entries (not filesystem-backed) |
| `source` | NodeSource | PROJECT, SIBLING, or VIRTUAL |
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

**Modules:** `docker/file_ops.py` (file operations), `docker/container_lifecycle.py` (container operations)

**Domains:** Orchestration (Phase 7)
