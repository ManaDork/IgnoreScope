"""List Panel Configuration.

ListDisplayConfig for Session History panel. Inherits BaseDisplayConfig
for JSON loading, state_styles, resolve_text_color, color_vars.
Uses HISTORY_ state definitions with ``list_style.json`` / ``list_font.json``.
Does NOT store state, render UI, or interact with CORE.
"""

from __future__ import annotations

from typing import Optional

from .display_config import BaseDisplayConfig
from .style_engine import GradientClass


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

    Inherits JSON loading, state_styles, resolve_text_color, color_vars
    from BaseDisplayConfig. Passes HISTORY_ state defs and list-specific
    JSON files.
    """

    def __init__(
        self,
        color_json: str = "list_style.json",
        font_json: str = "list_font.json",
    ):
        super().__init__(_HISTORY_STATE_DEFS, color_json, font_json)
