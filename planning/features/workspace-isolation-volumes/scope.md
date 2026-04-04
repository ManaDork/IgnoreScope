# Scope: Workspace Isolation Volumes

## Phases

### Phase 1: Config Schema + Extension Tracking ✓
Extend config to track extensions as LocalMountConfig entries with state lifecycle.
- [x] Add `state` field to `LocalMountConfig`
- [x] Create `ExtensionConfig` dataclass (extends LocalMountConfig)
- [x] Add `extensions: list[ExtensionConfig]` to `ScopeDockerConfig`
- [x] JSON serialization round-trip for extensions
- [x] Each installer declares its isolation paths
- [x] On successful deploy, write extension entry to config with state='installed'
- **Estimated complexity:** M
- **DRY checkpoint:** State update in ONE place (caller of deploy_runtime, not per-installer) ✓

### Phase 2: Layer 4 Compose Generation ✓
Generate isolation volumes in docker-compose.yml as Layer 4 (final overlay).
- [x] `compute_container_hierarchy()` adds isolation entries after Layer 3
- [x] Isolation volume naming: `iso_{extension_name}_{sanitized_path}`
- [x] `generate_compose_with_masks()` declares isolation volumes in volumes section
- [x] Orphan detection includes isolation volumes in `execute_update()`
- **Estimated complexity:** M
- **DRY checkpoint:** Parallel pattern to mask volumes, guard consistency enforced ✓

### Phase 3: Lifecycle Reconciliation
Reconcile extension state after container start via verify + deploy loop.
- [x] On container start: scan extension binary paths (`verify()` per extension)
- [x] Compare scan results against config state
- [x] state='deploy' + missing → run `deploy_runtime()`
- [x] state='installed' + missing → re-deploy (recreate recovery)
- [x] state='installed' + present → no-op
- [x] After successful deploy: update state → 'installed' (caller saves config)
- [x] Wire into `execute_create()` and `execute_update()` post-start
- [x] `get_installer()` factory resolves installer_class string → instance
- [x] Non-fatal: individual extension failure doesn't block others
- [x] 11 unit tests covering full state × presence matrix
- **Estimated complexity:** L
- **DRY checkpoint:** Reconciliation is generic loop over extensions list, not per-extension code ✓

### Phase 4: GUI [Isolate] Column
Add isolation control to Local Host Configuration tree.
- [ ] [Isolate] column in `LocalHostDisplayConfig` (folders only, checkable)
- [ ] `NodeState` integration for isolated paths
- [ ] User can add custom isolation paths (beyond extension-declared ones)
- [ ] Seed method choice per path: clone from host / start empty
- [ ] Persist choices in config
- **Estimated complexity:** M

### Phase 5: Remove/Uninstall UX
GUI for removing installed extensions.
- [ ] RMB action on extension in Scope Config: "Remove Extension"
- [ ] Sets state='remove' in config
- [ ] Reconciliation detects state='remove' + present → runs uninstall
- [ ] After uninstall: remove config entry, remove isolation volume
- **Estimated complexity:** M

## Task Breakdown

| # | Task | Depends On | Complexity | Phase |
|---|------|-----------|------------|-------|
| 1 | Add `state` field to `LocalMountConfig` | — | S | 1 |
| 2 | Create `ExtensionConfig` dataclass | Task 1 | S | 1 |
| 3 | Add `extensions` list to `ScopeDockerConfig` + serialization | Task 2 | M | 1 |
| 4 | Each installer declares `isolation_paths` | Task 2 | S | 1 |
| 5 | Write extension entry on deploy success | Tasks 3-4 | S | 1 |
| 6 | DRY audit: state update location | Task 5 | S | 1 |
| 7 | Layer 4 volume computation in hierarchy | Task 4 | M | 2 |
| 8 | Compose generation for isolation volumes | Task 7 | M | 2 |
| 9 | DRY audit: unify named volume generation | Task 8 | M | 2 |
| 10 | Scan extension binary paths on container start | Task 5 | M | 3 |
| 11 | Reconciliation loop (desired vs actual) | Task 10 | L | 3 |
| 12 | Wire reconciliation to Live View scan | Task 11 | M | 3 |
| 13 | [Isolate] column in Local Host tree | Task 7 | M | 4 |
| 14 | Seed method choice UX | Task 13 | M | 4 |
| 15 | Remove extension RMB action | Task 11 | M | 5 |

## Testing Strategy

- **Unit:** ExtensionConfig serialization round-trip
- **Unit:** Layer 4 volume computation (ordering after L1/L2/L3)
- **Unit:** Reconciliation state matrix (all 6 combinations of state x presence)
- **Unit:** DRY — state update called once per deploy, not per-installer
- **Integration:** Install extension → update container → verify binary persists
- **Integration:** Recreate container → verify auto-re-deploy via reconciliation
- **Manual:** GUI [Isolate] column renders, checkbox toggles persist to config

## Deferred Items

| Item | Phase | Notes |
|------|-------|-------|
| Remove/uninstall UX | 5 | state='remove' tracked, GUI deferred |
| Custom isolation paths (non-extension) | 4 | [Isolate] column covers this |
| Apt-get system path isolation | Future | Git's `/usr/bin/` needs special handling — may need clone-from-image |
