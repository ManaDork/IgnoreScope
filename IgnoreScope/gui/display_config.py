"""TreeDisplayConfig Base + Subclasses.

TreeDisplayConfig base class with LocalHostDisplayConfig and
ScopeDisplayConfig subclasses. Receives pre-resolved color/font dicts
from the consolidated ``*_theme.json`` via StyleGui. Contains
``state_styles: dict[str, StateStyleClass]`` for display state name -> visual
lookup, ``columns: list[ColumnDef]``, and content filter booleans.
Folder states derived via ``derive_gradient()`` formula.
File states derived via ``derive_file_style()`` formula.
Does NOT store state, render UI, or interact with CORE.
"""

from __future__ import annotations

from dataclasses import dataclass

from .style_engine import FontStyleClass, GradientClass, StateStyleClass, StyleGui


# ------------------------------------------------------------------
# ColumnDef
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnDef:
    """Definition for one tree column (per GUI_LAYOUT_SPECS Section 10B)."""

    header: str
    visible: bool = True
    width: int | str = "stretch"


# ------------------------------------------------------------------
# State definition tuples: (GradientClass, font_var_name)
# GradientClass args are variable names from tree_state_style.json
# font_var_name resolves via tree_state_font.json
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Folder Gradient Formula
#   P1 = visibility (what container sees)
#   P2 = context (parent/inherited visibility)
#   P3 = ancestor (descendant tracking) — falls to P4, then to P1 when absent
#   P4 = config||inherited (direct/inherited action) — falls to P1 when absent
# ------------------------------------------------------------------

