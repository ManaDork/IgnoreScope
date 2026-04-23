# Core Data Flow Chart

> **Backend Reference** — canonical data flow for IgnoreScope core, docker, cli, utils, and container_ext packages.
> All code changes must respect this flow. If reality diverges, update the code, not this chart.
>
> GUI flow reference: `DATAFLOWCHART.md` (Phases 7-8 are shared cross-domain concepts; Phases 1-6 are domain-specific pipelines)
> State model: 14 states (7 folder + 7 file) + 2 overrides — see `GUI_STATE_STYLES.md` Section 3

---

## Primary Purpose

The tool's purpose is **selective file visibility** — controlling what a container can and cannot see.
Containers limited to control folder visibility.
Everything else (volumes, YAML, docker cp) exists to enforce that visibility.

---

## Domain Ownership

### UI OWNS (thin layer — display and interaction)

1. Location input for CORE container environment (scope_docker.json or default template)
2. `MountDataTree = GetHostNodes()` — receives node tree FROM CORE
3. `DisplayDataTree(displayConfig, MountDataTree)` — uses displayConfig to filter and apply displayed information from Node.States (mounted, masked, revealed, visible, hidden, pushed, orphaned); derives **cosmetic** from Node.states matrix for UX feedback cosmetic=(gradients, text colors, checkbox enable/disable)
4. Filters user actions based on: UI context && CORE validation && CORE node states
5. Sends commands to trigger actions in CORE
6. Refreshes and displays results

### CORE OWNS (authority — state, structure, operations)

1. `scope = Read(scope_docker.json)` — config path sets (mounts, masked, revealed, pushed_files)
2. `ApplyNodeStateFromScope(config, paths)` — computes NodeState per path from config sets
3. Validation (in hierarchy.py) — relationship checks (mask under mount, reveal under mask)
4. `Write(scope_docker.json)` — persist config
5. `ComposeDocker(ordered_volumes, *kwargs)` — YAML structure, masks, isolation volumes, Dockerfile
6. `File_Ops` — host-side file operations, ancestor queries, path lookups
7. `Container_Ops` — container-side operations (docker inspect/cp, lifecycle, push/pull/remove)
8. `Reconcile_Extensions` — post-start verify/re-deploy loop (config.extensions × binary presence → state matrix)

> **Note on filesystem scanning:** CORE does not scan the host filesystem or build a file tree.
> GUI lazy-loads tree nodes via `MountDataNode.load_children()` (single-level `Path.iterdir()`).
> CLI operates directly on config path sets — no tree needed. CORE accepts path sets as input.

### NodeState Authority

CORE defines NodeState **rules and computation** (visibility logic, orphan detection, validation).
GUI **instantiates** NodeState per node and **hosts** the runtime tree (`MountDataTree._states`).
See: DATAFLOWCHART.md Module Responsibility Map for GUI-side hosting.

---

## Config IS the State Definition

`scope_docker.json` mount_specs are evaluated via pathspec to produce per-node state flags:

| Config source | → | NodeState flag | Meaning |
|---|---|---|---|
| `local.mount_specs[].mount_root` | → | `mounted: bool` | Path under a bind mount root |
| `mount_specs[].patterns` (non-`!`) | pathspec eval → | `masked: bool` | Path matched by deny pattern |
| `mount_specs[].patterns` (`!` prefix) | pathspec eval → | `revealed: bool` | Path overridden by exception |
| `pushed_files[]` | → | `pushed: bool` | File was docker cp'd into container |
| *(derived at build)* | → | `orphaned: bool` | TTFF: pushed + masked + not mounted + not revealed |
| `mirrored` | → | `mirrored: bool` | Config toggle: enable Stage 2 descendant walk + mirrored mkdir (default: True) |
| *(derived at build)* | → | `visibility: str` | orphaned / revealed / virtual / masked / visible / hidden |

**Visibility is NodeState, not cosmetic.** CORE computes it; GUI reads it as data. GUI only adds cosmetic rendering on top.

**Stage 1 — CORE per-node** (MatrixState in core/node_state.py):
Raw boolean flags computed via ancestor walk (is_descendant checks), then combined:

| Visibility | Condition |
|---|---|
| `orphaned` | TTFF: pushed=T, masked=T, mounted=F, revealed=F |
| `revealed` | revealed=T |
| `masked` | masked=T, mounted=T |
| `visible` | mounted=T |
| `hidden` | (none of the above) |

