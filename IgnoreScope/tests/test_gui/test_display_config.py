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
)
from IgnoreScope.gui.display_config import (
    ColumnDef,
    TreeDisplayConfig,
    LocalHostDisplayConfig,
    ScopeDisplayConfig,
    resolve_tree_state,
    derive_gradient,
    FILE_STATE_TABLE,
)
from IgnoreScope.gui.list_display_config import ListDisplayConfig


# ===========================================================================
# Truth Table Resolution — Folders
# ===========================================================================

class TestFolderTruthTable:
    """Folder states resolve correctly from NodeState fields."""

    def test_folder_hidden(self):
        ns = NodeState(visibility="hidden")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_HIDDEN"

    def test_folder_visible(self):
        ns = NodeState(visibility="visible")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_VISIBLE"

    def test_folder_mounted(self):
        """Mount root → FOLDER_MOUNTED (config.mount accent)."""
        ns = NodeState(visibility="visible", is_mount_root=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED"

    def test_folder_mounted_revealed(self):
        """Mount root with visible descendants → FOLDER_MOUNTED_REVEALED."""
        ns = NodeState(visibility="visible", is_mount_root=True,
                       has_direct_visible_child=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED_REVEALED"

    def test_folder_mounted_with_pushed_descendant(self):
        """Mount root with pushed descendant → FOLDER_MOUNTED_REVEALED (unified)."""
        ns = NodeState(visibility="visible", is_mount_root=True,
                       has_pushed_descendant=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED_REVEALED"

    def test_folder_masked(self):
        """Under mount, denied by pattern → FOLDER_MASKED."""
        ns = NodeState(visibility="masked", masked=True, mounted=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MASKED"

    def test_folder_mirrored_revealed(self):
        """Structural path with visible descendant."""
        ns = NodeState(visibility="virtual", has_direct_visible_child=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MIRRORED_REVEALED"

    def test_folder_mirrored(self):
        """Structural path, no direct visible child."""
        ns = NodeState(visibility="virtual", has_direct_visible_child=False)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MIRRORED"

    def test_folder_virtual_volume(self):
        """Non-filesystem volume entry."""
        ns = NodeState(visibility="virtual")
        assert resolve_tree_state(ns, is_folder=True, virtual_type="volume") == "FOLDER_VIRTUAL_VOLUME"

    def test_folder_virtual_auth(self):
        """Non-filesystem auth volume entry."""
        ns = NodeState(visibility="virtual")
        assert resolve_tree_state(ns, is_folder=True, virtual_type="auth") == "FOLDER_VIRTUAL_AUTH"

    def test_folder_pushed_ancestor(self):
        ns = NodeState(visibility="hidden", has_pushed_descendant=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_PUSHED_ANCESTOR"

    def test_folder_revealed(self):
        ns = NodeState(visibility="revealed", revealed=True, masked=True, mounted=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_REVEALED"

    def test_folder_container_only(self):
        ns = NodeState(visibility="container_only", container_only=True)
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
        ns = NodeState(visibility="hidden", pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_HIDDEN"

    def test_file_visible(self):
        ns = NodeState(visibility="visible", pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_VISIBLE"

    def test_file_masked(self):
        ns = NodeState(visibility="masked", pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_MASKED"

    def test_file_revealed(self):
        ns = NodeState(visibility="revealed", pushed=False)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_REVEALED"

    def test_file_pushed(self):
        ns = NodeState(visibility="masked", pushed=True)
        assert resolve_tree_state(ns, is_folder=False) == "FILE_PUSHED"

    def test_file_host_orphan(self):
        """FILE_HOST_ORPHAN requires host_orphaned=True (via getattr)."""
        ns = NodeState(visibility="masked", pushed=True)
        ns_with_attr = type("NS", (), {**ns.__dict__, "host_orphaned": True})()
        assert resolve_tree_state(ns_with_attr, is_folder=False) == "FILE_HOST_ORPHAN"

    def test_file_container_orphan(self):
        ns = NodeState(visibility="orphaned", pushed=True, container_orphaned=True)
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
            "FOLDER_MIRRORED_REVEALED", "FOLDER_MIRRORED",
            "FOLDER_VIRTUAL_VOLUME", "FOLDER_VIRTUAL_AUTH",
            "FOLDER_REVEALED", "FOLDER_PUSHED_ANCESTOR",
            "FOLDER_CONTAINER_ONLY",
            "FILE_HIDDEN", "FILE_VISIBLE", "FILE_MASKED",
            "FILE_REVEALED", "FILE_PUSHED",
            "FILE_HOST_ORPHAN", "FILE_CONTAINER_ORPHAN",
            "FILE_CONTAINER_ONLY",
        }
        assert set(config.state_styles.keys()) == expected

    def test_folder_hidden_gradient_vars(self, config):
        """FOLDER_HIDDEN: all 4 positions are visibility.background."""
        style = config.state_styles["FOLDER_HIDDEN"]
        g = style.gradient
        assert g.pos1 == "visibility.background"
        assert g.pos4 == "visibility.background"

    def test_folder_mounted_gradient(self, config):
        """FOLDER_MOUNTED: vis.visible left, config.mount right."""
        style = config.state_styles["FOLDER_MOUNTED"]
        g = style.gradient
        assert g.pos1 == "visibility.visible"
        assert g.pos3 == "config.mount"
        assert g.pos4 == "config.mount"

    def test_folder_mounted_revealed_gradient(self, config):
        """FOLDER_MOUNTED_REVEALED: vis.visible left, ancestor.visible + config.mount right."""
        style = config.state_styles["FOLDER_MOUNTED_REVEALED"]
        g = style.gradient
        assert g.pos1 == "visibility.visible"
        assert g.pos3 == "ancestor.visible"
        assert g.pos4 == "config.mount"

    def test_folder_masked_gradient(self, config):
        """FOLDER_MASKED: vis.hidden left, inherited.masked right."""
        style = config.state_styles["FOLDER_MASKED"]
        g = style.gradient
        assert g.pos1 == "visibility.hidden"
        assert g.pos3 == "inherited.masked"

    def test_folder_revealed_gradient(self, config):
        """FOLDER_REVEALED: P2=hidden (visible in hidden context)."""
        style = config.state_styles["FOLDER_REVEALED"]
        g = style.gradient
        assert g.pos1 == "visibility.visible"
        assert g.pos2 == "visibility.hidden"
        assert g.pos3 == "config.revealed"

    def test_folder_mirrored_font(self, config):
        """FOLDER_MIRRORED: virtual_mirrored font (text_primary)."""
        style = config.state_styles["FOLDER_MIRRORED"]
        assert style.font.text_color_var == "text_primary"

    def test_folder_virtual_volume_font(self, config):
        """FOLDER_VIRTUAL_VOLUME: purple text."""
        style = config.state_styles["FOLDER_VIRTUAL_VOLUME"]
        assert style.font.text_color_var == "text_virtual_purple"
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
        assert "visibility.visible" in keys
        assert "config.masked" in keys
        assert "inherited.masked" in keys
        assert "ancestor.visible" in keys

    def test_color_vars_no_old_flat_keys(self, config):
        """Old flat names are gone."""
        keys = set(config.color_vars.keys())
        for old_key in ("background", "visible", "hidden", "masked", "revealed",
                        "mounted", "pushed", "virtual", "warning", "selected"):
            assert old_key not in keys, f"Old key '{old_key}' still present"

    def test_font_vars_count(self, config):
        """tree_state_font.json has 6 entries."""
        assert len(config._font_vars) == 6

    def test_font_vars_keys(self, config):
        assert set(config._font_vars.keys()) == {
            "default", "muted", "italic",
            "virtual_mirrored", "virtual_volume", "virtual_auth",
        }

    def test_resolve_text_color_primary(self, config):
        font = FontStyleClass(text_color_var="text_primary")
        assert config.resolve_text_color(font) == "#ECEFF4"

    def test_resolve_text_color_dim(self, config):
        font = FontStyleClass(text_color_var="text_dim")
        assert config.resolve_text_color(font) == "#616E88"

    def test_resolve_text_color_purple(self, config):
        font = FontStyleClass(text_color_var="text_virtual_purple")
        assert config.resolve_text_color(font) == "#B48EAD"

    def test_resolve_text_color_unknown_fallback(self, config):
        """Unknown var falls back to text_primary."""
        font = FontStyleClass(text_color_var="nonexistent_var")
        assert config.resolve_text_color(font) == "#ECEFF4"


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

    def test_column_0_not_checkable(self, config):
        assert config.columns[0].checkable is False

    def test_filters(self, config):
        assert config.display_files is True
        assert config.display_hidden is True
        assert config.display_non_mounted is True
        assert config.display_masked_dead_branches is True
        assert config.display_virtual_nodes is False
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
        assert config.display_virtual_nodes is True
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
        assert config.resolve_text_color(font) == "#ECEFF4"
