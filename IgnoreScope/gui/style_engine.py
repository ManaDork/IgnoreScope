"""Color Theme Engine.

Singleton that loads theme.json, pre-builds QColor lookups for all 6 theme
sections, generates the application QSS stylesheet, and constructs
GradientClass instances from variable-resolved colors. Provides
``build_gradient(GradientClass, color_vars, width)`` for 4-stop universal
gradient construction. Does NOT define visual states (those live in
TreeDisplayConfig.state_styles), create widgets, interact with tree models,
or manage application state. This is the ONLY layout-phase module with real
logic.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QRadialGradient


# ------------------------------------------------------------------
# Dataclasses — GradientClass / FontStyleClass / StateStyleClass
# ------------------------------------------------------------------

@dataclass(frozen=True)
class GradientClass:
    """Universal 4-position gradient. Each field is a variable NAME.

    Position layout::

        |-- pos1 (0.0) --|-- pos2 (0.25) --|-- pos3 (0.50) --|-- pos4 (0.75) --|
    """

    pos1: str
    pos2: str
    pos3: str
    pos4: str


@dataclass(frozen=True)
class FontStyleClass:
    """Text style recipe resolved from font JSON."""

    weight: str = "normal"
    italic: bool = False
    text_color_var: str = "text_primary"


@dataclass(frozen=True)
class StateStyleClass:
    """Complete visual recipe: gradient + font."""

    gradient: Optional[GradientClass] = None  # None for DEFERRED states
    font: FontStyleClass = FontStyleClass()


# ------------------------------------------------------------------
# Dataclasses — Widget Gradient System
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _rotate(
    x: float, y: float, cx: float, cy: float, rad: float,
) -> tuple[float, float]:
    """Rotate point (x, y) around center (cx, cy) by rad radians."""
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    dx, dy = x - cx, y - cy
    return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a


# ------------------------------------------------------------------
# GradientBackgroundMixin
# ------------------------------------------------------------------

class GradientBackgroundMixin:
    """Mixin for widgets that paint a gradient background.

    Subclass must set ``_gradient_name`` to a key from
    theme.json ``"gradients"`` section.
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


# ------------------------------------------------------------------
# StyleGui singleton
# ------------------------------------------------------------------

