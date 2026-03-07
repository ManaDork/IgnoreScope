"""Tests for display_config.py and list_display_config.py.

Covers truth table resolution, state_styles dict, JSON loading,
subclass configs, and ListDisplayConfig.
"""

import pytest

from IgnoreScopeDocker.core.node_state import NodeState
from IgnoreScopeDocker.gui.style_engine import (
    GradientClass,
    FontStyleClass,
    StateStyleClass,
)
from IgnoreScopeDocker.gui.display_config import (
    ColumnDef,
    TreeDisplayConfig,
    LocalHostDisplayConfig,
    ScopeDisplayConfig,
    resolve_tree_state,
    FOLDER_STATE_TABLE,
    FILE_STATE_TABLE,
)
from IgnoreScopeDocker.gui.list_display_config import ListDisplayConfig


# ===========================================================================
# Truth Table Resolution
# ===========================================================================

class TestFolderTruthTable:
    """All 7 folder states resolve correctly from NodeState fields."""

    def test_folder_hidden(self):
        ns = NodeState(visibility="hidden")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_HIDDEN"

    def test_folder_visible(self):
        ns = NodeState(visibility="visible")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_VISIBLE"

    def test_folder_mounted_masked(self):
        ns = NodeState(visibility="masked", has_pushed_descendant=False)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED_MASKED"

    def test_folder_mounted_masked_pushed(self):
        ns = NodeState(visibility="masked", has_pushed_descendant=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MOUNTED_MASKED_PUSHED"

    def test_folder_masked_revealed(self):
        ns = NodeState(visibility="mirrored", has_direct_visible_child=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MASKED_REVEALED"

    def test_folder_masked_mirrored(self):
        ns = NodeState(visibility="mirrored", has_direct_visible_child=False)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_MASKED_MIRRORED"

    def test_folder_pushed_ancestor(self):
        ns = NodeState(visibility="hidden", has_pushed_descendant=True)
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_PUSHED_ANCESTOR"

    def test_folder_revealed(self):
        ns = NodeState(visibility="revealed")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_REVEALED"

    def test_folder_unknown_visibility_fallback(self):
        """Unknown visibility falls back to FOLDER_HIDDEN."""
        ns = NodeState(visibility="bogus")
        assert resolve_tree_state(ns, is_folder=True) == "FOLDER_HIDDEN"


class TestFileTruthTable:
    """All 7 file states resolve correctly from NodeState fields."""

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
        # Simulate host_orphaned attribute
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

    def test_all_15_states_present(self, config):
        expected = {
            "FOLDER_HIDDEN", "FOLDER_VISIBLE",
            "FOLDER_MOUNTED_MASKED", "FOLDER_MOUNTED_MASKED_PUSHED",
            "FOLDER_MASKED_REVEALED", "FOLDER_MASKED_MIRRORED",
            "FOLDER_REVEALED", "FOLDER_PUSHED_ANCESTOR",
            "FILE_HIDDEN", "FILE_VISIBLE", "FILE_MASKED",
            "FILE_REVEALED", "FILE_PUSHED",
            "FILE_HOST_ORPHAN", "FILE_CONTAINER_ORPHAN",
        }
        assert set(config.state_styles.keys()) == expected

    def test_folder_hidden_gradient_vars(self, config):
        """FOLDER_HIDDEN: all 4 positions are 'background'."""
        style = config.state_styles["FOLDER_HIDDEN"]
        g = style.gradient
        assert g.pos1 == "background"
        assert g.pos2 == "background"
        assert g.pos3 == "background"
        assert g.pos4 == "background"

    def test_folder_hidden_font(self, config):
        """FOLDER_HIDDEN: muted font."""
        style = config.state_styles["FOLDER_HIDDEN"]
        assert style.font.text_color_var == "text_dim"
        assert style.font.italic is False

    def test_folder_masked_revealed_gradient(self, config):
        """F5 user-confirmed: (masked, masked, hidden, revealed)."""
        style = config.state_styles["FOLDER_MASKED_REVEALED"]
        g = style.gradient
        assert (g.pos1, g.pos2, g.pos3, g.pos4) == (
            "masked", "masked", "hidden", "revealed"
        )

    def test_folder_pushed_ancestor_gradient(self, config):
        """F8: (background, background, background, pushed)."""
        style = config.state_styles["FOLDER_PUSHED_ANCESTOR"]
        g = style.gradient
        assert (g.pos1, g.pos2, g.pos3, g.pos4) == (
            "background", "background", "background", "pushed"
        )

    def test_file_pushed_gradient(self, config):
        """FILE_PUSHED: (pushed, pushed, hidden, hidden)."""
        style = config.state_styles["FILE_PUSHED"]
        g = style.gradient
        assert (g.pos1, g.pos2, g.pos3, g.pos4) == (
            "pushed", "pushed", "hidden", "hidden"
        )

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

    def test_color_vars_count(self, config):
        """tree_state_style.json has 10 entries."""
        assert len(config.color_vars) == 10

    def test_color_vars_keys(self, config):
        expected_keys = {
            "background", "mounted", "pushed", "masked",
            "revealed", "visible", "mirrored", "hidden",
            "warning", "selected",
        }
        assert set(config.color_vars.keys()) == expected_keys

    def test_font_vars_count(self, config):
        """tree_state_font.json has 3 entries."""
        assert len(config._font_vars) == 3

    def test_font_vars_keys(self, config):
        assert set(config._font_vars.keys()) == {"default", "muted", "italic"}

    def test_resolve_text_color_primary(self, config):
        font = FontStyleClass(text_color_var="text_primary")
        assert config.resolve_text_color(font) == "#ECEFF4"

    def test_resolve_text_color_dim(self, config):
        font = FontStyleClass(text_color_var="text_dim")
        assert config.resolve_text_color(font) == "#616E88"

    def test_resolve_text_color_warning(self, config):
        font = FontStyleClass(text_color_var="text_warning")
        assert config.resolve_text_color(font) == "#D08770"

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
        assert len(config.columns) == 5

    def test_column_headers(self, config):
        headers = [c.header for c in config.columns]
        assert headers == ["Local Host", "Mount", "Mask", "Reveal", "Push"]

    def test_column_0_not_checkable(self, config):
        assert config.columns[0].checkable is False

    def test_column_1_mount(self, config):
        col = config.columns[1]
        assert col.checkable is True
        assert col.check_field == "mounted"
        assert col.symbol_type == "check"
        assert col.cascade_on_uncheck == ["masked", "revealed"]

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
        assert len(config.columns) == 2

    def test_column_headers(self, config):
        headers = [c.header for c in config.columns]
        assert headers == ["Container Scope", "Push"]

    def test_column_1_push(self, config):
        col = config.columns[1]
        assert col.checkable is True
        assert col.check_field == "pushed"
        assert col.symbol_type == "pushed_status"

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
