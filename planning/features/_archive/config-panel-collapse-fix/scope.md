# Scope: Config Panel Collapse/Expand Fix

## Phases

### Phase 1 — MVP (this feature)
Fix the three collapse/expand bugs using min/max pin pattern. No animation, no drag customization.

### Phase 2 — Polish (future)
Optional animated transitions via QPropertyAnimation. Separate task.

## Task Breakdown

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|------------|------------|----------------|
| 1 | Add splitter guards in `app.py` — `setChildrenCollapsible(False)`, `setMinimumHeight(80)` on tree container, drop `setStretchFactor` calls, add explicit initial `setSizes()` | — | Low | N/A |
| 2 | Extract `_header_height()` pure computation method from `_apply_collapsed_height()` | — | Low | Verify no duplicate height calc exists |
| 3 | Rewrite `_apply_collapsed_height()` to pin min==max | 2 | Low | N/A |
| 4 | Add `_apply_expanded_height()` method — floor at header, ceiling unconstrained | 2 | Low | Verify not duplicating collapse logic |
| 5 | Add `_collapse_in_splitter()` — explicit tree-dominant `setSizes()` call | — | Low | Inverse of `_expand_in_splitter`, verify no logic duplication |
| 6 | Rewrite `_expand_in_splitter()` — use `setSizes([80, rest])` instead of `[0, total]` | — | Low | N/A |
| 7 | Rewrite `_toggle_config_viewer()` to call new expand/collapse methods | 3, 4, 5, 6 | Low | N/A |
| 8 | Manual test: verify AC1–AC6 | 1–7 | Low | N/A |
| 9 | Update `GUI_STRUCTURE.md` sizing audit and pixel index | 1–7 | Low | N/A |
| 10 | Update `GUI_LAYOUT_SPECS.md` Section 5 panel behavior | 1–7 | Low | N/A |

**Total complexity:** Low — all tasks are small, focused edits to existing code. No new modules, no new widgets, no new signals.

## Estimated File Impact

| File | Type | Lines Changed (est.) |
|------|------|---------------------|
| `IgnoreScope/gui/app.py` | Modify | ~6 lines (splitter setup) |
| `IgnoreScope/gui/container_root_panel.py` | Modify | ~25 lines (methods rewrite) |
| `docs/architecture/GUI_STRUCTURE.md` | Modify | ~8 lines (sizing table updates) |
| `docs/architecture/GUI_LAYOUT_SPECS.md` | Modify | ~5 lines (behavior update) |
