# Feature Spec: Config Panel Collapse/Expand Fix

## Problem Statement

The `ContainerRootPanel` collapse/expand cycle in the Scope Configuration dock has three interacting bugs that make the panel unusable after the first expand/collapse cycle:

1. **Initial open — panel invisible**: `setMaximumHeight` is a ceiling, not a floor. The splitter may allocate less than header height on first layout, so the header doesn't appear.
2. **Collapse after expand — broken split**: Only `setMaximumHeight` is set on collapse. Splitter sizes from the expand call (`[0, total]`) are never restored, producing an unpredictable ~75/25 empty-space split.
3. **Tree viewport death**: During expand, the tree (`scope_container`) is crushed to 0px via `setSizes([0, total])`. Qt's QTreeView viewport stops processing paint events at 0 height and does not recover when space is restored.

**Root cause (single sentence):** `setMaximumHeight` alone is necessary but not sufficient — the splitter can still allocate ambiguous sizes to a widget that lacks a matching `setMinimumHeight` floor.

## Success Criteria

- Panel header is visible on initial open (collapsed state)
- Expand shows config panel content with tree shrunk to minimum (~80px)
- Collapse restores tree to full space, panel pinned to header-only
- Expand/collapse cycle is repeatable indefinitely with no rendering artifacts
- Tree viewport renders correctly through all state transitions

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC1 | Panel header visible on app launch (no project loaded) | Visual — header text and arrow visible |
| AC2 | Panel header visible after project open (collapsed default) | Visual — header text reads "▶ Desktop Docker Scope Config" |
| AC3 | Click expand → panel dominates, tree shrinks to ~80px minimum | Visual — tree header row visible, panel fills remaining space |
| AC4 | Click collapse → panel pins to header-only, tree reclaims full space | Visual — tree renders all visible rows, no empty space |
| AC5 | Repeat AC3→AC4 five times with no degradation | Visual — tree renders correctly every cycle |
| AC6 | Splitter handle cannot drag tree or panel to 0px | Drag test — both widgets maintain minimum heights |

## User Stories

- As a user, I want the config panel header always visible so I know the panel exists and can expand it.
- As a user, I want the tree view to remain functional after collapsing the config panel so I can continue navigating the scope tree.

## Out of Scope

- Animated collapse/expand transitions (future phase)
- User drag-to-resize proportions (fixed ratios are acceptable)
- Splitter state persistence across sessions
- Changes to the `_GripSplitter` / `_GripHandle` visual design
- Pattern widget or JSON viewer content behavior

## Open Questions

None — all design decisions resolved during discovery.

## Related Bug Report

`_workbench/_bugs/config-panel-collapse-expand-cycle.md`