**Stage 2 — config-native** (CORE, core/node_state.py):

| Visibility | Condition |
|---|---|
| `virtual` | Check 1: owning spec has exception descendant (pattern scan) OR Check 2: config has pushed descendant (pushed_files scan) OR Check 3: mount_root is descendant of path (above-mount structural) |

Dual computation: config queries (primary) + inverse pattern derivation (cross-reference with discrepancy logging).

*(Full state model: 14 states — see GUI_STATE_STYLES.md Section 3)*

---

## CORE Flow (Phases)

Phases 7-8 (User Action, Refresh) are shared cross-domain concepts. Phases 1-6 are domain-specific pipelines — see DATAFLOWCHART.md for GUI ordering.

```
PHASE 1: READ CONFIG
──────────────────────────────────────────────────────────────

    scope = Read(scope_docker.json)
        │
        ├── IF file exists:
        │       ScopeDockerConfig.from_dict(data, host_project_root)
        │       All paths resolved to absolute
        │
        ├── IF no file:
        │       Empty ScopeDockerConfig (default template)
        │
        └── Returns: ScopeDockerConfig
                       mount_specs (list of MountSpecPath — per-mount patterns)
                       pushed_files, container_root, siblings
                       local_host_root (ancestor reference — see DATAFLOWCHART Root Concepts)
                       Backward-compat @properties: mounts, masked, revealed (computed from mount_specs)


PHASE 2: BUILD HOST STRUCTURE
──────────────────────────────────────────────────────────────

    HostFileTree = CreateHostHierarchyStructure(scope.root)
        │
        ├── Scan host_project_root → raw file/folder nodes from OS
        │
        ├── FOR EACH sibling in scope.siblings:
        │       Scan sibling.host_path → append nodes
        │
        ├── Stencil nodes (auth volume, future LLM configs, detached mount roots)
        │       Appended as non-filesystem entries
        │
        └── Returns: HostFileTree — node tree
                     (no state yet — just filesystem structure + stencils)
                     In GUI context, this becomes MountDataNode tree before
                     state application.


PHASE 3: APPLY NODE STATE
──────────────────────────────────────────────────────────────

    ApplyNodeStateFromScope(HostFileTree, scope)
        │
        │   Applies ALL state from config to nodes:
        │
        ├── FOR EACH path:
        │       Find owning MountSpecPath (mount_spec whose root contains path)
        │       node.mounted = True if path under any mount_spec.mount_root
        │       node.masked = owning_spec.is_masked(path)   ← pathspec eval
        │       node.revealed = owning_spec.is_unmasked(path) ← pathspec eval
        ├── FOR EACH path in scope.pushed_files: node.pushed = True
        │
        ├── Orphan detection (MatrixState TTFF):
        │       IF node.pushed AND node.masked AND NOT node.mounted AND NOT node.revealed:
        │           node.orphaned = True
        │
        ├── Stage 1 visibility (MatrixState — per-node, no tree context):
        │       FOR EACH node:
        │           node.visibility = compute_visibility(node flags)
        │           → accessible / restricted / virtual
        │
        ├── Stage 2 visibility (config-native — no tree walks):
        │       IF config.mirrored:
        │           FOR EACH path with visibility == "restricted":
        │               Check 1: owning_spec.has_exception_descendant(path)
        │               Check 2: config.has_pushed_descendant(path)
        │               Check 3: any mount_root is descendant of path
        │               IF any check true → visibility = "virtual"
        │           Cross-reference: inverse pattern derivation with discrepancy logging
        │       CORE-owned in core/node_state.py. GUI uses CORE results only.
        │
        ├── Stage 3 descendant folder fields (config-native — no tree walks):
        │       has_pushed_descendant = config.has_pushed_descendant(path)
        │       has_direct_visible_child = parents of revealed/pushed nodes (single pass)
        │
        └── Returns: HostFileTree with all NodeState populated


PHASE 4: VALIDATION
──────────────────────────────────────────────────────────────

    Validate(HostFileTree)
        │
        ├── Relationship validation (hierarchy.py):
        │       masked must be under a mount → error if orphaned
        │       revealed must be under a mask → error if orphaned
        │
        ├── Host state validation:
        │       mount paths exist on disk
        │       masked paths exist on disk
        │       revealed paths exist on disk
        │
        └── Returns: list of errors (empty if valid)


PHASE 5: WRITE CONFIG
──────────────────────────────────────────────────────────────

    Write(scope_docker.json)
        │
        ├── ScopeDockerConfig.to_dict(project_root)
        │       Absolute paths → relative POSIX
        │       Siblings keep absolute host_path
        │
        └── JSON written to .{project}_igsc/.{container}/


PHASE 6: COMPOSE DOCKER
──────────────────────────────────────────────────────────────

    ComposeDocker(HostFileTree, *kwargs)
        │
        │   Reads node state from HostFileTree — does NOT recompute.
        │   Formats into Docker artifacts:
        │
        ├── docker-compose.yml
        │       Auth volume           (named, persists — LLM credentials)
        │       Volumes in pattern order per MountSpecPath:
        │         For each mount: bind mount root, then for each pattern:
        │           - non-negated pattern → named mask volume (starts empty, persists)
        │           - negated (!) pattern → bind mount punch-through
        │         Mask volumes accumulate pushed exception files at runtime via docker cp.
        │       Siblings              (repeat pattern-order structure per sibling)
        │       Isolation             (final named volumes for extensions)
        │       Compose metadata      (project name, service, working_dir)
        │
        └── Dockerfile
                Base image, WORKDIR, CMD
                Optional: LLM installation via deployer

    Exception dirs (mkdir -p for pushed files in masked areas) are
    computed by hierarchy.revealed_parents, consumed by container_ops
    during create — NOT a compose artifact.


PHASE 6a: PER-SPEC DELIVERY EMIT (create only)
──────────────────────────────────────────────────────────────

    Compose emission and container lifecycle branch per MountSpecPath
    based on `mount_spec.delivery`, NOT on a scope-level mode:

    delivery == "bind" ─── compose YAML emits the Layer 1 bind mount
                           + mask/reveal layers as described in Phase 6.
                           Lifecycle runs no init step for this spec —
                           content is live-linked from the host.

    delivery == "detached" ─ compose YAML emits NO Layer 1 for this
                             spec (and no L2/L3 project-content volumes
                             backing it). Lifecycle runs a per-spec
                             init (`_detached_init`) after `compose up`
                             that branches on `content_seed` and
                             `host_path`:

                             content_seed == "tree" (host_path set):
                               • Walk mount_root's content on the host
                                 (respecting mask/reveal patterns) and
                                 `docker cp` into the container.
                               • Masks (L2 patterns) within this spec
                                 → `docker exec rm -rf <masked_path>`
                                 post-cp.
                               • Reveals (L3 patterns) within this spec
                                 → included in the cp walk.
                               • Symlinks/junctions get a mkdir stub;
                                 contents are not traversed.

                             content_seed == "folder" (host-backed):
                               • `docker exec mkdir -p <container_path>`;
                                 no cp walk, no host read.
                               • Validator gate: patterns must be empty
                                 on folder-seed specs (folder-seed has
                                 no walk to mask/reveal over).
                               • `pushed_files` replay still applies.

                             content_seed == "folder" (host_path is None,
                             container-only):
                               • mount_root is interpreted as a
                                 container-logical path (no host-side
                                 translation via host_container_root).
                               • `docker exec mkdir -p <mount_root>`;
                                 no cp, no host read.
                               • Validator gate: container-only specs
                                 (host_path=None) require content_seed
                                 == "folder".

    delivery == "volume" ─── L_volume tier (stencil-named Docker volume).
                             hierarchy.py: `_compute_volume_tier_entries`
                             walks mount_specs in order; each
                             delivery="volume" spec yields
                             `vol_{owner_segment}_{sanitized_container_path}`
                             as volume name via `_derive_volume_name(
                             ms.owner, container_path)` (see glossary →
                             "volume layering order"). owner_segment is
                             "user" for user-authored specs and
                             sanitize_volume_name(extension_name) for
                             extension-synthesized specs (e.g.
                             "Claude Code" → "claude_code"). Cross-scope
                             uniqueness comes from docker compose
                             project namespacing (no explicit `name:` on
                             the declaration — matches the mask volume
                             pattern, not the auth volume pattern).

                             compose.py: per-spec `- "{name}:{container_path}"`
                             appears in services.volumes between L1-L3
                             and Layer 4 isolation blocks; `name:`
                             appears in the top-level `volumes:`
                             section without extra options (empty
                             declaration → Docker creates/reattaches
                             persistent local volume).

                             Validator gates: `delivery="volume"` ⇒
                             `content_seed="folder"`; no tree-seed cp
                             walk into a named volume at this phase.
                             host_path=None (container-only) is the
                             Phase 3 shape; host-backed volume-delivery
                             deferred.

                             Lifecycle: no Phase 6a cp is needed —
                             volume is empty on first create, content
                             filled via `pushed_files` or in-container
                             writes. Survives `docker compose down` +
                             `up` natively (Docker retains the volume
                             unless `-v` is passed). Update path emits
                             an identical compose file, so the volume
                             name matches across the down/up cycle and
                             content persists without staging.

    Layer 4 (isolation volumes for extensions — auth, Claude, Git)
    are emitted regardless of any mount_spec delivery. They are
    orthogonal to per-spec delivery choice.

    All deliveries share the `pushed_files` replay and extension
    reconciliation steps that follow. On container recreate, detached
    tree-seed content is ephemeral (writable layer) and must replay
    every time; folder-seed content is empty until pushed_files or
    in-container writes fill it; bind content re-attaches host state
    automatically; volume content survives recreate natively.

    UPDATE PATH — preserve_on_update hook
    ──────────────────────────────────────

    The update path (`execute_update`) adds two hooks around recreate
    for `delivery="detached" + content_seed="folder" + preserve_on_update=True`
    specs. These are the "soft permanent" tier — lighter than a named
    volume but persistent across ordinary updates.

    Phase 4b  `_preserve_detached_folders` — runs BEFORE `docker compose
                down`. For each spec with `preserve_on_update=True`:
                  • `docker exec test -e <cpath>`: missing path is
                    treated as first-ever update (empty snapshot placeholder).
                  • `docker cp cname:<cpath> <tmp_stage>/spec_{idx}` pulls
                    the live container contents to a host tmp staging dir
                    (tempfile.mkdtemp with prefix "ignorescope_preserve_").
                  • FAIL-SAFE: any cp-out failure aborts the update
                    BEFORE compose-down. The old container stays intact
                    and the caller receives an OpResult(success=False).
                    No mid-state is possible — either every preserve
                    snapshot is on disk or the update never started.

    Phase 8b  `_restore_detached_folders` — runs AFTER `_detached_init`
                has mkdir'd each folder-seed path. For each snapshot:
                  • `docker cp <stage>/spec_{idx}/. cname:<cpath>` merges
                    the preserved contents into the fresh (empty) folder
                    using the canonical `/.` "copy contents" pattern.
                  • NON-FATAL: cp-back failure is logged as a warning
                    note in OpResult.details and the outer update
                    continues. A failed restore leaves the folder empty
                    (mkdir stub intact) — user can re-push manually.
                    Rationale: at this point the container is already
                    recreated; aborting would waste work and leave the
                    user in an even worse state.

    Staging cleanup runs in a `finally` block wrapping Phase 5-12, so
    the temp dir is removed whether the update succeeds, aborts mid-way,
    or raises. Cleanup errors are swallowed — never mask a real op failure.

    Why only `detached + folder + preserve=True`? Tree-seed specs re-read
    from host on update (no need to preserve writable-layer deltas);
    `delivery="volume"` survives update natively via Docker's named
    volume retention. Validator rejects `preserve_on_update=True` on
    any other combination.

    See glossary → "Mount Delivery Terms" for vocabulary.


PHASE 7: USER ACTION (GUI → CORE)
──────────────────────────────────────────────────────────────

    User clicks checkbox / RMB action in GUI
        │
        ▼
    UI: Action Filter
        │
        ├── UI context check (which panel, which column)
        ├── CORE validation (is action allowed given node state?)
        ├── CORE node state (enable conditions from NodeState)
        │
        ▼
    CORE: Apply Change
        │
        ├── Toggle via MountSpecPath pattern operations:
        │       Mount removed → remove entire MountSpecPath (all patterns lost)
        │       Mask removed  → remove deny pattern + filter descendant patterns
        │       Reveal removed → remove exception pattern only
        │
        ├── OR execute file operation:
        │       Push  → docker cp host→container, pushed=True
        │       Pull  → docker cp container→host
        │       Remove → docker exec rm, pushed=False
        │
        ▼
    CORE: Write(scope_docker.json)


PHASE 8: REFRESH
──────────────────────────────────────────────────────────────

    After PHASE 7 completes, event triggers return to
    the appropriate phase for status update:

    State toggle (mount/mask/reveal checkbox):
        → Return to PHASE 3 (re-apply node state)
        → Then PHASE 4 (re-validate)
        → GUI refreshes from updated NodeState

    File operation (push/pull/remove):
        → Update pushed/orphaned flags in-place
        → GUI refreshes affected nodes

    Config reload (switch container, reopen project):
        → Return to PHASE 1 (full re-read)
```

