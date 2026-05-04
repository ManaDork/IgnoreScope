# Technical Design: Config Panel Collapse/Expand Fix

## Overview

Replace the current `setMaximumHeight`-only collapse mechanism with a **min/max pin pattern** that eliminates sizing ambiguity. Add `setMinimumHeight` on the tree container to prevent 0px viewport death. Drop `setStretchFactor` calls in favor of explicit `setSizes()`.

## Architecture

**Pattern:** Min/Max Pin — set `minHeight == maxHeight` on collapse to create an immovable constraint the splitter cannot override. On expand, floor at header height, ceiling unconstrained.

**Key insight:** `setMaximumHeight` alone is a ceiling. The splitter can still allocate any amount between 0 and max. Setting `min == max` creates a single valid size — zero ambiguity.

## Dependencies

### Internal
- `IgnoreScope/gui/container_root_panel.py` — collapse/expand logic (primary)
- `IgnoreScope/gui/app.py` — splitter construction in `_setup_docks()` (secondary)

### External
- None

### Ordering
1. `app.py` changes first (splitter guards)
2. `container_root_panel.py` changes second (pin pattern)

## Key Changes

### Modified Files

#### `IgnoreScope/gui/app.py` — `_setup_docks()`

| Change | Lines | Description |
|--------|-------|-------------|
| Add `setChildrenCollapsible(False)` | after 265 | Prevent drag-to-zero on both children |
| Add `setMinimumHeight(80)` on `scope_container` | after 262 | Prevent tree from being crushed to 0px during expand |
| Remove `setStretchFactor(0, 3)` | 268 | Drop stretch factors — they fight `setSizes()` |
| Remove `setStretchFactor(1, 1)` | 269 | Drop stretch factors |
| Add initial `setSizes()` call | after splitter setup | Set explicit 75/25 default instead of stretch factors |

#### `IgnoreScope/gui/container_root_panel.py`

| Change | Method | Description |
|--------|--------|-------------|
| Rename to `_header_height()` | `_apply_collapsed_height` (extract) | Pure computation, no side effects |
| Rewrite `_apply_collapsed_height()` | lines 141-154 | Set BOTH `setMinimumHeight(h)` AND `setMaximumHeight(h)` — the pin |
| New `_apply_expanded_height()` | new method | Set `minHeight` to header height (floor), `maxHeight` to QWIDGETSIZE_MAX (unconstrained) |
| Rewrite `_toggle_config_viewer()` | lines 121-139 | Call `_apply_expanded_height()` + `_collapse_in_splitter()` on expand; call `_apply_collapsed_height()` on collapse |
| Rewrite `_expand_in_splitter()` | lines 156-168 | Use `setSizes([80, total-80])` instead of `[0, total]` — tree keeps minimum |
| New `_collapse_in_splitter()` | new method | Explicitly restore tree-dominant sizes: `setSizes([total-header_h, header_h])` |
| Keep `showEvent()` | lines 181-184 | Still calls `_apply_collapsed_height()` on first show |
| Remove `QSplitter` import | line 27 | No longer imported (was unused in current code, only used for type hint in `_find_parent_splitter`) |

### New Files
None

### Deleted Files
None

## Interfaces & Data

No new signals, properties, or data structures. All changes are internal to existing methods.

## Collapse/Expand State Machine

```
                    ┌──────────────┐
    construction ──►│  COLLAPSED   │◄──── LMB click (from expanded)
                    │  min==max==h │
                    │  content hidden│
                    └──────┬───────┘
                           │ LMB click
                           ▼
                    ┌──────────────┐
                    │  EXPANDED    │
                    │  min=h       │
                    │  max=HUGE    │
                    │  content visible│
                    │  tree=80px min│
                    └──────────────┘
```

## Alternatives Considered

| Approach | Verdict | Reason |
|----------|---------|--------|
| Drop splitter, use QVBoxLayout | Viable but rejected | User chose to keep splitter architecture |
| Nested QDockWidget | Over-engineered | Fragile nested QMainWindow, theme conflicts |
| QToolBox | Not viable | Wrong widget for single-panel collapse in splitter |
| QPropertyAnimation | Future polish | Does not fix core bugs, adds complexity |
| QSplitter.setCollapsible() | Supplementary only | Collapse = 0px (header vanishes), wrong semantic |

## Risks

| Risk | Mitigation |
|------|------------|
| `showEvent` fires before layout is complete, `fontMetrics` returns wrong height | Header height is font-based, font is set before first show. If wrong, the pin self-corrects on toggle. |
| Tree minimum of 80px may be too small/large for some screen sizes | 80px accommodates the header row + 1-2 tree items. Acceptable fixed value. |
| `setSizes()` rounding with integer pixel math | Use `int()` truncation. Off-by-1 pixel is invisible. |

## Architecture Doc Impact

| Document | Section | Change Needed |
|----------|---------|---------------|
| `GUI_STRUCTURE.md` | Section 2: Sizing Audit Table — Scope Dock | Update `configPanel` row: add min/max pin constraint. Update `scope_container` row: add minimumHeight 80px. |
| `GUI_STRUCTURE.md` | Section 5: Hardcoded Pixel Value Index | Add `80` (tree minimum) and update collapse height formula entry. Remove stretch factor entry (3:1 dropped). |
| `GUI_LAYOUT_SPECS.md` | Section 5: Scope Container Actions | Update collapse/expand behavior description to match pin pattern. |
