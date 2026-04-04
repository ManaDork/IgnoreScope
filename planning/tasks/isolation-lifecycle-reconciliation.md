# Task: Workspace Isolation Volumes — Phase 3: Lifecycle Reconciliation

## Summary
On container start, scan extension binary paths to detect discrepancies between desired state (config) and actual state (container). Auto-re-deploy extensions after Recreate Container; no-op after Update Container (volumes survive).

## Parent Feature
`planning/features/workspace-isolation-volumes/` — Phase 3 of 5.

## Acceptance Criteria
- [x] `reconcile_extensions()` function scans each tracked extension's binary
- [x] state='deploy' + binary missing → run `deploy_runtime()` → state='installed'
- [x] state='installed' + binary missing → re-deploy (recreate recovery)
- [x] state='installed' + binary present → no-op
- [x] state='remove' + binary present → no-op (removal deferred to Phase 5)
- [x] Reconciliation is a generic loop over `config.extensions`, not per-extension code
- [x] Config mutated in-place, caller saves (DRY: no double-save)
- [x] Non-fatal: individual extension failure doesn't block others
- [x] CLI integration: automatic via `execute_create()` / `execute_update()`
- [x] GUI integration: automatic via `execute_create()` / `execute_update()`
- [x] Unit tests for all state × presence combinations (11 tests)
- [x] `get_installer()` factory in `container_ext/__init__.py`

## Approach
1. Add `reconcile_extensions()` to `container_lifecycle.py` — takes config + container_name, iterates extensions, calls `verify()` on each, deploys if needed, updates state
2. Wire into existing post-start touchpoints in CLI and GUI
3. State matrix is the core logic — 6 combinations of (deploy/installed/remove) × (present/missing)

## DRY Checkpoint
- Reconciliation loop is generic — no per-extension branching
- Uses existing `ExtensionInstaller.verify()` and `deploy_runtime()` — no new install logic
- State update via existing `config.track_extension()` — no new persistence code