---

## Orchestration Entry Points

```
CLI entry:       cmd_create()                  → Phases 1→2→3→4→5→6
GUI entry:       config_manager.open_project() → Phases 1→2→3→4→5
GUI lifecycle:   container_ops_ui → container_lifecycle → Phases 1→6
Both:            Phase 7→8 triggered by user actions
```

---

## CORE Module Map (Intended)

```
core/
  config.py              → PHASE 1, 5: Read/Write scope_docker.json
                            ScopeDockerConfig, SiblingMount
                            Path helpers (get_igsc_root, get_container_dir, etc.)
                            Container path formula: get_container_path(container_root, rel_path)
                              Formula: {container_root}/{rel_path} (rel_path relative to host_container_root)

  hierarchy.py           → PHASE 3, 4: ApplyNodeStateFromScope + Validation
                            NodeState rules and computation (mounted/masked/revealed/pushed/orphaned)
                            Visibility computation (visible/mirrored/hidden)
                            Relationship validation (orphan masks, orphan reveals)
                            Volume ordering (consumed by compose.py)
                            Exception parent dirs (consumed by container_ops)

  node_state.py          → PHASE 3: Per-node state model
                            NodeState dataclass (6 boolean flags + visibility)
                            MatrixState: compute_visibility(), compute_node_state()
                            Orphan detection: find_orphaned_paths()
                            Batch: apply_node_states_from_scope()

  op_result.py           → PHASE 7: Standardized operation result types
                            OpWarning (confirmable), OpError (blocking), OpResult, BatchFileResult
                            Used by docker/file_ops.py orchestrators, consumed by GUI/CLI

  mount_spec_path.py     → MountSpecPath dataclass: mount_root + patterns (gitignore)
                            Pattern CRUD, pathspec matching, validation

  local_mount_config.py  → Base model: mount_specs list, pushed_files, mirrored
                            Backward-compat @property shims (mounts, masked, revealed)
                            State query methods (is_mounted, is_masked, is_revealed)

  constants.py           → Container path constants


docker/
  compose.py             → PHASE 6: ComposeDocker
                            Formats node state into docker-compose.yml
                            Generates Dockerfile (with optional LLM)
                            Does NOT compute volumes — reads from hierarchy

  file_ops.py            → PHASE 7: File_Ops (orchestrator + host-side)
                            Path resolution: resolve_container_path (Rule 5 consumer)
                            Preflight validation: preflight_push/pull/remove
                            Execution: execute_push/pull/remove
                            Batch wrappers: preflight_*_batch, execute_*_batch
                            Host-side helpers: resolve_file_subset, resolve_pull_output

  file_filter_ops.py     → PHASE 7: File content filter hooks (placeholder)
                            FileFilter type alias, passthrough() no-op
                            execute_push accepts optional file_filter parameter

  container_lifecycle.py → Container lifecycle orchestrators
                            preflight_create / execute_create (6-phase: preflight→hierarchy→compose→build→deploy→reconcile→save)
                            preflight_update / execute_update (14-phase: load old→preflight→hierarchy→orphan detect→preserve→down→compose→build→up→detached init→restore→prune→dirs→reconcile→save)
                            preflight_remove_container / execute_remove_container
                            reconcile_extensions — post-start verify/re-deploy loop (state × presence matrix)
                            _collect_isolation_paths — extracts extension isolation paths for Layer 4 volumes (vestigial post Task 1.3; lifecycle callers now pass extensions= directly into compute_container_hierarchy; helper retires in Task 1.5)
                            _preserve_detached_folders / _restore_detached_folders — preserve_on_update hook pair
                            Shared by GUI and CLI — neither owns orchestration

  container_ops.py       → PHASE 7, 8: Container_Ops (subprocess layer)
                            Container-side operations:
                            Container state checks (docker inspect, docker ps)
                            Lifecycle (build, create, start, stop, remove)
                            Container file operations (push/pull/remove via docker cp)
                            Exception dir creation (mkdir -p, from hierarchy.revealed_parents)

  names.py               → Docker naming (DockerNames, sanitize_volume_name)


cli/
  interactive.py         → CLI-specific user interaction (prompts, wrappers)

  commands.py            → CLI command handlers (thin wrappers)
                            cmd_create, cmd_push, cmd_pull, cmd_remove
                            Delegates to docker/file_ops.py and docker/container_lifecycle.py


utils/
  paths.py               → Path conversion (to_relative_posix, is_descendant, etc.)
  subprocess_helpers.py  → Cross-platform subprocess kwargs
  validation.py          → Host state validation (paths exist, container ready)


container_ext/
  install_extension.py   → ExtensionInstaller ABC, DeployMethod, DeployResult
  claude_extension.py    → ClaudeInstaller (install, verify, entrypoint)
  git_extension.py       → GitInstaller (install, verify)
```

