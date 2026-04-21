"""Tests for dominant-mode header tinting (Task 2.8).

Covers:
  - resolve_delivery_tint_key() — pure resolver logic
  - LocalHostView._apply_header_tint() — Qt stylesheet wiring
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.gui.local_host_view import LocalHostView
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.style_engine import StyleGui, resolve_delivery_tint_key


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_style_singleton():
    StyleGui._reset()
    yield
    StyleGui._reset()


# ──────────────────────────────────────────────
# Resolver — pure logic
# ──────────────────────────────────────────────

class TestResolveDeliveryTintKey:
    def _spec(self, name: str, delivery: str) -> MountSpecPath:
        return MountSpecPath(mount_root=Path(f"/fake/{name}"), delivery=delivery)

    def test_empty_returns_none(self):
        assert resolve_delivery_tint_key([]) is None

    def test_all_bind_returns_config_mount(self):
        specs = [self._spec("a", "bind"), self._spec("b", "bind")]
        assert resolve_delivery_tint_key(specs) == "config.mount"

    def test_all_detached_returns_visibility_virtual(self):
        specs = [self._spec("a", "detached"), self._spec("b", "detached")]
        assert resolve_delivery_tint_key(specs) == "visibility.virtual"

    def test_majority_bind(self):
        specs = [
            self._spec("a", "bind"),
            self._spec("b", "bind"),
            self._spec("c", "detached"),
        ]
        assert resolve_delivery_tint_key(specs) == "config.mount"

    def test_majority_detached(self):
        specs = [
            self._spec("a", "detached"),
            self._spec("b", "detached"),
            self._spec("c", "bind"),
        ]
        assert resolve_delivery_tint_key(specs) == "visibility.virtual"

    def test_tie_resolves_to_config_mount(self):
        specs = [self._spec("a", "bind"), self._spec("b", "detached")]
        assert resolve_delivery_tint_key(specs) == "config.mount"

    def test_single_bind_returns_config_mount(self):
        assert resolve_delivery_tint_key([self._spec("a", "bind")]) == "config.mount"

    def test_single_detached_returns_visibility_virtual(self):
        specs = [self._spec("a", "detached")]
        assert resolve_delivery_tint_key(specs) == "visibility.virtual"


# ──────────────────────────────────────────────
# LocalHostView.apply_header_tint — Qt wiring
# ──────────────────────────────────────────────

class TestLocalHostViewHeaderTint:
    @pytest.fixture
    def view(self, tmp_path: Path) -> LocalHostView:
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        v = LocalHostView(tree)
        return v

    def test_empty_scope_clears_override(self, view: LocalHostView):
        assert view._tree_view.header().styleSheet() == ""

    def test_bind_only_tints_with_config_mount(
        self, view: LocalHostView, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        view._tree.toggle_mounted(src, True)

        expected_hex = view._config.color_vars["config.mount"]
        qss = view._tree_view.header().styleSheet()
        assert expected_hex in qss
        assert "QHeaderView::section" in qss

    def test_detached_only_tints_with_visibility_virtual(
        self, view: LocalHostView, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        view._tree.toggle_detached_mount(src, True)

        expected_hex = view._config.color_vars["visibility.virtual"]
        qss = view._tree_view.header().styleSheet()
        assert expected_hex in qss

    def test_mixed_majority_bind(
        self, view: LocalHostView, tmp_path: Path,
    ):
        a = tmp_path / "a"
        b = tmp_path / "b"
        c = tmp_path / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        view._tree.toggle_mounted(a, True)
        view._tree.toggle_mounted(b, True)
        view._tree.toggle_detached_mount(c, True)

        expected_hex = view._config.color_vars["config.mount"]
        assert expected_hex in view._tree_view.header().styleSheet()

    def test_mixed_majority_detached(
        self, view: LocalHostView, tmp_path: Path,
    ):
        a = tmp_path / "a"
        b = tmp_path / "b"
        c = tmp_path / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        view._tree.toggle_detached_mount(a, True)
        view._tree.toggle_detached_mount(b, True)
        view._tree.toggle_mounted(c, True)

        expected_hex = view._config.color_vars["visibility.virtual"]
        assert expected_hex in view._tree_view.header().styleSheet()

    def test_tint_updates_on_mount_added(
        self, view: LocalHostView, tmp_path: Path,
    ):
        assert view._tree_view.header().styleSheet() == ""
        src = tmp_path / "src"
        src.mkdir()
        view._tree.toggle_detached_mount(src, True)
        expected_hex = view._config.color_vars["visibility.virtual"]
        assert expected_hex in view._tree_view.header().styleSheet()

    def test_tint_clears_when_last_mount_removed(
        self, view: LocalHostView, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        view._tree.toggle_mounted(src, True)
        assert "QHeaderView::section" in view._tree_view.header().styleSheet()

        view._tree.toggle_mounted(src, False)
        assert view._tree_view.header().styleSheet() == ""

    def test_tint_updates_on_delivery_convert(
        self, view: LocalHostView, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        view._tree.toggle_mounted(src, True)
        bind_hex = view._config.color_vars["config.mount"]
        assert bind_hex in view._tree_view.header().styleSheet()

        view._tree.convert_delivery(src, "detached")
        detached_hex = view._config.color_vars["visibility.virtual"]
        assert detached_hex in view._tree_view.header().styleSheet()
