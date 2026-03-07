"""TreeDisplayConfig Base + Subclasses.

TreeDisplayConfig base class with LocalHostDisplayConfig and
ScopeDisplayConfig subclasses. Loads color/font variables from JSON files
(``tree_state_style.json``, ``tree_state_font.json``). Contains
``state_styles: dict[str, StateStyleClass]`` for MatrixState -> visual
lookup, ``columns: list[ColumnDef]``, content filter booleans, and
``undo_scope``. Subclasses override columns, filters, and undo_scope.
Each config CAN point to different JSON files. Does NOT store state,
render UI, or interact with CORE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .style_engine import FontStyleClass, GradientClass, StateStyleClass


# ------------------------------------------------------------------
# ColumnDef
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnDef:
    """Definition for one tree column (per GUI_LAYOUT_SPECS Section 10B)."""

    header: str
    visible: bool = True
    width: int | str = "stretch"
    checkable: bool = False
    check_field: Optional[str] = None
    enable_condition: Optional[str] = None
    cascade_on_uncheck: list[str] = field(default_factory=list)
    files_only: bool = False
    folders_only: bool = False
    symbol_type: Optional[str] = None


# ------------------------------------------------------------------
# State definition tuples: (GradientClass, font_var_name)
# GradientClass args are variable names from tree_state_style.json
# font_var_name resolves via tree_state_font.json
# ------------------------------------------------------------------

# 8 Folder states (GUI_STATE_STYLES Section 3.1)
_FOLDER_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    # F1
    "FOLDER_HIDDEN": (
        GradientClass("background", "background", "background", "background"),
        "muted",
    ),
    # F2
    "FOLDER_VISIBLE": (
        GradientClass("background", "background", "visible", "visible"),
        "default",
    ),
    # F3
    "FOLDER_MOUNTED_MASKED": (
        GradientClass("mounted", "mounted", "masked", "masked"),
        "muted",
    ),
    # F4
    "FOLDER_MOUNTED_MASKED_PUSHED": (
        GradientClass("mounted", "mounted", "masked", "pushed"),
        "default",
    ),
    # F5 (user-confirmed gradient)
    "FOLDER_MASKED_REVEALED": (
        GradientClass("masked", "masked", "hidden", "revealed"),
        "default",
    ),
    # F6
    "FOLDER_MASKED_MIRRORED": (
        GradientClass("masked", "masked", "mirrored", "mirrored"),
        "default",
    ),
    # F7
    "FOLDER_REVEALED": (
        GradientClass("revealed", "revealed", "visible", "visible"),
        "default",
    ),
    # F8
    "FOLDER_PUSHED_ANCESTOR": (
        GradientClass("background", "background", "background", "pushed"),
        "default",
    ),
}

# 7 File states (GUI_STATE_STYLES Section 3.1)
_FILE_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    # FI1
    "FILE_HIDDEN": (
        GradientClass("background", "background", "background", "background"),
        "muted",
    ),
    # FI2
    "FILE_VISIBLE": (
        GradientClass("background", "background", "visible", "visible"),
        "default",
    ),
    # FI3
    "FILE_MASKED": (
        GradientClass("background", "background", "hidden", "hidden"),
        "muted",
    ),
    # FI4
    "FILE_REVEALED": (
        GradientClass("background", "background", "visible", "revealed"),
        "default",
    ),
    # FI5
    "FILE_PUSHED": (
        GradientClass("pushed", "pushed", "hidden", "hidden"),
        "default",
    ),
    # FI6 — DEFERRED (gradient=None)
    "FILE_HOST_ORPHAN": (
        None,
        "italic",
    ),
    # FI7
    "FILE_CONTAINER_ORPHAN": (
        GradientClass("warning", "warning", "hidden", "hidden"),
        "italic",
    ),
}

_TREE_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    **_FOLDER_STATE_DEFS,
    **_FILE_STATE_DEFS,
}


# ------------------------------------------------------------------
# Truth tables — keyed by condition tuple, None = don't-care
# Values are state name strings (keys into _TREE_STATE_DEFS)
# ------------------------------------------------------------------

# Folder: (visibility, has_pushed_descendant, has_direct_visible_child) -> state
FOLDER_STATE_TABLE: dict[tuple, str] = {
    ("hidden",   True,  None):  "FOLDER_PUSHED_ANCESTOR",  # pushed ancestor outside mount
    ("hidden",   None,  None):  "FOLDER_HIDDEN",
    ("visible",  None,  None):  "FOLDER_VISIBLE",
    ("masked",   False, None):  "FOLDER_MOUNTED_MASKED",
    ("masked",   True,  None):  "FOLDER_MOUNTED_MASKED_PUSHED",
    ("mirrored", None,  True):  "FOLDER_MASKED_REVEALED",
    ("mirrored", None,  False): "FOLDER_MASKED_MIRRORED",
    ("revealed", None,  None):  "FOLDER_REVEALED",
}

# File: (visibility, pushed, host_orphaned) -> state
FILE_STATE_TABLE: dict[tuple, str] = {
    ("hidden",   True,  False): "FILE_PUSHED",     # unmounted pushed file
    ("hidden",   False, None):  "FILE_HIDDEN",
    ("visible",  False, None):  "FILE_VISIBLE",
    ("masked",   False, None):  "FILE_MASKED",
    ("revealed", False, None):  "FILE_REVEALED",
    ("masked",   True,  False): "FILE_PUSHED",
    ("masked",   True,  True):  "FILE_HOST_ORPHAN",
    ("orphaned", None,  None):  "FILE_CONTAINER_ORPHAN",
}


def _match_key(condition: tuple, table_key: tuple) -> bool:
    """Check if a condition tuple matches a table key with None wildcards."""
    for cond_val, key_val in zip(condition, table_key):
        if key_val is None:
            continue
        if cond_val != key_val:
            return False
    return True


def resolve_tree_state(node_state, is_folder: bool) -> str:
    """Resolve a NodeState to a state name via truth table lookup.

    Args:
        node_state: A core.node_state.NodeState instance.
        is_folder: True for folder nodes, False for file nodes.

    Returns:
        State name string (e.g. "FOLDER_HIDDEN", "FILE_PUSHED").
        Falls back to "FOLDER_HIDDEN" or "FILE_HIDDEN" if no match.
    """
    if is_folder:
        condition = (
            node_state.visibility,
            node_state.has_pushed_descendant,
            node_state.has_direct_visible_child,
        )
        table = FOLDER_STATE_TABLE
        fallback = "FOLDER_HIDDEN"
    else:
        # host_orphaned is not on NodeState yet (DEFERRED).
        # Default to False until FILE_HOST_ORPHAN is implemented.
        host_orphaned = getattr(node_state, "host_orphaned", False)
        condition = (
            node_state.visibility,
            node_state.pushed,
            host_orphaned,
        )
        table = FILE_STATE_TABLE
        fallback = "FILE_HIDDEN"

    for key, state_name in table.items():
        if _match_key(condition, key):
            return state_name
    return fallback


# ------------------------------------------------------------------
# TreeDisplayConfig base class
# ------------------------------------------------------------------

class BaseDisplayConfig:
    """Shared display configuration base for tree and list panels.

    Loads color/font variables from JSON, builds state_styles dict
    from a caller-provided state definitions dictionary.
    """

    text_primary: str = "#ECEFF4"

    def __init__(
        self,
        state_defs: dict[str, tuple[Optional[GradientClass], str]],
        color_json: str,
        font_json: str,
    ):
        gui_dir = Path(__file__).parent

        with open(gui_dir / color_json, "r") as f:
            self._color_vars: dict[str, str] = json.load(f)

        with open(gui_dir / font_json, "r") as f:
            self._font_vars: dict[str, dict] = json.load(f)

        self.state_styles: dict[str, StateStyleClass] = self._build_state_styles(state_defs)

    def _build_state_styles(
        self, state_defs: dict[str, tuple[Optional[GradientClass], str]],
    ) -> dict[str, StateStyleClass]:
        """Build StateStyleClass instances from state defs + font vars."""
        styles = {}
        for name, (gradient, font_var) in state_defs.items():
            font_data = self._font_vars[font_var]
            font = FontStyleClass(
                weight=font_data["weight"],
                italic=font_data["italic"],
                text_color_var=font_data["text_color"],
            )
            styles[name] = StateStyleClass(gradient=gradient, font=font)
        return styles

    def resolve_text_color(self, font: FontStyleClass) -> str:
        """Resolve a FontStyleClass text_color_var to a hex color string."""
        var_name = font.text_color_var
        return getattr(self, var_name, self.text_primary)

    @property
    def color_vars(self) -> dict[str, str]:
        """Color variable dict for gradient construction."""
        return self._color_vars


class TreeDisplayConfig(BaseDisplayConfig):
    """Display configuration for tree panels.

    Extends BaseDisplayConfig with tree-specific color variables,
    columns, display filters, and undo scope.
    """

    # Additional one-off color variables (Section 6.3)
    text_dim: str = "#616E88"
    text_warning: str = "#D08770"
    hover_color: str = "#4C566A"
    hover_alpha: int = 60
    selection_alpha: int = 100

    def __init__(
        self,
        color_json: str = "tree_state_style.json",
        font_json: str = "tree_state_font.json",
    ):
        super().__init__(_TREE_STATE_DEFS, color_json, font_json)

    # Subclass-defined attributes (defaults)
    columns: list[ColumnDef] = []
    file_actions: frozenset[str] = frozenset()
    display_files: bool = False
    display_hidden: bool = True
    display_non_mounted: bool = True
    display_masked_dead_branches: bool = True
    display_virtual_nodes: bool = False
    display_orphaned: bool = True
    undo_scope: str = "full"


# ------------------------------------------------------------------
# Subclasses
# ------------------------------------------------------------------

class LocalHostDisplayConfig(TreeDisplayConfig):
    """Local Host Configuration panel (left dock).

    5 columns: Local Host | Mount | Mask | Reveal | Pushed
    Files + folders, shows hidden + non-mounted + dead branches.
    Mount/Mask/Reveal on folders only, Push on files only.
    """

    display_files = True
    file_actions = frozenset({"push", "remove"})
    display_hidden = True
    display_non_mounted = True
    display_masked_dead_branches = True
    display_virtual_nodes = False
    display_orphaned = True
    undo_scope = "full"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.columns = [
            ColumnDef(
                header="Local Host",
                width="stretch",
            ),
            ColumnDef(
                header="Mount",
                width=70,
                checkable=True,
                check_field="mounted",
                enable_condition="can_check_mounted",
                cascade_on_uncheck=["masked", "revealed"],
                folders_only=True,
                symbol_type="check",
            ),
            ColumnDef(
                header="Mask",
                width=70,
                checkable=True,
                check_field="masked",
                enable_condition="can_check_masked",
                cascade_on_uncheck=["revealed"],
                folders_only=True,
                symbol_type="check",
            ),
            ColumnDef(
                header="Reveal",
                width=70,
                checkable=True,
                check_field="revealed",
                enable_condition="can_check_revealed",
                folders_only=True,
                symbol_type="check",
            ),
            ColumnDef(
                header="Pushed",
                width=70,
                checkable=True,
                check_field="pushed",
                enable_condition="can_push",
                files_only=True,
                symbol_type="pushed_status",
            ),
        ]


class ScopeDisplayConfig(TreeDisplayConfig):
    """Scope Configuration panel (right dock).

    2 columns: Container Scope | Pushed
    Files + folders, hides hidden + non-mounted + dead branches.
    """

    display_files = True
    file_actions = frozenset({"push", "remove", "update", "pull"})
    display_hidden = False
    display_non_mounted = False
    display_masked_dead_branches = False
    display_virtual_nodes = True
    display_orphaned = True
    undo_scope = "selection_history"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.columns = [
            ColumnDef(
                header="Container Scope",
                width="stretch",
            ),
            ColumnDef(
                header="Pushed",
                width=80,
                checkable=True,
                check_field="pushed",
                enable_condition="can_push",
                symbol_type="pushed_status",
            ),
        ]
