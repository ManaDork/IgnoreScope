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

# Folder Gradient Framework:
#   P1 = visibility        P2 = visibility
#   P3 = config/inherited   P4 = config/inherited
#
# 12 Folder states
_FOLDER_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    # F1 — not under any mount
    "FOLDER_HIDDEN": (
        GradientClass("visibility.background", "visibility.background", "visibility.background", "visibility.background"),
        "muted",
    ),
    # F2 — mounted, no mask
    "FOLDER_VISIBLE": (
        GradientClass("visibility.visible", "visibility.visible", "visibility.visible", "visibility.visible"),
        "default",
    ),
    # F3 — mount root with deny patterns (content masked)
    "FOLDER_MOUNTED_MASKED": (
        GradientClass("visibility.visible", "visibility.visible", "config.masked", "config.mount"),
        "default",
    ),
    # F4 — under mount, denied by pattern, NOT mount root
    "FOLDER_MASKED": (
        GradientClass("visibility.hidden", "visibility.hidden", "inherited.masked", "inherited.masked"),
        "muted",
    ),
    # F5 — structural path, direct revealed child
    "FOLDER_VIRTUAL_MIRRORED_REVEALED": (
        GradientClass("visibility.hidden", "visibility.hidden", "ancestor.revealed", "ancestor.revealed"),
        "virtual_mirrored",
    ),
    # F6 — structural path, deeper revealed descendant
    "FOLDER_VIRTUAL_MIRRORED": (
        GradientClass("visibility.hidden", "visibility.hidden", "visibility.hidden", "visibility.hidden"),
        "virtual_mirrored",
    ),
    # F7 — non-filesystem named volume entry
    "FOLDER_VIRTUAL_VOLUME": (
        GradientClass("visibility.virtual", "visibility.virtual", "virtual.volume", "virtual.volume"),
        "virtual_volume",
    ),
    # F8 — non-filesystem auth volume entry
    "FOLDER_VIRTUAL_AUTH": (
        GradientClass("visibility.virtual", "visibility.virtual", "virtual.auth", "virtual.auth"),
        "virtual_auth",
    ),
    # F9 — revealed punch-through
    "FOLDER_REVEALED": (
        GradientClass("visibility.visible", "visibility.visible", "config.revealed", "config.revealed"),
        "default",
    ),
    # F10 — has pushed descendant (outside mount or hidden)
    "FOLDER_PUSHED_ANCESTOR": (
        GradientClass("visibility.background", "visibility.background", "ancestor.pushed", "ancestor.pushed"),
        "default",
    ),
    # F11 — container-only
    "FOLDER_CONTAINER_ONLY": (
        GradientClass("visibility.container_only", "visibility.container_only", "visibility.container_only", "visibility.container_only"),
        "italic",
    ),
}

