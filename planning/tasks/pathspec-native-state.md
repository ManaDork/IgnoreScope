# Task: Pathspec-Native State Computation

**Feature:** `planning/features/pathspec-native-state/`
**Branch:** `refactor/pathspec-native-state`
**Status:** COMPLETE

## Goal

Replace tree-walk-based Stages 2+3 in `apply_node_states_from_scope()` with config-level queries. Eliminate GUI duplicate Stage 2 logic. Zero tree walks for state computation.

## Execution Plan

### Batch A — Foundation (1 commit)
Add config query methods + their unit tests.

| Task | File | Change |
|------|------|--------|
| 1 | `core/mount_spec_path.py` | Add `has_exception_descendant(path)` |
| 2 | `core/local_mount_config.py` | Add `has_pushed_descendant(path)` |
| 3 | `tests/` | Unit tests for `has_exception_descendant` |
| 4 | `tests/` | Unit tests for `has_pushed_descendant` |

**DRY checkpoint:** Compare against `_has_revealed_descendant` (export_structure.py), `has_revealed_descendant` (node_state.py), `find_paths_with_pushed_descendants` (node_state.py).

**Commit:** `[AI] Add config-level descendant query methods`

---

### Batch B — Core Refactor (1 commit)
Replace pipeline stages + exhaustive regression tests.

| Task | File | Change |
|------|------|--------|
| 5 | `core/node_state.py` | Replace Stage 2 `find_mirrored_paths()` with config queries in `apply_node_states_from_scope()` |
| 6 | `core/node_state.py` | Fix Stage 3 sequencing — `find_paths_with_direct_visible_children()` runs after virtual assignment |
| 8 | `tests/` | Exhaustive truth table regression tests (all 14 folder+file states) |

**DRY checkpoint:** Verify `find_mirrored_paths` behavior preserved. Verify `FOLDER_VIRTUAL_REVEALED` truth table hit. Cross-check against `FOLDER_STATE_TABLE` and `FILE_STATE_TABLE` in display_config.py.

**Commit:** `[AI] Refactor visibility pipeline to config-native queries`

---

### Batch C — Stage 1 Review (1 commit, may be empty)
Review `compute_node_state()` for consolidation with new pattern-native approach.

| Task | File | Change |
|------|------|--------|
| 7 | `core/node_state.py` | Review — may consolidate or leave as-is |

**Commit:** `[AI] Review Stage 1 for consolidation` (skip if no changes)

---

### Batch D — Dead Code Removal (1 commit)
Remove functions replaced by config queries.

| Task | File | Change |
|------|------|--------|
| 12 | `core/node_state.py` | Remove `find_mirrored_paths()`, `has_revealed_descendant()`, `find_paths_with_pushed_descendants()` |

**Commit:** `[AI] Remove tree-walk functions replaced by config queries`

---

### Batch E — GUI Duplicate Elimination (1 commit)

| Task | File | Change |
|------|------|--------|
| 9 | `gui/` | Audit callers of `compute_mirrored_intermediate_paths()` |
| 10 | `gui/mount_data_tree.py` | Remove independent Stage 2 from `_recompute_states()` |
| 11 | `gui/export_structure.py` | Replace `_has_revealed_descendant()` + `_get_effective_visibility()` with CORE state |

**Commit:** `[AI] Eliminate GUI duplicate Stage 2 visibility logic`

---

### Batch F — Architecture Doc Updates (1 commit)

| Task | File | Change |
|------|------|--------|
| 13 | `COREFLOWCHART.md` | Update Phase 3 pipeline, remove "GUI retains independent copy" |
| 14 | `ARCHITECTUREGLOSSARY.md` | Update visibility + NodeState implementation status |
| 15 | `MIRRORED_ALGORITHM.md` | Review for accuracy post-refactor |

**Commit:** `[AI] Update architecture docs for pathspec-native pipeline`

## Risks

1. GUI `_recompute_states()` may have callers depending on pre-computed mirrored intermediates — audit in Task 9
2. `hierarchy.compute_mirrored_intermediate_paths()` used by container_ops for mkdir — evaluate if compose consumers need it
3. Pattern scan O(paths × patterns) vs tree walk O(paths × depth) — acceptable for typical sizes

## Open Questions (resolve during implementation)

1. hierarchy.py consumers — keep function for container-path-specific work?
2. Stage 1 consolidation — absorb descendant queries inline?
3. GUI cleanup scope — how much simplification in `_recompute_states()`?