class StyleGui:
    """Singleton style engine -- loads theme.json."""

    _instance: Optional[StyleGui] = None

    def __init__(self):
        theme_path = Path(__file__).parent / "theme.json"
        with open(theme_path, "r") as f:
            self._theme = json.load(f)

        # Delegate overlay colors
        d = self._theme["delegate"]
        self._selection_qcolor = QColor(d["selection_color"])
        self._selection_qcolor.setAlpha(d["selection_alpha"])
        self._hover_qcolor = QColor(d["hover_color"])
        self._hover_qcolor.setAlpha(d["hover_alpha"])

        # Widget gradients
        self._widget_gradients: dict[str, WidgetGradientDef] = {}
        self._load_widget_gradients()

    @classmethod
    def instance(cls) -> StyleGui:
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def build_gradient(
        self,
        gradient: GradientClass,
        color_vars: dict[str, str],
        width: float,
        x_offset: float = 0.0,
    ) -> QLinearGradient:
        """Construct QLinearGradient from GradientClass + color variable dict.

        3-zone layout:
          LEFT (self):     pos1 at 0.0, pos2 at 0.4  — holds self state
          MIDDLE (parent): pos3 at 0.6                — brief parent zone
          RIGHT (child):   pos4 at 0.85               — child influence trailing off

        Args:
            gradient: 4-position gradient with variable names.
            color_vars: Variable name -> hex color mapping.
            width: Gradient width in pixels.
            x_offset: Horizontal offset for cell rect alignment.

        Returns:
            Horizontal QLinearGradient with 4 stops.
        """
        g = QLinearGradient(x_offset, 0, x_offset + width, 0)
        g.setColorAt(0.0, QColor(color_vars[gradient.pos1]))
        g.setColorAt(0.4, QColor(color_vars[gradient.pos2]))
        g.setColorAt(0.6, QColor(color_vars[gradient.pos3]))
        g.setColorAt(0.85, QColor(color_vars[gradient.pos4]))
        return g

    def selection_color(self) -> QColor:
        """Get selection overlay color (with alpha)."""
        return self._selection_qcolor

    def hover_color(self) -> QColor:
        """Get hover overlay color (with alpha)."""
        return self._hover_qcolor

    def palette_color(self, key: str) -> str:
        """Get Nord palette hex value by key."""
        return self._theme["palette"].get(key, "#FFFFFF")

    def ui_color(self, key: str) -> str:
        """Get UI semantic color hex value by key."""
        return self._theme["ui"].get(key, "#FFFFFF")

    # ------------------------------------------------------------------
    # Widget Gradient API
    # ------------------------------------------------------------------

    def _load_widget_gradients(self) -> None:
        """Parse theme.json 'gradients' section into WidgetGradientDef instances."""
        gradients_data = self._theme.get("gradients", {})
        for name, gdef in gradients_data.items():
            if name.startswith("_"):
                continue
            stops = tuple(
                GradientStop(
                    position=s["pos"],
                    color=s["color"],
                    offset_px=s.get("offset", 0),
                )
                for s in gdef.get("stops", [])
            )
            self._widget_gradients[name] = WidgetGradientDef(
                type=gdef.get("type", "linear"),
                stops=stops,
                anchor=gdef.get("anchor", "vertical"),
                angle=gdef.get("angle", 0.0),
                center_x=gdef.get("center_x", 0.5),
                center_y=gdef.get("center_y", 0.5),
                radius=gdef.get("radius", 0.5),
                child_opacity=gdef.get("child_opacity", 0),
            )

    def _resolve_gradient_color(self, color_ref: str) -> str:
        """Resolve a color reference to hex. Theme var lookup or hex passthrough."""
        if color_ref.startswith("#"):
            return color_ref
        pal = self._theme.get("palette", {})
        if color_ref in pal:
            return pal[color_ref]
        ui = self._theme.get("ui", {})
        if color_ref in ui:
            return ui[color_ref]
        return pal.get("base_0", "#383144")

    def build_widget_gradient(
        self,
        name: str,
        width: float,
        height: float,
    ) -> Optional[QLinearGradient | QRadialGradient]:
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
        gdef = self._widget_gradients.get(name)
        if gdef is None:
            return None

        resolved = [
            (stop, self._resolve_gradient_color(stop.color))
            for stop in gdef.stops
        ]

        if gdef.type == "radial":
            cx = width * gdef.center_x
            cy = height * gdef.center_y
            r = min(width, height) * gdef.radius
            grad = QRadialGradient(cx, cy, r)
            for stop, hex_color in resolved:
                grad.setColorAt(stop.position, QColor(hex_color))
            return grad

        # Linear gradient
        if gdef.anchor == "horizontal":
            x1, y1 = 0.0, height / 2
            x2, y2 = float(width), height / 2
        else:  # vertical
            x1, y1 = width / 2, 0.0
            x2, y2 = width / 2, float(height)

        if gdef.angle != 0:
            rot_cx, rot_cy = width / 2, height / 2
            rad = math.radians(gdef.angle)
            x1, y1 = _rotate(x1, y1, rot_cx, rot_cy, rad)
            x2, y2 = _rotate(x2, y2, rot_cx, rot_cy, rad)

        grad = QLinearGradient(x1, y1, x2, y2)
        for stop, hex_color in resolved:
            px_pos = stop.position
            if stop.offset_px:
                length = math.hypot(x2 - x1, y2 - y1)
                px_pos += stop.offset_px / length if length > 0 else 0
            px_pos = max(0.0, min(1.0, px_pos))
            grad.setColorAt(px_pos, QColor(hex_color))

        return grad

    def widget_gradient_names(self) -> list[str]:
        """List available widget gradient names."""
        return list(self._widget_gradients.keys())

    @property
    def row_gradient_opacity(self) -> int:
        """Row gradient opacity (0–255) from theme.json delegate section."""
        return self._theme.get("delegate", {}).get("row_gradient_opacity", 255)

    def _child_bg(self, gradient_name: str, base_color: str) -> str:
        """Compute child background-color with alpha from gradient's child_opacity."""
        grad_def = self._widget_gradients.get(gradient_name)
        if not grad_def or grad_def.child_opacity == 0:
            return "transparent"
        if grad_def.child_opacity >= 255:
            return base_color
        r = int(base_color[1:3], 16)
        g = int(base_color[3:5], 16)
        b = int(base_color[5:7], 16)
        return f"rgba({r}, {g}, {b}, {grad_def.child_opacity})"

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def build_stylesheet(self) -> str:
        """Build APP_STYLESHEET from theme.json ui tokens."""
        ui = self._theme["ui"]
        pal = self._theme["palette"]
        # Resolve checkbox X icon path (forward slashes for Qt QSS)
        checkbox_x = Path(__file__).parent / "icons" / "checkbox_x.svg"
        checkbox_x_path = str(checkbox_x).replace("\\", "/")

        # Gradient-aware backgrounds: transparent when widget/parent has gradient
        gradient_window_bg = (
            "transparent" if "main_window" in self._widget_gradients
            else ui["window_bg"]
        )
        gradient_tree_bg = self._child_bg("dock_panel", ui["panel_bg"])
        gradient_status_bg = (
            "transparent" if "status_bar" in self._widget_gradients
            else ui["panel_bg"]
        )

        return _STYLESHEET_TEMPLATE.format(
            window_bg=ui["window_bg"],
            gradient_window_bg=gradient_window_bg,
            gradient_tree_bg=gradient_tree_bg,
            gradient_status_bg=gradient_status_bg,
            panel_bg=ui["panel_bg"],
            surface_bg=ui["surface_bg"],
            border=ui["border"],
            text_primary=ui["text_primary"],
            text_bright=ui["text_bright"],
            text_muted=ui["text_muted"],
            text_disabled=ui["text_disabled"],
            accent_primary=ui["accent_primary"],
            accent_secondary=ui["accent_secondary"],
            accent_teal=ui["accent_teal"],
            checkbox_x_path=checkbox_x_path,
        )


