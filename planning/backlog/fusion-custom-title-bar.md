# Fusion Custom Title Bar

## Summary
Replace standard Windows title bar chrome with Fusion-styled custom window controls. Reference art direction shows a dark gradient title bar (blue -> purple -> light blue) instead of default Windows minimize/maximize/close buttons.

## Approach Options
1. **Frameless window + custom title bar widget**: Full control. Requires drag-to-move, min/max/close buttons, window snapping.
2. **QPalette override on Fusion style**: Limited — Windows 11 draws title bar via OS, not Qt.

## Reference Colors
- Title bar gradient left (marker 4): ~#181535 (deep indigo)
- Title bar gradient right (marker 5): ~#4070C0 (light blue)
- Estimated midpoint: ~#3030A0 (purple)

## Dependencies
- Fusion style already set in `IgnoreScope/gui/__init__.py`
- Would need custom QWidget title bar with painted gradient background

## Source
Art direction reference, glassmorphism palette shift task (2026-04-07).

---

## Cross-Feature Integration Opportunities (2026-04-08 analysis)

### Gradient Continuity
The Windows title bar is the ONE element the `GradientBackgroundMixin` system cannot reach. Going frameless lets `main_window` gradient flow from pixel 0 through the entire window. A `title_bar` gradient entry in `glassmorphism_v1_theme.json` uses the existing `WidgetGradientDef` pipeline with zero engine changes — just a new mixin subclass following the `_GradientDockWidget` / `_GradientStatusBar` pattern.

### Menu Bar Merge
Currently `QMenuBar` is a separate widget below the OS title bar, styled via QSS with flat `panel_bg`. A custom title bar can embed the menu bar inside it (VS Code / Chrome pattern), saving ~30px vertical space. Menu bar gradient inherits from title bar gradient.

### Reusable GradientHeaderBar Widget
The codebase has three different "header bar" implementations today:

| Header | Implementation | Gradient | Click Behavior |
|--------|---------------|----------|----------------|
| Windows title bar | OS-drawn | None | OS drag/buttons |
| Dock title bars (`QDockWidget::title`) | QSS flat color | No | Qt close/float buttons |
| Config panel header (`configHeaderFrame`) | QFrame + QLabel + eventFilter | Parent mixin only | Manual toggle |

A shared `GradientHeaderBar` widget could unify all three with:
- Fixed known height (constant, not font-metrics calculation)
- Gradient background via `GradientBackgroundMixin` (theme-driven)
- Label text + optional action buttons
- Click signal emission (no event filter)

**Config panel impact:** The `configHeaderFrame` QFrame + QHBoxLayout + QLabel + eventFilter + font metrics height calculation reduces to `GradientHeaderBar(text, gradient_name)` with a constant `HEADER_HEIGHT`. The min/max pin pattern from config-panel-collapse-fix then uses a literal constant instead of a runtime calculation.

### Dock Title Bar Upgrade
`QDockWidget.setTitleBarWidget()` replaces Qt-drawn dock title bars with custom widgets. Enables gradient backgrounds on dock headers (currently flat `surface_bg` via QSS). Consistent visual language: title bar → dock bars → config panel header → all gradient-painted.

### QSS Reduction
Moving styled headers from QSS to `paintEvent` via gradient mixin removes:
- `QDockWidget::title` section (lines 662-668 of stylesheet template)
- `QMenuBar` / `QMenuBar::item` sections (lines 603-617)
- `#configHeaderFrame` / `#configHeaderLabel` sections (lines 726-738)

These would participate in theme JSON `gradients` section directly instead.

### Risks
| Risk | Severity | Mitigation |
|------|----------|------------|
| Win11 snap layouts lost | Medium | Handle `WM_NCHITTEST` via `nativeEvent()` |
| DWM window shadow lost | Low | Extend DWM frame with 1px invisible border |
| Accessibility | Low | Set `accessibleName` on custom buttons |
| Custom drag-to-move | Medium | `mousePressEvent`/`mouseMoveEvent` on title bar widget |
| DPI scaling | Medium | Use `logicalDpiX()` for height constants |

### Implementation Order
1. Ship config-panel-collapse-fix first (Phase 1 — min/max pin, done)
2. Implement `GradientHeaderBar` base widget
3. Frameless window + custom title bar using `GradientHeaderBar`
4. Refactor config panel header to use `GradientHeaderBar` (collapsed height becomes constant)
5. Optional: replace dock title bars via `setTitleBarWidget()`
