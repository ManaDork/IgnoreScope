# Widget Gradient Background Styles — Technical Design

## Overview

Add a JSON-driven widget gradient system to IgnoreScope. Widgets declare a gradient name; `StyleGui` resolves the definition from `theme.json`, builds a `QLinearGradient` or `QRadialGradient` at paint time, and a mixin paints it as the widget background. Separate from the existing delegate `GradientClass` system.

## Architecture

### Current Flow (widgets)
```
theme.json palette/ui colors
    → StyleGui._STYLESHEET_TEMPLATE
    → QSS string with solid background-color
    → QMainWindow.setStyleSheet()
    → All widgets styled with flat colors
```

### Target Flow (widgets)
```
theme.json "gradients" section (named definitions)
    → StyleGui loads WidgetGradientDef per name
    → Widget.paintEvent() calls StyleGui.build_widget_gradient(name, rect)
    → StyleGui resolves stops: theme var → hex, or passthrough hex
    → QLinearGradient / QRadialGradient constructed at widget dimensions
    → QPainter fills widget rect with gradient brush
    → Child widgets render on top (transparent background)
```

### Existing Delegate Flow (unchanged)
```
display_config.py state_defs (GradientClass with 4 var names)
    → delegates.py _paint_gradient() calls StyleGui.build_gradient()
    → 4-stop horizontal QLinearGradient at row dimensions
    → QPainter fills row rect
```

## Dependencies

### Internal
- `style_engine.py` — new dataclasses + build method (primary change target)
- `theme.json` — new `"gradients"` section
- `app.py` — wire gradients to main window, docks, status bar
- `container_root_panel.py` — wire gradient to config panel
- `GUI_STATE_STYLES.md` — document widget gradient system
- `GUI_STRUCTURE.md` — update widget notes

### External
- None

### Ordering
1. Dataclasses (`GradientStop`, `WidgetGradientDef`) in `style_engine.py`
2. JSON schema + initial gradient entries in `theme.json`
3. `StyleGui.build_widget_gradient()` method
4. Color resolution helper (shared between delegate + widget paths)
5. `GradientBackgroundMixin` paintEvent pattern
6. Wire MVP widgets
7. QSS transparency adjustments for child widgets
8. Tests
9. Architecture doc updates

## Key Changes

### New Dataclasses (`style_engine.py`)

```python
@dataclass(frozen=True)
class GradientStop:
    """One color stop in a widget gradient."""
    position: float          # 0.0–1.0, percentage along gradient line
    color: str               # theme var name (e.g. "base_0") or "#hex" direct
    offset_px: int = 0       # signed pixel nudge from percentage position


@dataclass(frozen=True)
class WidgetGradientDef:
    """Definition for a widget background gradient.

    Linear: anchor axis + angle offset. Gradient line runs along
    the anchor dimension, rotated by angle degrees.
    Radial: center point + radius as percentages of widget dimensions.
    """
    type: str                            # "linear" or "radial"
    stops: tuple[GradientStop, ...]      # 2+ color stops

    # Linear-specific
    anchor: str = "vertical"             # "horizontal" or "vertical"
    angle: float = 0.0                   # degrees offset from anchor baseline

    # Radial-specific
    center_x: float = 0.5               # % of widget width  (0.0=left, 1.0=right)
    center_y: float = 0.5               # % of widget height (0.0=top, 1.0=bottom)
    radius: float = 0.5                 # % of smaller dimension

    # Child widget transparency
    child_opacity: int = 0              # 0=fully transparent (gradient shows through),
                                        # 255=fully opaque (child paints own bg)
```

### JSON Schema (`theme.json` "gradients" section)

