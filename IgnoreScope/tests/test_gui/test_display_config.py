"""Tests for display_config.py and list_display_config.py.

Covers truth table resolution, state_styles dict, JSON loading,
subclass configs, and ListDisplayConfig.
"""

import pytest

from IgnoreScope.core.node_state import NodeState
from IgnoreScope.gui.style_engine import (
    GradientClass,
    FontStyleClass,
    StateStyleClass,
    StyleGui,
)
from IgnoreScope.gui.display_config import (
    ColumnDef,
    TreeDisplayConfig,
    LocalHostDisplayConfig,
    ScopeDisplayConfig,
    resolve_tree_state,
    derive_gradient,
    derive_file_style,
    _FILE_STYLE_INPUTS,
)
from IgnoreScope.gui.list_display_config import ListDisplayConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset StyleGui singleton between tests."""
    StyleGui._reset()
    yield
    StyleGui._reset()


# ===========================================================================
# Truth Table Resolution — Folders
# ===========================================================================

class TestFolderTruthTable:
    """Folder states resolve correctly from NodeState fields."""

    def test_folder_hidden(self):
        ns = NodeState(visibility="restricted")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_HIDDEN"

    def test_folder_visible(self):
        ns = NodeState(visibility="accessible")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_VISIBLE"

    def test_folder_mounted(self):
        """Mount root → FOLDER_MOUNTED (config.mount accent)."""
        ns = NodeState(visibility="accessible", is_mount_root=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED"

    def test_folder_mounted_revealed(self):
        """Mount root with visible descendants → FOLDER_MOUNTED_REVEALED."""
        ns = NodeState(visibility="accessible", is_mount_root=True,
                       has_direct_visible_child=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED_REVEALED"

    def test_folder_mounted_with_pushed_descendant(self):
        """Mount root with pushed descendant → FOLDER_MOUNTED_REVEALED (unified)."""
        ns = NodeState(visibility="accessible", is_mount_root=True,
                       has_pushed_descendant=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED_REVEALED"

    def test_folder_masked(self):
        """Under mount, denied by pattern → FOLDER_MASKED."""
        ns = NodeState(visibility="restricted", masked=True, mounted=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MASKED"

    def test_folder_mirrored_revealed(self):
        """Structural path with visible descendant."""
        ns = NodeState(visibility="virtual", has_direct_visible_child=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MIRRORED_REVEALED"

    def test_folder_mirrored(self):
        """Structural path, no direct visible child."""
        ns = NodeState(visibility="virtual", has_direct_visible_child=False)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MIRRORED"

    def test_folder_stencil_volume(self):
        """Non-filesystem volume entry."""
        ns = NodeState(visibility="virtual")
        assert resolve_tree_state(ns, is_folder=True, stencil_tier="volume") == "FOLDER_STENCIL_VOLUME"

    def test_folder_stencil_auth(self):
        """Non-filesystem auth volume entry."""
        ns = NodeState(visibility="virtual")
        assert resolve_tree_state(ns, is_folder=True, stencil_tier="auth") == "FOLDER_STENCIL_AUTH"

    def test_folder_pushed_ancestor(self):
        ns = NodeState(visibility="restricted", has_pushed_descendant=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_PUSHED_ANCESTOR"

    def test_folder_revealed(self):
        ns = NodeState(visibility="accessible", revealed=True, masked=False, mounted=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_REVEALED"

    def test_folder_masked_revealed(self):
        """Masked folder upgraded to virtual with revealed/pushed child -> F5."""
        ns = NodeState(visibility="virtual", masked=True, mounted=True,
                       has_direct_visible_child=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MASKED_REVEALED"

    def test_folder_masked_mirrored(self):
        """Masked folder upgraded to virtual, no direct visible child -> F6."""
        ns = NodeState(visibility="virtual", masked=True, mounted=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MASKED_MIRRORED"

    def test_folder_masked_revealed_with_pushed_descendant(self):
        """Masked folder virtual with pushed descendant -> F5."""
        ns = NodeState(visibility="virtual", masked=True, mounted=True,
                       has_pushed_descendant=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MASKED_REVEALED"

    def test_folder_stencil_volume_not_affected_by_masked(self):
        """Volume stencil tier takes priority over masked flag."""
        ns = NodeState(visibility="virtual", masked=True)
        assert resolve_tree_state(ns, is_folder=True, stencil_tier="volume") == "FOLDER_STENCIL_VOLUME"

    def test_folder_stencil_auth_not_affected_by_masked(self):
        """Auth stencil tier takes priority over masked flag."""
        ns = NodeState(visibility="virtual", masked=True)
        assert resolve_tree_state(ns, is_folder=True, stencil_tier="auth") == "FOLDER_STENCIL_AUTH"

    def test_folder_container_only(self):
        ns = NodeState(visibility="virtual", container_only=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_CONTAINER_ONLY"

    def test_folder_unknown_visibility_fallback(self):
        """Unknown visibility falls back to FOLDER_HIDDEN."""
        ns = NodeState(visibility="bogus")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_HIDDEN"


# ===========================================================================
# Truth Table Resolution — Files
# ===========================================================================

class TestFileTruthTable:
    """File states resolve correctly from NodeState fields."""

    def test_file_hidden(self):
        ns = NodeState(visibility="restricted", pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_HIDDEN"

    def test_file_visible(self):
        ns = NodeState(visibility="accessible", pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_VISIBLE"

    def test_file_masked(self):
        ns = NodeState(visibility="restricted", masked=True, mounted=True, pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_MASKED"

    def test_file_revealed(self):
        ns = NodeState(visibility="accessible", revealed=True, masked=False, mounted=True, pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_REVEALED"

    def test_file_pushed(self):
        ns = NodeState(visibility="restricted", masked=True, mounted=True, pushed=True)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_PUSHED"

    def test_file_host_orphan(self):
        """FILE_HOST_ORPHAN requires host_orphaned=True (via getattr)."""
        ns = NodeState(visibility="restricted", masked=True, mounted=True, pushed=True)
        ns_with_attr = type("NS", (), {**ns.__dict__, "host_orphaned": True})()
        assert resolve_tree_state(ns_with_attr, is_folder=False) == "FILE_HOST_ORPHAN"

    def test_file_container_orphan(self):
        ns = NodeState(visibility="restricted", pushed=True, container_orphaned=True)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_CONTAINER_ORPHAN"

    def test_file_unknown_visibility_fallback(self):
        """Unknown visibility falls back to FILE_HIDDEN."""
        ns = NodeState(visibility="bogus", pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_HIDDEN"


# ===========================================================================
# State Styles Dict
# ===========================================================================

class TestStateStylesDict:
    """Verify state_styles dict built from JSON + defs."""

    @pytest.fixture
    def config(self):
        return TreeDisplayConfig()

    def test_all_states_present(self, config):
        expected = {
            "FOLDER_HIDDEN", "FOLDER_VISIBLE",
            "FOLDER_MOUNTED", "FOLDER_MOUNTED_REVEALED",
            "FOLDER_MASKED",
            "FOLDER_MASKED_REVEALED", "FOLDER_MASKED_MIRRORED",
            "FOLDER_MIRRORED_REVEALED", "FOLDER_MIRRORED",
            "FOLDER_STENCIL_VOLUME", "FOLDER_STENCIL_AUTH",
            "FOLDER_REVEALED", "FOLDER_PUSHED_ANCESTOR",
            "FOLDER_CONTAINER_ONLY",
            "FILE_HIDDEN", "FILE_VISIBLE", "FILE_MASKED",
            "FILE_REVEALED", "FILE_PUSHED",
            "FILE_HOST_ORPHAN", "FILE_CONTAINER_ORPHAN",
            "FILE_CONTAINER_ONLY",
        }
        assert set(config.state_styles.keys()) == expected

    def test_folder_hidden_gradient_vars(self, config):
        """FOLDER_HIDDEN: all 4 positions are visibility.restricted."""
        style = config.state_styles["FOLDER_HIDDEN"]
        g = style.gradient
        assert g.pos1 == "visibility.restricted"
        assert g.pos4 == "visibility.restricted"

    def test_folder_mounted_gradient(self, config):
        """FOLDER_MOUNTED: vis.accessible left, config.mount right."""
        style = config.state_styles["FOLDER_MOUNTED"]
        g = style.gradient
        assert g.pos1 == "visibility.accessible"
        assert g.pos3 == "config.mount"
        assert g.pos4 == "config.mount"

    def test_folder_mounted_revealed_gradient(self, config):
        """FOLDER_MOUNTED_REVEALED: vis.accessible left, ancestor.visible + config.mount right."""
        style = config.state_styles["FOLDER_MOUNTED_REVEALED"]
        g = style.gradient
        assert g.pos1 == "visibility.accessible"
        assert g.pos3 == "ancestor.visible"
        assert g.pos4 == "config.mount"

    def test_folder_masked_gradient(self, config):
        """FOLDER_MASKED: vis.restricted left, inherited.masked right."""
        style = config.state_styles["FOLDER_MASKED"]
        g = style.gradient
        assert g.pos1 == "visibility.restricted"
        assert g.pos3 == "inherited.masked"

    def test_folder_masked_revealed_gradient(self, config):
        """F5: vis.virtual left, ancestor.visible + inherited.masked right."""
        style = config.state_styles["FOLDER_MASKED_REVEALED"]
        g = style.gradient
        assert (g.pos1, g.pos2, g.pos3, g.pos4) == (
            "visibility.virtual", "visibility.virtual",
            "ancestor.visible", "inherited.masked",
        )

    def test_folder_masked_mirrored_gradient(self, config):
        """F6: vis.virtual left, inherited.masked right (no descendant)."""
        style = config.state_styles["FOLDER_MASKED_MIRRORED"]
        g = style.gradient
        assert (g.pos1, g.pos2, g.pos3, g.pos4) == (
            "visibility.virtual", "visibility.virtual",
            "inherited.masked", "inherited.masked",
        )

    def test_folder_masked_revealed_font(self, config):
        """F5: default font (not muted, not stencil_mirrored)."""
        style = config.state_styles["FOLDER_MASKED_REVEALED"]
        assert style.font.text_color_var == "text_primary"
        assert style.font.italic is False

    def test_folder_masked_mirrored_font(self, config):
        """F6: default font (not muted, not stencil_mirrored)."""
        style = config.state_styles["FOLDER_MASKED_MIRRORED"]
        assert style.font.text_color_var == "text_primary"
        assert style.font.italic is False

    def test_folder_revealed_gradient(self, config):
        """FOLDER_REVEALED: P2=restricted (accessible in restricted context)."""
        style = config.state_styles["FOLDER_REVEALED"]
        g = style.gradient
        assert g.pos1 == "visibility.accessible"
        assert g.pos2 == "visibility.restricted"
        assert g.pos3 == "config.revealed"

    def test_folder_mirrored_font(self, config):
        """FOLDER_MIRRORED: stencil_mirrored font (text_primary)."""
        style = config.state_styles["FOLDER_MIRRORED"]
        assert style.font.text_color_var == "text_primary"

    def test_folder_stencil_volume_font(self, config):
        """FOLDER_STENCIL_VOLUME: purple text."""
        style = config.state_styles["FOLDER_STENCIL_VOLUME"]
        assert style.font.text_color_var == "text_stencil_purple"
        assert style.font.italic is True

    def test_folder_pushed_ancestor_gradient(self, config):
        """FOLDER_PUSHED_ANCESTOR: ancestor.pushed on right."""
        style = config.state_styles["FOLDER_PUSHED_ANCESTOR"]
        g = style.gradient
        assert g.pos3 == "ancestor.visible"

    def test_file_pushed_gradient(self, config):
        """FILE_PUSHED: config.pushed in P4."""
        style = config.state_styles["FILE_PUSHED"]
        g = style.gradient
        assert g.pos4 == "config.pushed"

    def test_file_host_orphan_deferred(self, config):
        """FILE_HOST_ORPHAN: gradient is None (DEFERRED)."""
        style = config.state_styles["FILE_HOST_ORPHAN"]
        assert style.gradient is None

    def test_file_container_orphan_font(self, config):
        """FILE_CONTAINER_ORPHAN: italic font with text_warning."""
        style = config.state_styles["FILE_CONTAINER_ORPHAN"]
        assert style.font.italic is True
        assert style.font.text_color_var == "text_warning"


# ===========================================================================
# derive_file_style() — Formulaic File State Derivation
# ===========================================================================

class TestDeriveFileStyle:
    """Verify derive_file_style() produces correct (GradientClass, font) tuples."""

    @pytest.mark.parametrize("state_name,expected_grad,expected_font", [
        ("FILE_HIDDEN",
         ("visibility.restricted", "visibility.restricted", "visibility.restricted", "visibility.restricted"),
         "muted"),
        ("FILE_VISIBLE",
         ("visibility.accessible", "visibility.restricted", "visibility.restricted", "visibility.restricted"),
         "default"),
        ("FILE_MASKED",
         ("visibility.restricted", "visibility.restricted", "visibility.restricted", "visibility.restricted"),
         "muted"),
        ("FILE_REVEALED",
         ("visibility.accessible", "visibility.restricted", "visibility.restricted", "visibility.restricted"),
         "default"),
        ("FILE_PUSHED",
         ("visibility.restricted", "visibility.restricted", "visibility.restricted", "config.pushed"),
         "default"),
        ("FILE_HOST_ORPHAN", None, "italic"),
        ("FILE_CONTAINER_ORPHAN",
         ("visibility.restricted", "visibility.restricted", "visibility.restricted", "status.warning"),
         "italic"),
        ("FILE_CONTAINER_ONLY",
         ("visibility.virtual", "visibility.restricted", "visibility.restricted", "visibility.restricted"),
         "italic"),
    ])
    def test_derive_file_style_all_states(self, state_name, expected_grad, expected_font):
        """Each file state input produces the expected gradient + font."""
        inputs = _FILE_STYLE_INPUTS[state_name]
        grad, font = derive_file_style(**inputs)
        if expected_grad is None:
            assert grad is None
        else:
            assert (grad.pos1, grad.pos2, grad.pos3, grad.pos4) == expected_grad
        assert font == expected_font

    def test_derive_file_style_host_orphan_deferred(self):
        """FILE_HOST_ORPHAN returns (None, 'italic') — gradient deferred."""
        grad, font = derive_file_style(visibility="orphaned")
        assert grad is None
        assert font == "italic"

    def test_derive_file_style_pushed_overrides_muted(self):
        """Pushed file gets 'default' font, not 'muted', even though restricted."""
        grad, font = derive_file_style(visibility="restricted", is_pushed=True)
        assert font == "default"
        assert grad.pos4 == "config.pushed"

    def test_derive_file_style_p2_p3_always_restricted(self):
        """Files never use ancestor tracking — P2/P3 always visibility.restricted."""
        for inputs in _FILE_STYLE_INPUTS.values():
            grad, _ = derive_file_style(**inputs)
            if grad is not None:
                assert grad.pos2 == "visibility.restricted"
                assert grad.pos3 == "visibility.restricted"

    def test_pushed_font_keys_exist(self):
        """pushed_sync and pushed_nosync exist in font vars (unused placeholders)."""
        config = TreeDisplayConfig()
        assert "pushed_sync" in config._font_vars
        assert "pushed_nosync" in config._font_vars

    def test_pushed_text_color_vars_resolve(self):
        """Pushed text color placeholders resolve to hex strings."""
        config = TreeDisplayConfig()
        assert isinstance(config.text_pushed_sync, str)
        assert config.text_pushed_sync.startswith("#")
        assert isinstance(config.text_pushed_nosync, str)
        assert config.text_pushed_nosync.startswith("#")


# ===========================================================================
# JSON Loading
# ===========================================================================

class TestJsonLoading:
    """Verify JSON files load correctly."""

    @pytest.fixture
    def config(self):
        return TreeDisplayConfig()

    def test_color_vars_has_categorical_keys(self, config):
        """tree_state_style.json uses categorical naming."""
        keys = set(config.color_vars.keys())
        assert "visibility.accessible" in keys
        assert "visibility.restricted" in keys
        assert "visibility.virtual" in keys
        assert "config.masked" in keys
        assert "inherited.masked" in keys
        assert "ancestor.visible" in keys

    def test_color_vars_no_old_flat_keys(self, config):
        """Old flat names are gone."""
        keys = set(config.color_vars.keys())
        for old_key in ("background", "visible", "hidden", "masked", "revealed",
                        "mounted", "pushed", "stencil", "warning", "selected"):
            assert old_key not in keys, f"Old key '{old_key}' still present"

    def test_font_vars_count(self, config):
        """tree_state_font.json has 8 entries (6 active + 2 pushed placeholders)."""
        assert len(config._font_vars) == 8

    def test_font_vars_keys(self, config):
        assert set(config._font_vars.keys()) == {
            "default", "muted", "italic",
            "stencil_mirrored", "stencil_volume", "stencil_auth",
            "pushed_sync", "pushed_nosync",
        }

    def test_resolve_text_color_primary(self, config):
        font = FontStyleClass(text_color_var="text_primary")
        assert config.resolve_text_color(font) == "#E8DEFF"

    def test_resolve_text_color_dim(self, config):
        font = FontStyleClass(text_color_var="text_dim")
        assert config.resolve_text_color(font) == "#A89BC8"

    def test_resolve_text_color_purple(self, config):
        font = FontStyleClass(text_color_var="text_stencil_purple")
        assert config.resolve_text_color(font) == "#9040B0"

    def test_resolve_text_color_unknown_fallback(self, config):
        """Unknown var falls back to text_primary."""
        font = FontStyleClass(text_color_var="nonexistent_var")
        assert config.resolve_text_color(font) == "#E8DEFF"


# ===========================================================================
# Subclass Configs
# ===========================================================================

class TestLocalHostDisplayConfig:
    """Verify LocalHostDisplayConfig columns and filters."""

    @pytest.fixture
    def config(self):
        return LocalHostDisplayConfig()

    def test_column_count(self, config):
        assert len(config.columns) == 1

    def test_column_headers(self, config):
        headers = [c.header for c in config.columns]
        assert headers == ["Local Host"]

    def test_filters(self, config):
        assert config.display_files is True
        assert config.display_hidden is True
        assert config.display_non_mounted is True
        assert config.display_masked_dead_branches is True
        assert config.display_stencil_nodes is False
        assert config.display_orphaned is True

    def test_undo_scope(self, config):
        assert config.undo_scope == "full"


class TestScopeDisplayConfig:
    """Verify ScopeDisplayConfig columns and filters."""

    @pytest.fixture
    def config(self):
        return ScopeDisplayConfig()

    def test_column_count(self, config):
        assert len(config.columns) == 1

    def test_column_headers(self, config):
        headers = [c.header for c in config.columns]
        assert headers == ["Container Scope"]

    def test_filters(self, config):
        assert config.display_files is True
        assert config.display_hidden is False
        assert config.display_non_mounted is False
        assert config.display_masked_dead_branches is False
        assert config.display_stencil_nodes is True
        assert config.display_orphaned is True

    def test_undo_scope(self, config):
        assert config.undo_scope == "selection_history"


# ===========================================================================
# ListDisplayConfig
# ===========================================================================

class TestListDisplayConfig:
    """Verify ListDisplayConfig state_styles and JSON loading."""

    @pytest.fixture
    def config(self):
        return ListDisplayConfig()

    def test_all_5_history_states_present(self, config):
        expected = {
            "HISTORY_NORMAL",
            "HISTORY_UNDO_CURRENT",
            "HISTORY_REDO_AVAILABLE",
            "HISTORY_DESTRUCTIVE",
            "HISTORY_DESTRUCTIVE_SELECTED",
        }
        assert set(config.state_styles.keys()) == expected

    def test_color_vars_count(self, config):
        """list_style.json has 4 entries."""
        assert len(config.color_vars) == 4

    def test_color_vars_keys(self, config):
        assert set(config.color_vars.keys()) == {
            "background", "selected", "warning", "destructive",
        }

    def test_font_vars_count(self, config):
        assert len(config._font_vars) == 1

    def test_history_normal_gradient(self, config):
        style = config.state_styles["HISTORY_NORMAL"]
        g = style.gradient
        assert (g.pos1, g.pos2, g.pos3, g.pos4) == (
            "background", "background", "background", "background"
        )

    def test_history_destructive_selected_gradient(self, config):
        style = config.state_styles["HISTORY_DESTRUCTIVE_SELECTED"]
        g = style.gradient
        assert (g.pos1, g.pos2, g.pos3, g.pos4) == (
            "selected", "background", "destructive", "destructive"
        )

    def test_resolve_text_color(self, config):
        font = FontStyleClass(text_color_var="text_primary")
        assert config.resolve_text_color(font) == "#E8DEFF"


# ===========================================================================
# Consolidated Theme — Per-Panel Identity
# ===========================================================================

class TestPerPanelIdentity:
    """Verify TreeDisplayConfig panel identity and scope deep-merge."""

    def test_local_host_panel_default(self):
        """TreeDisplayConfig defaults to local_host panel."""
        config = TreeDisplayConfig()
        sg = StyleGui.instance()
        local_colors = sg._theme_data["local_host"]["state_colors"]
        assert config.color_vars == local_colors

    def test_scope_panel_uses_resolved_colors(self):
        """Scope panel uses _scope_resolved (deep-merged) colors."""
        config = TreeDisplayConfig(panel="scope")
        sg = StyleGui.instance()
        resolved_colors = sg._theme_data["_scope_resolved"]["state_colors"]
        assert config.color_vars == resolved_colors
        # Scope should differ from local_host when scope overrides are present
        local_colors = sg._theme_data["local_host"]["state_colors"]
        assert config.color_vars != local_colors

    def test_scope_display_config_uses_scope_panel(self):
        """ScopeDisplayConfig passes panel='scope'."""
        config = ScopeDisplayConfig()
        sg = StyleGui.instance()
        resolved = sg._theme_data["_scope_resolved"]["state_colors"]
        assert config.color_vars == resolved

    def test_delegate_values_from_theme(self):
        """hover_color, hover_alpha, selection_alpha come from theme delegate."""
        config = TreeDisplayConfig()
        sg = StyleGui.instance()
        delegate = sg._theme_data["base"]["delegate"]
        assert config.hover_color == delegate["hover_color"]
        assert config.hover_alpha == delegate["hover_alpha"]
        assert config.selection_alpha == delegate["selection_alpha"]

    def test_no_hex_class_defaults(self):
        """TreeDisplayConfig has no class-level hex defaults."""
        # These used to be class-level attributes — now injected from theme
        config = TreeDisplayConfig()
        assert hasattr(config, "text_primary")
        assert hasattr(config, "text_dim")
        assert hasattr(config, "hover_color")
        # All should be strings starting with #
        assert config.text_primary.startswith("#")
        assert config.text_dim.startswith("#")
        assert config.hover_color.startswith("#")
