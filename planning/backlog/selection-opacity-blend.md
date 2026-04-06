# Selection Opacity Blend System

## Status: TODO (stashed from style-polish-round-2 session)

## Design

Replace current P2/P3 color replacement with opacity-based blend per gradient position.

### Formula

```
For each position when selected:
  final_color = blend(base_color, highlight_color, position_ratio)
  ratio=0 → pure base, ratio=1 → pure highlight
```

### Position Ratios (importance: P3 > P4 > P2 > P1)

```
P1 = 0.7   least important — mostly highlight
P2 = 0.5   mid blend
P3 = 0.2   most important — base shows through
P4 = 0.3   important — base mostly visible
```

### Control Variables

- `highlight_color`: single color for entire selected node background
- `opacity`: overall multiplier (0-1)
- Per-position ratios as above

### Implementation Location

Recommended: style_engine.py as `build_selected_gradient()` or optional param on `build_gradient()`. Color math is a style concern, delegate passes selection flag.

### Open Item

GradientClass "just variable names" abstraction is outdated — folder gradients are now formulaic via derive_gradient(). Review whether GradientClass should carry resolved colors or remain as variable names.

## Files

- `gui/style_engine.py` — build_gradient / build_selected_gradient
- `gui/delegates.py` — paint path passes selection state
- `gui/display_config.py` — remove GradientClass.with_selected() if it exists