```json
{
    "palette": { ... },
    "ui": { ... },
    "text": { ... },
    "delegate": { ... },
    "gradients": {
        "main_window": {
            "type": "linear",
            "anchor": "vertical",
            "angle": 0,
            "child_opacity": 0,
            "stops": [
                { "pos": 0.0, "color": "base_1" },
                { "pos": 1.0, "color": "base_0" }
            ],
            "_note": "Darkest at bottom — deep purple vertical wash"
        },
        "dock_panel": {
            "type": "linear",
            "anchor": "vertical",
            "angle": 0,
            "child_opacity": 0,
            "stops": [
                { "pos": 0.0, "color": "surface_0" },
                { "pos": 0.5, "color": "base_3" },
                { "pos": 1.0, "color": "base_2" }
            ],
            "_note": "Glass card: lighter top edge fading to panel body — 3-stop top-lit"
        },
        "config_panel": {
            "type": "linear",
            "anchor": "vertical",
            "angle": 0,
            "child_opacity": 0,
            "stops": [
                { "pos": 0.0, "color": "base_3" },
                { "pos": 1.0, "color": "base_1" }
            ],
            "_note": "Subtle top-lit glass, darker than dock panels"
        },
        "status_bar": {
            "type": "linear",
            "anchor": "horizontal",
            "angle": 0,
            "child_opacity": 0,
            "stops": [
                { "pos": 0.0, "color": "base_0" },
                { "pos": 0.5, "color": "base_1" },
                { "pos": 1.0, "color": "base_0" }
            ],
            "_note": "Subtle center-bright horizontal bar"
        }
    }
}
```

**Stop schema:**
- `pos` — float 0.0–1.0 (required)
- `color` — string (required). If starts with `#`, used as direct hex. Otherwise resolved as theme var from `palette` then `ui` section.
- `offset` — integer pixels, optional (default 0). Added to computed pixel position.

**Color resolution order:**
1. Direct hex (`#BDA4FF`) → passthrough
2. `theme.palette[color]` → hex
3. `theme.ui[color]` → hex
4. KeyError → fallback to `palette.base_0` + warning

### StyleGui Methods (`style_engine.py`)

```python
class StyleGui:
    def __init__(self):
        # ... existing init ...
        self._widget_gradients: dict[str, WidgetGradientDef] = {}
        self._load_widget_gradients()

    def _load_widget_gradients(self):
        """Parse theme.json 'gradients' section into WidgetGradientDef instances."""

    def _resolve_gradient_color(self, color_ref: str) -> str:
        """Resolve a color reference to hex. Theme var lookup or hex passthrough."""

    def build_widget_gradient(
        self,
        name: str,
        width: float,
        height: float,
    ) -> Optional[QGradient]:
        """Build QLinearGradient or QRadialGradient from named definition.

        Resolves stop colors, computes pixel positions from percentages + offsets,
        constructs gradient at widget dimensions.

        Args:
            name: Gradient name from theme.json "gradients" section.
            width: Widget width in pixels.
            height: Widget height in pixels.

        Returns:
            QLinearGradient or QRadialGradient, or None if name not found.
        """

    def widget_gradient_names(self) -> list[str]:
        """List available widget gradient names."""
```

**Linear gradient construction:**
```python
# Anchor determines gradient line direction
if anchor == "vertical":
    # Base line: top-to-bottom (0° = straight down)
    x1, y1 = width / 2, 0
    x2, y2 = width / 2, height
elif anchor == "horizontal":
    # Base line: left-to-right (0° = straight across)
    x1, y1 = 0, height / 2
    x2, y2 = width, height / 2

# Rotate by angle (degrees) around center
if angle != 0:
    cx, cy = width / 2, height / 2
    rad = math.radians(angle)
    # Rotate start and end points around center
    x1, y1 = _rotate(x1, y1, cx, cy, rad)
    x2, y2 = _rotate(x2, y2, cx, cy, rad)

grad = QLinearGradient(x1, y1, x2, y2)
for stop in stops:
    px_pos = stop.position  # 0.0–1.0
    # offset_px applied as fraction of gradient length
    if stop.offset_px:
        length = math.hypot(x2 - x1, y2 - y1)
        px_pos += stop.offset_px / length if length > 0 else 0
    px_pos = max(0.0, min(1.0, px_pos))
    grad.setColorAt(px_pos, QColor(resolved_hex))
```

