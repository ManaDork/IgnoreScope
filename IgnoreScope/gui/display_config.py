"""TreeDisplayConfig Base + Subclasses.

TreeDisplayConfig base class with LocalHostDisplayConfig and
ScopeDisplayConfig subclasses. Loads color/font variables from JSON files
(``tree_state_style.json``, ``tree_state_font.json``). Contains
``state_styles: dict[str, StateStyleClass]`` for display state name -> visual
lookup, ``columns: list[ColumnDef]``, and content filter booleans.
Folder states derived via ``derive_gradient()`` formula. File states hand-built.
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

# ------------------------------------------------------------------
# Folder Gradient Formula
#   P1 = visibility (what container sees)
#   P2 = context (parent/inherited visibility)
#   P3 = ancestor (descendant tracking) — falls to P4 when absent
#   P4 = config||inherited (direct/inherited action) — falls to P1 when absent
# ------------------------------------------------------------------

_P2_MAP = {"visible": "visible", "hidden": "hidden", "background": "background",
           "virtual": "virtual", "container_only": "container_only"}


def derive_gradient(
    visibility: str,
    is_mount_root: bool = False,
    is_masked: bool = False,
    is_revealed: bool = False,
    has_visible_descendant: bool = False,
    virtual_type: str = "mirrored",
    container_only: bool = False,
) -> tuple[GradientClass, str]:
    """Derive gradient + font var from node properties. No lookup table.

    Returns:
        (GradientClass, font_var_name) tuple for StateStyleClass construction.
    """
    # P1: what the container sees (must match JSON key suffix in visibility.*)
    is_virtual = (visibility == "virtual")
    if container_only:
        p1 = "container_only"
    elif is_virtual and virtual_type in ("volume", "auth"):
        p1 = "virtual"         # non-filesystem accent color
    elif is_virtual:
        p1 = "hidden"          # mirrored content IS hidden
    elif visibility in ("visible", "revealed"):
        p1 = "visible"
    elif visibility == "masked":
        p1 = "hidden"
    else:
        p1 = "background"      # not under any mount

    # P2: parent context — REVEALED gets P2=hidden (visible in hidden context: punch-through)
    if p1 == "visible" and is_revealed:
        p2 = "hidden"
    else:
        p2 = _P2_MAP.get(p1, "hidden")

    # P4: config/inherited action — full color variable name
    # When virtual, masking is already captured in visibility — skip is_masked
    if is_mount_root:
        p4_var = "config.mount"
    elif is_revealed:
        p4_var = "config.revealed"
    elif is_masked and not is_virtual:
        p4_var = "inherited.masked"
    elif is_virtual and virtual_type in ("volume", "auth"):
        p4_var = f"virtual.{virtual_type}"
    else:
        p4_var = None

    # P3: ancestor tracking (overrides P4 position when present)
    has_ancestor = has_visible_descendant and not is_revealed
    p3_var = "ancestor.visible" if has_ancestor else p4_var

    # Resolve with fallback chain: P3→P4→P1, P4→P1
    p1_var = f"visibility.{p1}"
    p2_var = f"visibility.{p2}"
    if p3_var is None:
        p3_var = p1_var
    if p4_var is None:
        p4_var = p1_var

    # Font derivation
    if container_only:
        font = "italic"
    elif is_virtual and virtual_type in ("volume", "auth"):
        font = f"virtual_{virtual_type}"
    elif is_virtual:
        font = "virtual_mirrored"
    elif p1 in ("hidden", "background") and not has_visible_descendant:
        font = "muted"
    else:
        font = "default"

    return GradientClass(p1_var, p2_var, p3_var, p4_var), font


# Folder state inputs — declarative tuples fed to derive_gradient() at init
# Each entry: (name, kwargs for derive_gradient)
_FOLDER_STATE_INPUTS: dict[str, dict] = {
    "FOLDER_HIDDEN":            {"visibility": "hidden"},
    "FOLDER_VISIBLE":           {"visibility": "visible"},
    "FOLDER_MOUNTED":           {"visibility": "visible", "is_mount_root": True},
    "FOLDER_MOUNTED_REVEALED":  {"visibility": "visible", "is_mount_root": True, "has_visible_descendant": True},
    "FOLDER_MASKED":            {"visibility": "masked", "is_masked": True},
    "FOLDER_REVEALED":          {"visibility": "revealed", "is_revealed": True},
    "FOLDER_MIRRORED":          {"visibility": "virtual"},
    "FOLDER_MIRRORED_REVEALED": {"visibility": "virtual", "has_visible_descendant": True},
    "FOLDER_VIRTUAL_VOLUME":    {"visibility": "virtual", "virtual_type": "volume"},
    "FOLDER_VIRTUAL_AUTH":      {"visibility": "virtual", "virtual_type": "auth"},
    "FOLDER_PUSHED_ANCESTOR":   {"visibility": "hidden", "has_visible_descendant": True},
    "FOLDER_CONTAINER_ONLY":    {"visibility": "hidden", "container_only": True},
}

# Generate folder state defs from formula
_FOLDER_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    name: derive_gradient(**inputs) for name, inputs in _FOLDER_STATE_INPUTS.items()
}

# File Gradient Framework (slim layout):
#   P1 = visibility   P2/P3 = background   P4 = config/status (pushed or warning)
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

# Folder states are derived via derive_gradient() — no lookup table needed.
# The _FOLDER_STATE_INPUTS dict above defines all known states declaratively.

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
    """Resolve a NodeState to a display state name.

    Folders: resolved via _resolve_folder_state() if/elif chain.
    Files: lookup table (FILE_STATE_TABLE).

    Args:
        node_state: A core.node_state.NodeState instance.
        is_folder: True for folder nodes, False for file nodes.
        virtual_type: For virtual nodes — "mirrored", "volume", or "auth".

    Returns:
        State name string (e.g. "FOLDER_MOUNTED", "FILE_PUSHED").
    """
    if is_folder:
        return _resolve_folder_state(node_state, virtual_type)

    # File path — FILE_STATE_TABLE lookup (folders use formula)
    host_orphaned = getattr(node_state, "host_orphaned", False)
    condition = (
        node_state.visibility,
        node_state.pushed,
        host_orphaned,
    )
    for key, state_name in FILE_STATE_TABLE.items():
        if _match_key(condition, key):
            return state_name
    return "FILE_HIDDEN"


def _resolve_folder_state(node_state, virtual_type: str = "mirrored") -> str:
    """Derive folder state name directly from NodeState properties.

    Uses the same logic as derive_gradient() to determine the state name
    without gradient comparison — O(1) per node.
    """
    vis = node_state.visibility
    has_vis_desc = (node_state.has_pushed_descendant or
                    node_state.has_direct_visible_child)

    if node_state.container_only:
        return "FOLDER_CONTAINER_ONLY"
    if vis == "virtual":
        if virtual_type == "volume":
            return "FOLDER_VIRTUAL_VOLUME"
        if virtual_type == "auth":
            return "FOLDER_VIRTUAL_AUTH"
        if has_vis_desc:
            return "FOLDER_MIRRORED_REVEALED"
        return "FOLDER_MIRRORED"
    if vis in ("visible", "revealed"):
        if node_state.revealed:
            return "FOLDER_REVEALED"
        if node_state.is_mount_root:
            if has_vis_desc:
                return "FOLDER_MOUNTED_REVEALED"
            return "FOLDER_MOUNTED"
        return "FOLDER_VISIBLE"
    if vis == "masked":
        return "FOLDER_MASKED"
    # hidden or unknown
    if has_vis_desc:
        return "FOLDER_PUSHED_ANCESTOR"
    return "FOLDER_HIDDEN"


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
