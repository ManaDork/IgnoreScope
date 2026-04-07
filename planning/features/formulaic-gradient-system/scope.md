# Scope — Formulaic Gradient System

## Phases

### Phase 1: Remove MOUNTED_MASKED + Add FOLDER_MOUNTED

Cleanup artifacts from the invalid MOUNTED_MASKED state. Add FOLDER_MOUNTED as a distinct visible state for mount roots (config.mount accent).

### Phase 2: Formulaic derive_gradient()

Replace hand-built folder state defs with derive_gradient(). Unify ancestor tracking. Generate folder state_styles from formula.

### Phase 3: Architecture Docs

Update ARCHITECTUREGLOSSARY, GUI_STATE_STYLES, COREFLOWCHART.

## Task Breakdown

| # | Task | Phase | Depends On | Complexity |
|---|------|-------|-----------|------------|
| 1 | Remove `mount_root_masked` from MountSpecPath (field + to_dict/from_dict) | 1 | — | Low |
| 2 | Remove `has_mount_masks` from NodeState + compute_node_state() | 1 | — | Low |
| 3 | Remove header RMB Mask/Unmask from local_host_view.py | 1 | — | Low |
| 4 | Remove `toggle_mount_root_masked()` from mount_data_tree.py | 1 | — | Low |
| 5 | Remove FOLDER_MOUNTED_MASKED from display_config state defs + truth table | 1 | 1-4 | Low |
| 6 | Add FOLDER_MOUNTED to truth table (is_mount_root=T, vis=visible) | 1 | 5 | Low |
| 7 | Add FOLDER_MOUNTED_REVEALED to truth table | 1 | 6 | Low |
| 8 | Update tests for Phase 1 changes | 1 | 5-7 | Medium |
| 9 | Implement `derive_gradient()` function | 2 | 6 | Medium |
| 10 | Unify ancestor.pushed + ancestor.revealed → ancestor.visible in JSON | 2 | 9 | Low |
| 11 | Replace `_FOLDER_STATE_DEFS` with formula-generated styles | 2 | 9 | Medium |
| 12 | Replace `FOLDER_STATE_TABLE` + folder path in `resolve_tree_state()` | 2 | 9, 11 | Medium |
| 13 | Verify all 12 folder states via derivation table test | 2 | 12 | Medium |
| 14 | Update ARCHITECTUREGLOSSARY.md | 3 | 12 | Low |
| 15 | Update GUI_STATE_STYLES.md with formula documentation | 3 | 12 | Low |
| 16 | Update COREFLOWCHART.md | 3 | 12 | Low |

## Batch Grouping (execution order)

**Batch A (Phase 1):** Tasks 1-8 — Remove MOUNTED_MASKED, add MOUNTED + MOUNTED_REVEALED
**Batch B (Phase 2):** Tasks 9-13 — Formulaic system
**Batch C (Phase 3):** Tasks 14-16 — Docs

## Deferred

- File state formulaic derivation
- Dynamic state name generation (debugging utility)
- File font color differentiation
- Container Scope panel override system