**Radial gradient construction:**
```python
cx = width * center_x
cy = height * center_y
r = min(width, height) * radius
grad = QRadialGradient(cx, cy, r)
for stop in stops:
    grad.setColorAt(stop.position, QColor(resolved_hex))
```

### GradientBackgroundMixin

```python
class GradientBackgroundMixin:
    """Mixin for widgets that paint a gradient background.

    Subclass must set self._gradient_name to a key from
    theme.json "gradients" section.
    """
    _gradient_name: str = ""

    def paintEvent(self, event):
        if self._gradient_name:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            gradient = StyleGui.instance().build_widget_gradient(
                self._gradient_name,
                self.width(),
                self.height(),
            )
            if gradient:
                painter.fillRect(self.rect(), QBrush(gradient))
            painter.end()
        super().paintEvent(event)
```

Widgets using the mixin:
```python
class GradientMainWindow(GradientBackgroundMixin, QMainWindow):
    _gradient_name = "main_window"

class GradientDockWidget(GradientBackgroundMixin, QDockWidget):
    _gradient_name = "dock_panel"
```

### QSS Child Opacity Application

Each gradient definition has a `child_opacity` (0–255) that controls how opaque child widget backgrounds are. At stylesheet build time, `StyleGui` reads the parent gradient's `child_opacity` and injects an RGBA `background-color` into child widget QSS rules.

```python
# In StyleGui.build_stylesheet():
# For each gradient-parent widget, resolve child background:
#   child_opacity=0   → background-color: transparent
#   child_opacity=128 → background-color: rgba(panel_bg, 0.5)
#   child_opacity=255 → background-color: {panel_bg} (fully opaque, gradient hidden)

def _child_bg(self, gradient_name: str, base_color: str) -> str:
    """Compute child background-color with alpha from gradient's child_opacity."""
    grad_def = self._widget_gradients.get(gradient_name)
    if not grad_def or grad_def.child_opacity == 0:
        return "transparent"
    if grad_def.child_opacity >= 255:
        return base_color
    # RGBA with alpha
    r, g, b = int(base_color[1:3], 16), int(base_color[3:5], 16), int(base_color[5:7], 16)
    return f"rgba({r}, {g}, {b}, {grad_def.child_opacity})"
```

This replaces the existing `background-color: {panel_bg}` entries in `_STYLESHEET_TEMPLATE` for widgets whose parent has a gradient.

### Row Gradient Opacity (`delegates.py`)

Delegate row gradients gain a JSON-configurable opacity, allowing the widget gradient behind them to bleed through.

**theme.json addition:**
```json
{
    "delegate": {
        "selection_color": "#9BA5FF",
        "selection_alpha": 100,
        "hover_color": "#50476F",
        "hover_alpha": 60,
        "row_gradient_opacity": 242
    }
}
```

`row_gradient_opacity` (0–255): 0 = row gradient invisible (widget gradient fully visible), 255 = row gradient fully opaque. Default **242** (~0.95 opacity) — subtle bleed-through of the parent widget gradient behind tree rows.

**delegates.py change — `GradientDelegate._paint_gradient()`:**
```python
def _paint_gradient(self, painter, option, gradient, color_vars):
    # ... existing gradient construction ...
    row_opacity = StyleGui.instance().row_gradient_opacity
    if row_opacity < 255:
        painter.setOpacity(row_opacity / 255.0)
    painter.fillRect(full_row_rect, QBrush(qt_gradient))
    if row_opacity < 255:
        painter.setOpacity(1.0)  # restore for text/symbol layers
```

