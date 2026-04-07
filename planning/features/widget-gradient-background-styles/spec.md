# Widget Gradient Background Styles — Feature Specification

## Problem Statement

All IgnoreScope GUI widgets (main window, dock panels, config panel, status bar) use **solid background colors** applied via QSS stylesheets. The only gradient rendering in the app is inside tree/list **delegates**, which paint per-row gradients using `GradientClass` + `QPainter`. There is no way to give a widget itself a gradient background.

This creates two problems:

1. **Visual flatness**: Large UI surfaces (docks, main window) are single-color rectangles. Subtle gradients add depth and visual hierarchy without introducing new UI elements.

2. **No gradient configurability**: The existing `GradientClass` is hardcoded to 4 fixed-position horizontal stops and only works inside delegates. Widget backgrounds have no gradient support at all — adding one requires writing a custom `paintEvent()` per widget with inline color values.

## Success Criteria

- Any QWidget subclass can display a gradient background defined in JSON
- Linear gradients support configurable angle and N-stop positions
- Radial gradients support center point + radius with N-stop positions
- Gradient colors reference theme.json palette/UI vars with optional hex overrides
- Gradient dimensions anchor dynamically to widget size at paint time
- Stop positions support percentage (0.0–1.0) with optional pixel offsets
- Existing tree delegate gradient system (`GradientClass`) is **not modified**

## Acceptance Criteria

- [ ] `WidgetGradientDef` dataclass exists in `style_engine.py`
- [ ] `GradientStop` dataclass exists in `style_engine.py`
- [ ] `theme.json` has a `"gradients"` section with named gradient definitions
- [ ] `StyleGui.build_widget_gradient(name, rect)` resolves gradient def → `QLinearGradient` or `QRadialGradient`
- [ ] Color references resolve: theme var name → hex from palette/ui, or direct `#hex` passthrough
- [ ] Linear gradients support `anchor` (horizontal/vertical) + `angle` (degrees offset from anchor)
- [ ] Radial gradients support `center_x`, `center_y` (% of widget dims) + `radius` (% of smaller dim)
- [ ] Stops support `position` (0.0–1.0) + optional `offset_px` (signed integer)
- [ ] `GradientBackgroundMixin` (or equivalent) provides `paintEvent()` that paints gradient background
- [ ] Main window (`QMainWindow`) has gradient background
- [ ] Dock panels (LocalHost, Scope) have gradient backgrounds
- [ ] Config panel (`ContainerRootPanel`) has gradient background
- [ ] Status bar has gradient background
- [ ] Each gradient definition includes `child_opacity` (0–255) controlling child widget background transparency
- [ ] Child widget QSS `background-color` alpha derived from parent gradient's `child_opacity` value
- [ ] `theme.json` → `delegate` section has `row_gradient_opacity` (0–255) controlling tree/list row gradient opacity
- [ ] `GradientDelegate._paint_gradient()` applies `row_gradient_opacity` before fillRect, allowing widget gradient to bleed through
- [ ] Existing `GradientClass` and delegate rendering are unchanged
- [ ] All existing tests pass unchanged
- [ ] New tests validate gradient definition loading, color resolution, and gradient construction

## Out of Scope

- **Conical gradients** — not needed for current UI; can add later
- **Tree/list delegate gradient changes** — existing `GradientClass` 4-stop system stays as-is
- **Animated gradients** — no transitions or time-based gradient shifts
- **Per-state widget gradients** — widgets don't change gradient based on app state (that's delegates)
- **Gradient unification** — merging WidgetGradientDef and GradientClass into one model is a future option, not this feature
- **QPushButton/QCheckBox gradients** — small interactive controls stay QSS-styled for now
- **Spread modes** — gradient spread beyond bounds stays at Qt default (PadSpread)

## Visual Reference

Target aesthetic: **dark purple glassmorphism** — reference image from Kaarwan design showcase.

```
Key visual properties to achieve:
┌──────────────────────────────────────────────┐
│  Main window: vertical gradient              │
│  darkest at bottom (#1A1035 → #2A1B4E)       │
│                                              │
│  ┌────────────────┐  ┌────────────────┐      │
│  │ Dock panel:    │  │ Dock panel:    │      │
│  │ glass card     │  │ glass card     │      │
│  │ lighter top    │  │ lighter top    │      │
│  │ edge, fades    │  │ edge, fades    │      │
│  │ into body      │  │ into body      │      │
│  │                │  │                │      │
│  │ Tree rows at   │  │ Tree rows at   │      │
│  │ 95% opacity —  │  │ 95% opacity —  │      │
│  │ dock gradient  │  │ dock gradient  │      │
│  │ bleeds through │  │ bleeds through │      │
│  └────────────────┘  └────────────────┘      │
│  ┌───────────────────────────────────┐       │
│  │ Status bar: subtle center-bright  │       │
│  └───────────────────────────────────┘       │
└──────────────────────────────────────────────┘

Accents: teal (#00E5CC), purple (#8B5CF6), pink (#FF6B9D)
```

**Palette gap:** Current base colors (#383144–#50476F) are too bright to match the reference (~#1A1035–#3D2A6E). A **palette shift** (tracked in `planning/backlog/gui-palette-shift.md`) is needed to reach the target darkness. The widget gradient system delivers the structural capability; the palette shift delivers the color values.

## Open Questions

None — all design decisions resolved during discovery. Transparency cascade resolved via per-gradient `child_opacity` field in JSON.

## Related Work

| Document | Relationship |
|----------|-------------|
| `planning/features/formulaic-gradient-system/` | Reference — established the 4-stop GradientClass pattern for delegates |
| `planning/features/font-derived-parity/` | Sibling — completed file style derivation using existing gradient system |
| `planning/backlog/gui-palette-shift.md` | Future — palette changes will auto-propagate through theme var references |
| `docs/architecture/GUI_STATE_STYLES.md` | Blueprint — must add widget gradient section |
| `docs/architecture/GUI_STRUCTURE.md` | Blueprint — update widget hierarchy with gradient capability |
