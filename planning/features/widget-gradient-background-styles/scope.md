# Widget Gradient Background Styles — Scope

## Phase: Single (MVP = Full)

All 4 target widgets ship together. No phasing needed — gradient system is self-contained and low risk.

## Task Breakdown

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|-----------|------------|----------------|
| 1 | Add `GradientStop` and `WidgetGradientDef` dataclasses to `style_engine.py` | — | Low | Verify no naming collision with existing `GradientClass`. Confirm frozen dataclass pattern matches existing style. |
| 2 | Add `"gradients"` section to `theme.json` with 4 named definitions (main_window, dock_panel, config_panel, status_bar) | — | Low | Verify color var names exist in palette/ui sections. |
| 3 | Implement `_resolve_gradient_color()` on `StyleGui` | 1 | Medium | Check for overlap with existing color resolution in `BaseDisplayConfig.resolve_text_color()`. Extract shared helper if warranted. |
| 4 | Implement `_load_widget_gradients()` on `StyleGui` — parse JSON into `WidgetGradientDef` instances | 1, 2 | Medium | Verify JSON parsing pattern matches existing `_color_vars` / `_font_vars` loading in BaseDisplayConfig. |
| 5 | Implement `build_widget_gradient()` on `StyleGui` — construct `QLinearGradient` / `QRadialGradient` from def + dimensions | 1, 3 | Medium | Compare with existing `build_gradient()` — shared color resolution, different construction. Rotation helper is new code. |
| 6 | Implement `GradientBackgroundMixin` with `paintEvent()` | 5 | Low | Compare paint pattern with `GradientDelegate._paint_gradient()`. Similar QPainter flow but for widgets, not delegate rows. |
| 7 | Wire gradient backgrounds to MVP widgets: main window, dock panels, config panel, status bar | 6 | Medium | Verify widget class hierarchy allows mixin insertion. Check `app.py` and `container_root_panel.py` for `paintEvent` conflicts. |
| 8 | Apply `child_opacity` to QSS for gradient-parented child widgets | 7 | Low | `_child_bg()` in StyleGui reads parent gradient's `child_opacity`. Only modify template entries for gradient parents. Don't break non-gradient widgets. |
| 9 | Add `row_gradient_opacity` to `theme.json` delegate section + wire into `GradientDelegate._paint_gradient()` | 2, 7 | Low | Only painter opacity change — text/symbols stay at full opacity. Restore opacity after fillRect. Default 255 preserves current behavior. |
| 10 | Add tests: dataclass construction, JSON loading, color resolution, gradient building, mixin paint, row opacity | 1–9 | Medium | Verify test names don't collide with existing `test_style_engine.py` test functions. |
| 11 | Update `GUI_STATE_STYLES.md` and `GUI_STRUCTURE.md` | 1–9 | Low | Cross-check widget gradient section doesn't conflict with existing delegate gradient documentation. |

## Deferred (from this feature)

- Conical gradient support (QConicalGradient)
- GradientClass / WidgetGradientDef unification
- Per-state widget gradients (gradient changes based on app state)
- Animated gradient transitions
- QPushButton / QCheckBox gradient backgrounds
- Spread mode configuration (PadSpread, RepeatSpread, ReflectSpread)
- Focal point offset for radial gradients

## Estimated File Changes

| File | Change Type |
|------|-------------|
| `IgnoreScope/gui/style_engine.py` | New dataclasses, new StyleGui methods, QSS template adjustments |
| `IgnoreScope/gui/theme.json` | New "gradients" section (4 entries) |
| `IgnoreScope/gui/app.py` | Widget class replacements or mixin application |
| `IgnoreScope/gui/container_root_panel.py` | Mixin application |
| `IgnoreScope/gui/delegates.py` | `_paint_gradient()` reads + applies `row_gradient_opacity` |
| `IgnoreScope/tests/test_gui/test_style_engine.py` | New test class for widget gradients |
| `docs/architecture/GUI_STATE_STYLES.md` | New section |
| `docs/architecture/GUI_STRUCTURE.md` | Widget hierarchy update |