---

## Claude CLI Installation (Runtime Install)

The production pipeline for installing the Claude Code CLI into a running container.
The CLI connects to Anthropic's cloud API — no local model is installed.

```
GUI: "Install Claude CLI" menu action (Extensions > Claude menu)
  └─ container_ops.py :: deploy_llm_to_container()
       └─ DeployWorker(QThread)
            └─ ClaudeInstaller.deploy_runtime(method=FULL)
                 ├─ exec_in_container: apt-get install curl ca-certificates
                 ├─ exec_in_container: curl -fsSL https://claude.ai/install.sh | bash
                 └─ verify: test -x /root/.local/bin/claude → claude --version
```

**Requirements:** Running container, internet access in container.
**Result:** Claude CLI binary at `/root/.local/bin/claude` (ephemeral — lives in container writable layer, lost on container removal).
**Auth persistence:** Named volume at `/root/.claude` survives container rebuilds.

### Pipeline Status

| Pipeline | Entry Point | Status |
|----------|-------------|--------|
| Runtime Install (Claude) | `container_ops_ui.deploy_llm_to_container()` → `ClaudeInstaller.deploy_runtime(FULL)` | **ACTIVE** |
| Runtime Install (Git) | `container_ops_ui.deploy_git_to_container()` → `GitInstaller.deploy_runtime(FULL)` | **ACTIVE** |
| Image Bake | *(removed)* | Shelved code deleted in house-cleaning refactor |

