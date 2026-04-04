# Scope — Pathspec-Native State Computation

## Phases

### Phase 1: MVP — Config Query Methods + Pipeline Refactor

Add new query methods, refactor the CORE pipeline, fix the Stage 3 bug. This phase delivers the primary goal (zero tree walks) without touching the GUI.

### Phase 2: GUI Duplicate Elimination

Audit and remove GUI's independent Stage 2 logic. Depends on Phase 1 being stable and tested.

### Phase 3: Architecture Doc Updates

Update blueprints to reflect the new pipeline structure.

## Task Breakdown

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|-----------|------------|----------------|
| 1 | Add `MountSpecPath.has_exception_descendant(path)` | — | Low | Check against `_has_revealed_descendant` in export_structure.py, `has_revealed_descendant` in node_state.py |
| 2 | Add `LocalMountConfig.has_pushed_descendant(path)` | — | Low | Check against `find_paths_with_pushed_descendants` in node_state.py |
| 3 | Unit tests for `has_exception_descendant` | 1 | Low | — |
| 4 | Unit tests for `has_pushed_descendant` | 2 | Low | — |
| 5 | Refactor `apply_node_states_from_scope()` — replace Stage 2 with config queries | 1, 2 | Medium | Verify `find_mirrored_paths` behavior preserved |
| 6 | Fix Stage 3 sequencing — `find_paths_with_direct_visible_children()` runs after virtual assignment | 5 | Low | Verify FOLDER_VIRTUAL_REVEALED truth table hit |
| 7 | Review Stage 1 `compute_node_state()` for consolidation | 5 | Medium | — |
| 8 | Regression tests — exhaustive truth table for all 14 states | 5, 6 | Medium | Cross-check against `FOLDER_STATE_TABLE` and `FILE_STATE_TABLE` in display_config.py |
| 9 | Audit GUI callers of `compute_mirrored_intermediate_paths()` | — | Low | — |
| 10 | Simplify `gui/mount_data_tree.py::_recompute_states()` — remove independent Stage 2 | 5, 9 | Medium | Verify no other GUI paths depend on pre-computed mirrored intermediates |
| 11 | Eliminate `gui/export_structure.py` duplicates — use CORE NodeState | 5 | Low | — |
| 12 | Remove dead code: `find_mirrored_paths()`, `has_revealed_descendant()`, `find_paths_with_pushed_descendants()` from node_state.py | 5, 8 | Low | Verify no remaining callers |
| 13 | Update `COREFLOWCHART.md` Phase 3 pipeline | 5, 6 | Low | — |
| 14 | Update `ARCHITECTUREGLOSSARY.md` visibility + NodeState sections | 5, 6 | Low | — |
| 15 | Review `MIRRORED_ALGORITHM.md` for accuracy | 5, 10 | Low | — |

### Phase Grouping

**Phase 1 (MVP):** Tasks 1-8, 12
**Phase 2 (GUI):** Tasks 9-11
**Phase 3 (Docs):** Tasks 13-15