# ------------------------------------------------------------------
# Stylesheet template (used by build_stylesheet)
# ------------------------------------------------------------------

_STYLESHEET_TEMPLATE = """\
/* Main window */
QMainWindow {{
    background-color: {gradient_window_bg};
}}

/* Tree views */
QTreeView {{
    border: 1px solid {border};
    border-radius: 4px;
    background-color: {gradient_tree_bg};
    color: {text_primary};
}}

QTreeView::item {{
    padding: 4px;
    border-bottom: 1px solid {surface_bg};
    background: none;
}}

QTreeView::item:hover {{
    background: none;
}}

QTreeView::item:selected {{
    background: none;
}}

/* Header sections */
QHeaderView::section {{
    background-color: {surface_bg};
    color: {text_bright};
    padding: 6px;
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    font-weight: bold;
}}

/* Group boxes */
QGroupBox {{
    font-weight: bold;
    border: 1px solid {border};
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
    color: {text_bright};
    background-color: {window_bg};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {accent_primary};
}}

/* Buttons */
QPushButton {{
    background-color: {surface_bg};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 6px 12px;
    min-width: 60px;
    color: {text_bright};
}}

QPushButton:hover {{
    background-color: {border};
    border-color: {accent_secondary};
}}

QPushButton:pressed {{
    background-color: {accent_secondary};
}}

QPushButton:disabled {{
    background-color: {panel_bg};
    color: {border};
}}

/* Line edits */
QLineEdit {{
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
    background-color: {panel_bg};
    color: {text_bright};
    selection-background-color: {accent_secondary};
}}

QLineEdit:focus {{
    border-color: {accent_primary};
}}

QLineEdit::placeholder {{
    color: {border};
}}

/* Checkboxes */
QCheckBox {{
    spacing: 6px;
    color: {text_primary};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid {border};
    background-color: {panel_bg};
}}

QCheckBox::indicator:checked {{
    background-color: {accent_secondary};
    border-color: {accent_primary};
    image: url({checkbox_x_path});
}}

QCheckBox::indicator:hover {{
    border-color: {accent_primary};
}}

/* Menu bar */
QMenuBar {{
    background-color: {panel_bg};
    border-bottom: 1px solid {border};
    color: {text_primary};
}}

QMenuBar::item {{
    padding: 6px 12px;
    background-color: transparent;
}}

QMenuBar::item:selected {{
    background-color: {accent_secondary};
    color: {text_bright};
}}

/* Menus */
QMenu {{
    background-color: {panel_bg};
    border: 1px solid {border};
    color: {text_primary};
}}

QMenu::item {{
    padding: 6px 24px;
}}

QMenu::item:selected {{
    background-color: {accent_secondary};
    color: {text_bright};
}}

QMenu::item:disabled {{
    color: {text_muted};
}}

QMenu::separator {{
    height: 1px;
    background-color: {border};
    margin: 4px 8px;
}}

/* Status bar */
QStatusBar {{
    background-color: {gradient_status_bg};
    border-top: 1px solid {border};
    color: {text_primary};
}}

/* Labels */
QLabel {{
    color: {text_primary};
}}

/* Dock widgets */
QDockWidget {{
    color: {accent_primary};
}}

QDockWidget::title {{
    background-color: {surface_bg};
    color: {accent_primary};
    padding: 6px;
    border: 1px solid {border};
}}

QDockWidget::close-button, QDockWidget::float-button {{
    background-color: transparent;
    border: none;
    padding: 2px;
}}

QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background-color: {border};
}}

/* Splitter — custom painted handle, no QSS styling needed */
QSplitter::handle {{
    background-color: transparent;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background-color: {window_bg};
    width: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background-color: {border};
    border-radius: 6px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {accent_secondary};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {window_bg};
    height: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {border};
    border-radius: 6px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {accent_secondary};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

#configHeaderFrame {{
    background-color: {surface_bg};
    border: 1px solid {border};
    border-radius: 4px;
}}

#configHeaderLabel {{
    color: {accent_primary};
    font-weight: bold;
    font-size: 12px;
    background: transparent;
    border: none;
}}

#configViewerText {{
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    font-size: 11px;
    background-color: {panel_bg};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 4px;
}}

/* Dialog styling */
QDialog {{
    background-color: {window_bg};
}}

QInputDialog {{
    background-color: {window_bg};
}}

/* Message boxes */
QMessageBox {{
    background-color: {window_bg};
}}

QMessageBox QLabel {{
    color: {text_primary};
}}
"""