**Layer stack with both opacity controls:**
```
┌─────────────────────────────┐
│  Dock Panel gradient        │  ← widget gradient (always opaque)
│  ┌───────────────────────┐  │
│  │ QTreeView bg          │  │  ← child_opacity: 0=transparent, 255=opaque
│  │  ┌─────────────────┐  │  │
│  │  │ Row gradient    │  │  │  ← row_gradient_opacity: 0=invisible, 255=opaque
│  │  │ (state colors)  │  │  │     Text/symbols always render at full opacity
│  │  ├─────────────────┤  │  │
│  │  │ Row gradient    │  │  │
│  │  ├─────────────────┤  │  │
│  │  │ (empty space)   │  │  │  ← widget gradient shows through
│  │  └─────────────────┘  │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

Text, symbols, selection overlay, and hover overlay render at full opacity regardless of `row_gradient_opacity` — only the background gradient layer is affected.

### Modified Files

| File | Change |
|------|--------|
| `style_engine.py` | `GradientStop`, `WidgetGradientDef` dataclasses; `_resolve_gradient_color()`, `build_widget_gradient()`, `_load_widget_gradients()` on StyleGui |
| `theme.json` | New `"gradients"` section with 4 named definitions |
| `app.py` | Replace `QMainWindow`/`QDockWidget` with gradient subclasses; wire gradient names |
| `container_root_panel.py` | Apply `GradientBackgroundMixin` or set `_gradient_name` |
| `style_engine.py` (_STYLESHEET_TEMPLATE) | Selective `background-color` alpha from `child_opacity` for gradient-parented widgets |
| `delegates.py` | `_paint_gradient()` reads `row_gradient_opacity` from theme, applies painter opacity before fillRect |
| `GUI_STATE_STYLES.md` | New widget gradient section |
| `GUI_STRUCTURE.md` | Note gradient capability on widgets |

### New Files

None — all changes fit in existing modules.

## Interfaces & Data

### `WidgetGradientDef` Signature
```python
WidgetGradientDef(
    type="linear",
    stops=(GradientStop(0.0, "base_0"), GradientStop(1.0, "base_2")),
    anchor="vertical",
    angle=0.0,
)
```

**Input:** Parsed from theme.json "gradients" section at StyleGui init.
**Output:** Consumed by `build_widget_gradient()` to produce Qt gradient objects at paint time.

### `build_widget_gradient()` Signature
```python
def build_widget_gradient(self, name: str, width: float, height: float) -> Optional[QGradient]
```

**Input:** Gradient name + widget pixel dimensions.
**Output:** Ready-to-paint `QLinearGradient` or `QRadialGradient`, or `None` if name not found.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| QSS `qlineargradient()` in stylesheets | Limited: no variable indirection, no radial, no dynamic sizing. Angle support is awkward. |
| Extend existing `GradientClass` with type/angle | Mixes delegate and widget concerns. GradientClass is optimized for 4-position row rendering. User chose separate system. |
| Per-widget gradient JSON files | Too many files for 4 widgets. Single `theme.json` section keeps all visual config together. |
| Code-defined gradients (no JSON) | Harder to theme. Doesn't match existing JSON-driven color variable pattern. |
| Unified gradient model replacing GradientClass | Over-scoped. Delegate system works well. Can unify later if beneficial. |

## Risks

| Risk | Mitigation |
|------|-----------|
| Transparency cascade breaks child widget rendering | Test each widget in isolation. Only set `transparent` where gradient parent confirmed. |
| Gradient repaint performance on resize | Qt gradient construction is fast. Only 4 widgets, not per-row. Profile if issues emerge. |
| Angle rotation math produces unexpected gradient lines | Unit test rotation helper with known angles (0°, 45°, 90°, 180°). Visual QA on widgets. |
| Color resolution ambiguity (var name vs hex) | `#` prefix is unambiguous. Document convention. |

## Architecture Doc Impact

| Document | Update Required |
|----------|----------------|
| `GUI_STATE_STYLES.md` | New section: Widget Gradient System — WidgetGradientDef, GradientStop, JSON schema, color resolution, separation from delegate system |
| `GUI_STRUCTURE.md` | Note GradientBackgroundMixin on main window, dock panels, config panel, status bar |
| `DATAFLOWCHART.md` | No change — widget gradients are cosmetic (Phase 5 display), no data flow impact |
| `ARCHITECTUREGLOSSARY.md` | No change — WidgetGradientDef is a GUI implementation detail |