### Extending for Other Extension Installers

The `ExtensionInstaller` abstract base class (`container_ext/install_extension.py`) is designed for extension. `ClaudeInstaller` and `GitInstaller` are existing implementations:

1. Subclass `ExtensionInstaller` in `IgnoreScope/container_ext/`
2. Implement: `name`, `binary_name`, `supported_methods`, `get_install_commands()`,
   `get_version_command()`, `parse_version_output()`
3. Export from `IgnoreScope/container_ext/__init__.py`
4. Add menu item + handler in `gui/menus.py` and `gui/container_ops_ui.py`

---

## Rules

1. **Visibility is NodeState** — `orphaned`/`revealed`/`virtual`/`masked`/`visible`/`hidden` is computed by CORE, stored per node. Stage 1 (6 values) computed per-node via MatrixState. Stage 2 adds `virtual` via config-native queries (CORE: core/node_state.py). Stage 3 adds folder descendant flags via config queries. GUI reads visibility as data; GUI only derives cosmetic rendering (gradients, colors) on top.
2. **Config IS the state** — scope_docker.json fields map 1:1 to NodeState flags. No separate state tracking.
3. **One derivation** — PHASE 3 applies all node state once. No consumer re-derives from raw config.
4. **Consumers format, never derive** — compose.py formats node state into YAML. container_ops passes derived paths to docker cp. GUI renders derived state into visuals.
5. **Container path formula exists once** — `get_container_path(container_root, rel_path)` in core/config.py. Formula: `{container_root}/{rel_path}` where rel_path is relative to `host_container_root`. container_root default: `/{host_container_root.name}`.
6. **Container state inspection exists once** — container_ops.py owns all docker inspect / docker ps. container_exists() uses docker inspect (structured JSON). docker ps is for listing, not existence checks.
7. **Validation is layered** — PHASE 4 validates relationships. utils/validation.py validates host state. Different concerns, different passes.
8. **Phase 7 → Phase 8** — every user action flows through CORE, triggers a refresh to the appropriate earlier phase.
9. **Import from package API** — GUI and CLI modules import docker functions from docker/__init__.py (package public API), not from internal modules directly. Internal module structure may change; __init__.py exports are stable.