# File Gradient Framework (slim layout):
#   P1 = visibility   P2 = background
#   P3 = sync (deferred → background)   P4 = pushed/status
#
# 8 File states
_FILE_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    # FI1 — hidden file, no push
    "FILE_HIDDEN": (
        GradientClass("visibility.hidden", "visibility.background", "visibility.background", "visibility.background"),
        "muted",
    ),
    # FI2 — visible file, no push
    "FILE_VISIBLE": (
        GradientClass("visibility.visible", "visibility.background", "visibility.background", "visibility.background"),
        "default",
    ),
    # FI3 — masked file (separate state, font color TBD)
    "FILE_MASKED": (
        GradientClass("visibility.hidden", "visibility.background", "visibility.background", "visibility.background"),
        "muted",
    ),
    # FI4 — revealed file (separate state, font color TBD)
    "FILE_REVEALED": (
        GradientClass("visibility.visible", "visibility.background", "visibility.background", "visibility.background"),
        "default",
    ),
    # FI5 — pushed file
    "FILE_PUSHED": (
        GradientClass("visibility.hidden", "visibility.background", "visibility.background", "config.pushed"),
        "default",
    ),
    # FI6 — host orphan: DEFERRED (gradient=None)
    "FILE_HOST_ORPHAN": (
        None,
        "italic",
    ),
    # FI7 — container orphan
    "FILE_CONTAINER_ORPHAN": (
        GradientClass("visibility.hidden", "visibility.background", "visibility.background", "status.warning"),
        "italic",
    ),
    # FI8 — container-only file
    "FILE_CONTAINER_ONLY": (
        GradientClass("visibility.container_only", "visibility.background", "visibility.background", "visibility.background"),
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

# Folder: (visibility, has_pushed_descendant, has_direct_visible_child, has_mount_masks) -> state
# Note: virtual_type is checked separately in resolve_tree_state for virtual subtypes
FOLDER_STATE_TABLE: dict[tuple, str] = {
    ("hidden",   True,  None,  None):   "FOLDER_PUSHED_ANCESTOR",
    ("hidden",   None,  None,  None):   "FOLDER_HIDDEN",
    ("visible",  None,  None,  True):   "FOLDER_MOUNTED_MASKED",  # mount root with deny patterns
    ("visible",  None,  None,  False):  "FOLDER_VISIBLE",
    ("visible",  None,  None,  None):   "FOLDER_VISIBLE",         # fallback for non-mount-root
    ("masked",   None,  None,  None):   "FOLDER_MASKED",          # under mount, denied by pattern
    ("virtual",  None,  True,  None):   "FOLDER_VIRTUAL_MIRRORED_REVEALED",
    ("virtual",  None,  False, None):   "FOLDER_VIRTUAL_MIRRORED",
    ("revealed", None,  None,  None):   "FOLDER_REVEALED",
    ("container_only", False, None, None): "FOLDER_CONTAINER_ONLY",
    ("container_only", True,  None, None): "FOLDER_CONTAINER_ONLY",
}

# File: (visibility, pushed, host_orphaned) -> state
FILE_STATE_TABLE: dict[tuple, str] = {
    ("hidden",         True,  False): "FILE_PUSHED",
    ("hidden",         False, None):  "FILE_HIDDEN",
    ("visible",        False, None):  "FILE_VISIBLE",
    ("visible",        True,  None):  "FILE_VISIBLE",          # redundant push in visible area
    ("masked",         False, None):  "FILE_MASKED",
    ("masked",         True,  False): "FILE_PUSHED",
    ("masked",         True,  True):  "FILE_HOST_ORPHAN",
    ("revealed",       False, None):  "FILE_REVEALED",
    ("revealed",       True,  None):  "FILE_REVEALED",         # redundant push in revealed area
    ("orphaned",       None,  None):  "FILE_CONTAINER_ORPHAN",
    ("container_only", False, False): "FILE_CONTAINER_ONLY",
}


def _match_key(condition: tuple, table_key: tuple) -> bool:
    """Check if a condition tuple matches a table key with None wildcards."""
    for cond_val, key_val in zip(condition, table_key):
        if key_val is None:
            continue
        if cond_val != key_val:
            return False
    return True


def resolve_tree_state(node_state, is_folder: bool, virtual_type: str = "mirrored") -> str:
    """Resolve a NodeState to a state name via truth table lookup.

    Args:
        node_state: A core.node_state.NodeState instance.
        is_folder: True for folder nodes, False for file nodes.
        virtual_type: For virtual nodes — "mirrored", "volume", or "auth".

    Returns:
        State name string (e.g. "FOLDER_HIDDEN", "FILE_PUSHED").
        Falls back to "FOLDER_HIDDEN" or "FILE_HIDDEN" if no match.
    """
    if is_folder:
        condition = (
            node_state.visibility,
            node_state.has_pushed_descendant,
            node_state.has_direct_visible_child,
            node_state.has_mount_masks,
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
            # Virtual subtype override — truth table returns VIRTUAL_MIRRORED*
            # but volume/auth nodes get their own states
            if is_folder and node_state.visibility == "virtual" and virtual_type != "mirrored":
                if virtual_type == "volume":
                    return "FOLDER_VIRTUAL_VOLUME"
                if virtual_type == "auth":
                    return "FOLDER_VIRTUAL_AUTH"
            return state_name
    import logging
    logging.getLogger(__name__).warning(
        "Unmatched state condition %s — falling back to %s", condition, fallback
    )
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
    text_virtual_purple: str = "#B48EAD"
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
        ]
