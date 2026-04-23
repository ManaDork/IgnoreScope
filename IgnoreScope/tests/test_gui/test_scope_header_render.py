"""Tests for Phase 3 Task 3.4: Scope Config Tree header rendering.

Covers:
  - ScopeView._apply_header_signals → QHeaderView stylesheet routing
  - ScopeView.refresh() dot prefix derivation from running state
  - mountSpecsChanged signal triggers header re-render
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.local_mount_config import ExtensionConfig
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.scope_view import ScopeView
from IgnoreScope.gui.style_engine import ScopeHeaderSignals, StyleGui


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_style_singleton():
    StyleGui._reset()
    yield
    StyleGui._reset()


@pytest.fixture
def tree_and_view(tmp_path: Path):
    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    tree.current_scope = "test_scope"
    view = ScopeView(tree)
    return tree, view


# ──────────────────────────────────────────────
# _apply_header_signals stylesheet routing
# ──────────────────────────────────────────────


class TestApplyHeaderSignals:
    def test_empty_signals_clears_stylesheet(self, tree_and_view):
        _, view = tree_and_view
        view._tree_view.header().setStyleSheet("QHeaderView::section { color: red; }")
        view._apply_header_signals(
            ScopeHeaderSignals(False, False, False),
        )
        assert view._tree_view.header().styleSheet() == ""

    def test_running_only_clears_stylesheet(self, tree_and_view):
        # running is text-only — does NOT paint the stylesheet.
        _, view = tree_and_view
        view._apply_header_signals(
            ScopeHeaderSignals(
                container_running=True, fully_virtual=False, has_mounts=False,
            ),
        )
        assert view._tree_view.header().styleSheet() == ""

    def test_fully_virtual_sets_background(self, tree_and_view):
        _, view = tree_and_view
        view._apply_header_signals(
            ScopeHeaderSignals(
                container_running=False, fully_virtual=True, has_mounts=False,
            ),
        )
        css = view._tree_view.header().styleSheet()
        assert "background-color:" in css
        assert "border-bottom" not in css

    def test_has_mounts_sets_border_bottom(self, tree_and_view):
        _, view = tree_and_view
        view._apply_header_signals(
            ScopeHeaderSignals(
                container_running=False, fully_virtual=False, has_mounts=True,
            ),
        )
        css = view._tree_view.header().styleSheet()
        assert "border-bottom:" in css
        assert "background-color" not in css

    def test_fully_virtual_uses_virtual_color(self, tree_and_view):
        _, view = tree_and_view
        expected = view._config.color_vars.get("visibility.virtual")
        assert expected, "visibility.virtual must exist in theme"
        view._apply_header_signals(
            ScopeHeaderSignals(
                container_running=False, fully_virtual=True, has_mounts=False,
            ),
        )
        assert expected in view._tree_view.header().styleSheet()

    def test_has_mounts_uses_config_mount_color(self, tree_and_view):
        _, view = tree_and_view
        expected = view._config.color_vars.get("config.mount")
        assert expected, "config.mount must exist in theme"
        view._apply_header_signals(
            ScopeHeaderSignals(
                container_running=False, fully_virtual=False, has_mounts=True,
            ),
        )
        assert expected in view._tree_view.header().styleSheet()


# ──────────────────────────────────────────────
# refresh() dot prefix
# ──────────────────────────────────────────────


class TestRefreshDotPrefix:
    def test_running_true_sets_filled_dot(self, tree_and_view):
        tree, view = tree_and_view
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=True,
        ):
            view.refresh()
        assert view._config.columns[0].header.startswith("● ")

    def test_running_false_sets_hollow_dot(self, tree_and_view):
        tree, view = tree_and_view
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=False,
        ):
            view.refresh()
        assert view._config.columns[0].header.startswith("○ ")

    def test_placeholder_scope_no_dot(self, tmp_path: Path):
        from IgnoreScope.gui.app import PLACEHOLDER_SCOPE
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        tree.current_scope = PLACEHOLDER_SCOPE
        view = ScopeView(tree)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=False,
        ):
            view.refresh()
        header = view._config.columns[0].header
        assert not header.startswith("● ")
        assert not header.startswith("○ ")

    def test_empty_scope_no_dot(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        tree.current_scope = ""
        view = ScopeView(tree)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=False,
        ):
            view.refresh()
        header = view._config.columns[0].header
        assert not header.startswith("● ")
        assert not header.startswith("○ ")


# ──────────────────────────────────────────────
# refresh() stylesheet composition
# ──────────────────────────────────────────────


class TestRefreshStylesheetComposition:
    def test_bind_mount_paints_border(self, tree_and_view, tmp_path: Path):
        tree, view = tree_and_view
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=True,
        ):
            view.refresh()
        css = view._tree_view.header().styleSheet()
        assert "border-bottom:" in css

    def test_extension_only_paints_background(self, tree_and_view):
        tree, view = tree_and_view
        ext = ExtensionConfig(
            name="claude", isolation_paths=["/root/.claude"],
        )
        tree._extensions.append(ext)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=True,
        ):
            view.refresh()
        css = view._tree_view.header().styleSheet()
        assert "background-color:" in css
        assert "border-bottom" not in css

    def test_empty_scope_clears_stylesheet(self, tree_and_view):
        _, view = tree_and_view
        view._tree_view.header().setStyleSheet(
            "QHeaderView::section { color: red; }",
        )
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=False,
        ):
            view.refresh()
        assert view._tree_view.header().styleSheet() == ""


# ──────────────────────────────────────────────
# mountSpecsChanged re-renders
# ──────────────────────────────────────────────


class TestMountSpecsChangedReRenders:
    def test_adding_bind_spec_updates_border(self, tree_and_view, tmp_path: Path):
        tree, view = tree_and_view
        # Baseline: empty scope, clear stylesheet.
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=False,
        ):
            view.refresh()
            assert "border-bottom" not in view._tree_view.header().styleSheet()
            # Mutation emits mountSpecsChanged → ScopeView.refresh → re-render.
            src = tmp_path / "src"
            src.mkdir()
            tree.toggle_mounted(src, True)
        assert "border-bottom:" in view._tree_view.header().styleSheet()

    def test_adding_extension_updates_background(self, tree_and_view):
        tree, view = tree_and_view
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=True,
        ):
            view.refresh()
            assert "background-color" not in view._tree_view.header().styleSheet()
            ext = ExtensionConfig(
                name="claude", isolation_paths=["/root/.claude"],
            )
            tree._extensions.append(ext)
            tree.mountSpecsChanged.emit()
        assert "background-color:" in view._tree_view.header().styleSheet()
