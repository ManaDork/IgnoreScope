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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QColor, QLinearGradient


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
    ) -> QLinearGradient:
        """Construct QLinearGradient from GradientClass + color variable dict.

        Args:
            gradient: 4-position gradient with variable names.
            color_vars: Variable name -> hex color mapping.
            width: Gradient width in pixels.

        Returns:
            Horizontal QLinearGradient with 4 stops.
        """
        g = QLinearGradient(0, 0, width, 0)
        g.setColorAt(0.0, QColor(color_vars[gradient.pos1]))
        g.setColorAt(0.25, QColor(color_vars[gradient.pos2]))
        g.setColorAt(0.50, QColor(color_vars[gradient.pos3]))
        g.setColorAt(0.75, QColor(color_vars[gradient.pos4]))
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

    def build_stylesheet(self) -> str:
        """Build APP_STYLESHEET from theme.json ui tokens."""
        ui = self._theme["ui"]
        pal = self._theme["palette"]
        # Resolve checkbox X icon path (forward slashes for Qt QSS)
        checkbox_x = Path(__file__).parent / "icons" / "checkbox_x.svg"
        checkbox_x_path = str(checkbox_x).replace("\\", "/")
        return _STYLESHEET_TEMPLATE.format(
            window_bg=ui["window_bg"],
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
            frost_0=pal["frost_0"],
            frost_1=pal["frost_1"],
            frost_2=pal["frost_2"],
            frost_3=pal["frost_3"],
            checkbox_x_path=checkbox_x_path,
        )


# ------------------------------------------------------------------
# Stylesheet template (used by build_stylesheet)
# ------------------------------------------------------------------

_STYLESHEET_TEMPLATE = """\
/* Main window */
QMainWindow {{
    background-color: {window_bg};
}}

/* Tree views */
QTreeView {{
    border: 1px solid {border};
    border-radius: 4px;
    background-color: {panel_bg};
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
    background-color: {panel_bg};
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
