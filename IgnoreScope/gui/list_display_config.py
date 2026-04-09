"""List Panel Configuration.

ListDisplayConfig for Session History panel. Inherits BaseDisplayConfig
for state_styles, resolve_text_color, color_vars. Loads from
``list_style.json`` / ``list_font.json`` directly (list panel section
deferred until session_history is wired to UI).
Does NOT store state, render UI, or interact with CORE.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .display_config import BaseDisplayConfig
from .style_engine import GradientClass, StyleGui


# ------------------------------------------------------------------
# HISTORY_ state definitions (GUI_LAYOUT_SPECS Section 12C)
# (GradientClass, font_var_name)
# ------------------------------------------------------------------

_HISTORY_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    # H1
    "HISTORY_NORMAL": (
        GradientClass("background", "background", "background", "background"),
        "default",
    ),
    # H2
    "HISTORY_UNDO_CURRENT": (
        GradientClass("selected", "selected", "background", "background"),
        "default",
    ),
    # H3
    "HISTORY_REDO_AVAILABLE": (
        GradientClass("warning", "background", "background", "background"),
        "default",
    ),
    # H4
    "HISTORY_DESTRUCTIVE": (
        GradientClass("background", "background", "destructive", "destructive"),
        "default",
    ),
    # H5
    "HISTORY_DESTRUCTIVE_SELECTED": (
        GradientClass("selected", "background", "destructive", "destructive"),
        "default",
    ),
}


# ------------------------------------------------------------------
# ListDisplayConfig
# ------------------------------------------------------------------

class ListDisplayConfig(BaseDisplayConfig):
    """Display configuration for the Session History list panel.

    Loads list_style.json / list_font.json directly (list panel section
    not yet in consolidated theme). Passes resolved dicts to
    BaseDisplayConfig.
    """

    def __init__(self):
        gui_dir = Path(__file__).parent

        with open(gui_dir / "list_style.json", "r") as f:
            color_vars: dict[str, str] = json.load(f)

        with open(gui_dir / "list_font.json", "r") as f:
            font_vars: dict[str, dict] = json.load(f)

        # Text colors from consolidated theme base.text section
        text_colors = dict(StyleGui.instance()._theme_data["base"]["text"])

        super().__init__(_HISTORY_STATE_DEFS, color_vars, font_vars, text_colors)