_P2_MAP = {"accessible": "accessible", "restricted": "restricted", "virtual": "virtual"}


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

    visibility is pure STATE: "accessible", "restricted", or "virtual".
    METHOD flags (is_masked, is_revealed, etc.) drive P3/P4 accents.

    Returns:
        (GradientClass, font_var_name) tuple for StateStyleClass construction.
    """
    # P1: pure state — direct 1:1 to visibility.* JSON key
    is_virtual = (visibility == "virtual")
    p1 = visibility

    # P2: parent context — REVEALED gets P2=restricted (accessible in restricted context)
    if p1 == "accessible" and is_revealed:
        p2 = "restricted"
    else:
        p2 = _P2_MAP.get(p1, "restricted")

    # P4: config/inherited action — full color variable name
    if is_mount_root:
        p4_var = "config.mount"
    elif is_revealed:
        p4_var = "config.revealed"
    elif is_masked:
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
    elif p1 == "restricted" and not has_visible_descendant:
        font = "muted"
    else:
        font = "default"

    return GradientClass(p1_var, p2_var, p3_var, p4_var), font


# Folder state inputs — declarative tuples fed to derive_gradient() at init
# visibility is pure STATE (accessible/restricted/virtual), METHOD on flags
_FOLDER_STATE_INPUTS: dict[str, dict] = {
    "FOLDER_HIDDEN":            {"visibility": "restricted"},
    "FOLDER_VISIBLE":           {"visibility": "accessible"},
    "FOLDER_MOUNTED":           {"visibility": "accessible", "is_mount_root": True},
    "FOLDER_MOUNTED_REVEALED":  {"visibility": "accessible", "is_mount_root": True, "has_visible_descendant": True},
    "FOLDER_MASKED":            {"visibility": "restricted", "is_masked": True},
    "FOLDER_MASKED_REVEALED":   {"visibility": "virtual", "is_masked": True, "has_visible_descendant": True},
    "FOLDER_MASKED_MIRRORED":   {"visibility": "virtual", "is_masked": True},
    "FOLDER_REVEALED":          {"visibility": "accessible", "is_revealed": True},
    "FOLDER_MIRRORED":          {"visibility": "virtual"},
    "FOLDER_MIRRORED_REVEALED": {"visibility": "virtual", "has_visible_descendant": True},
    "FOLDER_VIRTUAL_VOLUME":    {"visibility": "virtual", "virtual_type": "volume"},
    "FOLDER_VIRTUAL_AUTH":      {"visibility": "virtual", "virtual_type": "auth"},
    "FOLDER_PUSHED_ANCESTOR":   {"visibility": "restricted", "has_visible_descendant": True},
    "FOLDER_CONTAINER_ONLY":    {"visibility": "virtual", "container_only": True},
}

# Generate folder state defs from formula
_FOLDER_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    name: derive_gradient(**inputs) for name, inputs in _FOLDER_STATE_INPUTS.items()
}

# ------------------------------------------------------------------
# File Style Formula
#   P1 = visibility   P2/P3 = background (no ancestor tracking)
#   P4 = config/status (pushed or warning)
# ------------------------------------------------------------------


def derive_file_style(
    visibility: str,
    is_pushed: bool = False,
    container_orphaned: bool = False,
    container_only: bool = False,
) -> tuple[Optional[GradientClass], str]:
    """Derive file gradient + font key from node properties.

    Parallel to derive_gradient() for folders. Files use a simplified
    gradient model: P1 = visibility, P2/P3 = background (no descendant
    tracking), P4 = config overlay.

    Returns:
        (GradientClass | None, font_var_name) tuple for StateStyleClass
        construction. FILE_HOST_ORPHAN returns (None, "italic") — gradient
        deferred until core orphan detection lands.
    """
    # Host orphan: gradient deferred (None)
    if visibility == "orphaned":
        return None, "italic"

    # P1: pure state — direct 1:1 to visibility.* JSON key
    p1_var = f"visibility.{visibility}"

    # P2/P3: always restricted (files have no ancestor tracking)
    bg_var = "visibility.restricted"

    # P4: config overlay — pushed accent or warning, else falls to bg
    if is_pushed:
        p4_var = "config.pushed"
    elif container_orphaned:
        p4_var = "status.warning"
    else:
        p4_var = bg_var

    # Font derivation
    if container_only or container_orphaned:
        font = "italic"
    elif visibility == "restricted" and not is_pushed:
        font = "muted"
    else:
        font = "default"

    return GradientClass(p1_var, bg_var, bg_var, p4_var), font


# File state inputs — declarative dicts fed to derive_file_style() at init
_FILE_STYLE_INPUTS: dict[str, dict] = {
    "FILE_HIDDEN":           {"visibility": "restricted"},
    "FILE_VISIBLE":          {"visibility": "accessible"},
    "FILE_MASKED":           {"visibility": "restricted"},
    "FILE_REVEALED":         {"visibility": "accessible"},
    "FILE_PUSHED":           {"visibility": "restricted", "is_pushed": True},
    "FILE_HOST_ORPHAN":      {"visibility": "orphaned"},
    "FILE_CONTAINER_ORPHAN": {"visibility": "restricted", "container_orphaned": True},
    "FILE_CONTAINER_ONLY":   {"visibility": "virtual", "container_only": True},
}

# Generate file state defs from formula
_FILE_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    name: derive_file_style(**inputs) for name, inputs in _FILE_STYLE_INPUTS.items()
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

def resolve_tree_state(node_state, is_folder: bool, virtual_type: str = "mirrored") -> str:
    """Resolve a NodeState to a display state name.

    Both folders and files use if/elif resolution against pure STATE
    visibility + METHOD boolean flags from NodeState.

    Args:
        node_state: A core.node_state.NodeState instance.
        is_folder: True for folder nodes, False for file nodes.
        virtual_type: For virtual nodes — "mirrored", "volume", or "auth".

    Returns:
        State name string (e.g. "FOLDER_MOUNTED", "FILE_PUSHED").
    """
    if is_folder:
        return _resolve_folder_state(node_state, virtual_type)
    return _resolve_file_state(node_state)


def _resolve_file_state(node_state) -> str:
    """Derive file state name from NodeState properties."""
    vis = node_state.visibility
    if node_state.container_only:
        return "FILE_CONTAINER_ONLY"
    if node_state.container_orphaned:
        return "FILE_CONTAINER_ORPHAN"
    if vis == "accessible":
        if node_state.revealed:
            return "FILE_REVEALED"
        return "FILE_VISIBLE"
    # restricted or virtual (files shouldn't be virtual, but fallback)
    host_orphaned = getattr(node_state, "host_orphaned", False)
    if node_state.pushed:
        if host_orphaned:
            return "FILE_HOST_ORPHAN"
        return "FILE_PUSHED"
    if node_state.masked:
        return "FILE_MASKED"
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
        if node_state.masked:
            if has_vis_desc:
                return "FOLDER_MASKED_REVEALED"
            return "FOLDER_MASKED_MIRRORED"
        if has_vis_desc:
            return "FOLDER_MIRRORED_REVEALED"
        return "FOLDER_MIRRORED"
    if vis == "accessible":
        if node_state.revealed:
            return "FOLDER_REVEALED"
        if node_state.is_mount_root:
            if has_vis_desc:
                return "FOLDER_MOUNTED_REVEALED"
            return "FOLDER_MOUNTED"
        return "FOLDER_VISIBLE"
    # restricted or unknown
    if node_state.masked:
        return "FOLDER_MASKED"
    if has_vis_desc:
        return "FOLDER_PUSHED_ANCESTOR"
    return "FOLDER_HIDDEN"


# ------------------------------------------------------------------
# TreeDisplayConfig base class
# ------------------------------------------------------------------

class BaseDisplayConfig:
    """Shared display configuration base for tree and list panels.

    Receives pre-resolved color/font/text dicts from the consolidated
    theme. Builds state_styles dict from a caller-provided state
    definitions dictionary.
    """

    def __init__(
        self,
        state_defs: dict[str, tuple[Optional[GradientClass], str]],
        color_vars: dict[str, str],
        font_vars: dict[str, dict],
        text_colors: dict[str, str],
    ):
        self._color_vars = color_vars
        self._font_vars = font_vars

        # Apply text colors as instance attributes (replaces theme.json loading)
        for attr, value in text_colors.items():
            setattr(self, attr, value)

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

    Receives panel-specific resolved dicts from the consolidated theme.
    Panel identity ("local_host" or "scope") determines which state_colors
    and fonts section is used. Scope inherits from local_host via deep-merge.
    """

    def __init__(self, panel: str = "local_host"):
        sg = StyleGui.instance()
        theme = sg._theme_data
        if panel == "scope":
            resolved = theme["_scope_resolved"]
        else:
            resolved = theme["local_host"]

        super().__init__(
            _TREE_STATE_DEFS,
            color_vars=resolved["state_colors"],
            font_vars=resolved["fonts"],
            text_colors=theme["base"]["text"],
        )

        # Delegate overlay values from theme
        delegate = theme["base"]["delegate"]
        self.hover_color: str = delegate["hover_color"]
        self.hover_alpha: int = delegate["hover_alpha"]
        self.selection_alpha: int = delegate["selection_alpha"]

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

    def __init__(self):
        super().__init__(panel="local_host")
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

    def __init__(self):
        super().__init__(panel="scope")
        self.columns = [
            ColumnDef(
                header="Container Scope",
                width="stretch",
            ),
        ]
