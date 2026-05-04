# Unify L4 — Task 1.5: Delete `_collect_isolation_paths`

**Feature:** `unify-l4-reclaim-isolation-term`
**Phase:** 1 — Structural Unification (L4 Retirement)
**Task:** 1.5
**Branch:** `feature/unify-l4-task-1-5-delete-collect-isolation` (off `staging-v0.5`)
**Depends on:** 1.3 (unified hierarchy synth pipeline; all four lifecycle callers already pass `extensions=cfg.extensions or None`)
**Blocks:** 1.8 (orphan-diff `(old_iso - new_iso)` clause removal)

---

## Scope

Two removals and three doc cleanups:

1. **Delete the helper** `_collect_isolation_paths` (`container_lifecycle.py:401-417`). All four call sites in `execute_create` / `execute_update` / `preflight_create` / `execute_update` (old_hierarchy) have routed through `extensions=cfg.extensions or None` since Task 1.3; the helper is orphaned.
2. **Delete its test class** `TestCollectIsolationPaths` in `tests/test_docker/test_container_lifecycle.py:281-368`. Coverage for the extension → volume-spec translation is now owned by `ExtensionConfig.synthesize_mount_specs()` tests (Task 1.2) and `TestIsolationVolumes` in `test_hierarchy.py` (Task 1.3/1.4).
3. **Doc cleanup:** strike the retire-in-Task-1.5 breadcrumbs from `ExtensionConfig.synthesize_mount_specs` docstring, `COREFLOWCHART.md` lifecycle annotation, and `ARCHITECTUREGLOSSARY.md` STENCIL / Isolation (Layer 4) entries. Glossary wording at line 521 currently conflates the helper's retirement target (1.5) with the orphan-diff clause's target (1.8); corrected as part of this task.

The `(old_iso_names - new_iso_names)` orphan-diff clause in `execute_update` is NOT touched — it survives as a no-op pending Task 1.8.

---

## Acceptance Criteria

- [x] `IgnoreScope/docker/container_lifecycle.py`: `_collect_isolation_paths` function definition (lines 401-417) deleted.
- [x] `IgnoreScope/docker/container_lifecycle.py`: no remaining call sites to `_collect_isolation_paths` (verified via grep); all four `compute_container_hierarchy` invocations continue to pass `extensions=config.extensions or None` unchanged from Task 1.3.
- [x] `IgnoreScope/tests/test_docker/test_container_lifecycle.py`: `TestCollectIsolationPaths` class deleted; separator comment block trimmed.
- [x] `IgnoreScope/core/local_mount_config.py`: `ExtensionConfig.synthesize_mount_specs` docstring no longer references the retired `_collect_isolation_paths` helper (line 536 wording updated to reflect post-1.5 state).
- [x] `docs/architecture/COREFLOWCHART.md`: `container_lifecycle.py` module block (line 501) drops the `_collect_isolation_paths` bullet.
- [x] `docs/architecture/ARCHITECTUREGLOSSARY.md`: STENCIL Identifiers `synthesize_mount_specs` bullet (line 172) updated to drop the "retires in Task 1.5" qualifier; Isolation (Layer 4) entry (line 521) updated to reflect helper now deleted and separate the helper's retirement from the orphan-diff clause's retirement (Task 1.8).
- [x] `pytest IgnoreScope/tests`: non-docker-live tree green; only the 2 pre-existing `test_integration.py` baseline failures remain (Task 1.12 scope).
- [x] `grep -r _collect_isolation_paths` from project root returns zero matches.

---

## Out of Scope (explicitly deferred)

- Orphan-diff `(old_iso_names - new_iso_names)` clause removal — Task 1.8.
- `compose.py generate_compose_with_masks` signature collapse — Task 1.6.
- `_rebuild_l4_stencil_nodes` deletion — Task 1.9.
- Hard-coded `{name}-claude-auth` special case removal — Task 1.7.
- Pre-existing `test_integration.py` failures — Task 1.12.

---

## Files Touched

| File | Change |
|------|--------|
| `IgnoreScope/docker/container_lifecycle.py` | Delete `_collect_isolation_paths` |
| `IgnoreScope/tests/test_docker/test_container_lifecycle.py` | Delete `TestCollectIsolationPaths` class |
| `IgnoreScope/core/local_mount_config.py` | Drop retired-helper reference from `synthesize_mount_specs` docstring |
| `docs/architecture/COREFLOWCHART.md` | Drop `_collect_isolation_paths` annotation from lifecycle module block |
| `docs/architecture/ARCHITECTUREGLOSSARY.md` | Drop "retires in Task 1.5" qualifier; split helper vs orphan-clause retirement narrative |

---

## Notes

**No callers, no hazard.** Task 1.3 rewired all four `compute_container_hierarchy` callsites to pass `extensions=cfg.extensions or None`. The helper has been dead code across two prior PRs (#32 — Task 1.3; #33 — Task 1.4). This is a pure-deletion task.

**Test deletion vs migration.** `TestCollectIsolationPaths` tests the deleted helper, not a behavior. The equivalent behavior (extension → volume-spec translation) is already covered by `ExtensionConfig.synthesize_mount_specs()` tests landed in Task 1.2 and by `TestIsolationVolumes` in `test_hierarchy.py` (Task 1.3 migration + Task 1.4 naming assertions). No new test added; coverage is not reduced.

**Glossary correction.** Line 521 currently reads "_collect_isolation_paths helper and the (old_iso - new_iso) orphan-diff clause remain as vestigial no-ops pending formal removal in Task 1.8" — this bundles two retirements into Task 1.8 when scope.md assigns the helper to 1.5 and the clause to 1.8. The wording is corrected here as part of the helper's actual retirement.
