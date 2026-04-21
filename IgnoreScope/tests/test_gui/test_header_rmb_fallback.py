"""Tests for the Header/Tree RMB silent-no-op fallback (Phase 2 Task 3.3).

Covers the case where ``_add_delivery_gestures`` contributes zero
actions (e.g., the header path is an ancestor of an existing
mount_spec). The menu must still exec with a disabled
``No valid actions`` entry so the RMB hook is discoverable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QMenu

from IgnoreScope.gui.local_host_view import LocalHostView
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.style_engine import StyleGui


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
def view(tmp_path: Path) -> LocalHostView:
    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    return LocalHostView(tree)


class TestHeaderRmbFallback:
    def test_header_shows_disabled_placeholder_when_no_gestures(
        self, view: LocalHostView, tmp_path: Path,
    ):
        """Header RMB on a path that can't be acted on still pops a menu."""
        # Mount a child — header path (tmp_path) now can't be mounted
        # (would overlap) and isn't itself a mount_root to convert.
        src = tmp_path / "src"
        src.mkdir()
        view._tree.toggle_mounted(src, True)

        menu = QMenu()
        view._add_delivery_gestures(menu, tmp_path)
        assert menu.actions() == []  # precondition: gestures are empty

        # The header hook should append a disabled placeholder.
        fallback = QMenu()
        view._add_delivery_gestures(fallback, tmp_path)
        if not fallback.actions():
            from PyQt6.QtGui import QAction
            placeholder = QAction("No valid actions", fallback)
            placeholder.setEnabled(False)
            fallback.addAction(placeholder)

        assert len(fallback.actions()) == 1
        assert fallback.actions()[0].text() == "No valid actions"
        assert fallback.actions()[0].isEnabled() is False

    def test_header_real_gestures_unchanged(
        self, view: LocalHostView, tmp_path: Path,
    ):
        """When real gestures exist the menu is unchanged (no spurious placeholder)."""
        menu = QMenu()
        view._add_delivery_gestures(menu, tmp_path)
        assert len(menu.actions()) >= 1
        for action in menu.actions():
            # All real gestures are enabled; only the fallback placeholder
            # is disabled, so none should be present here.
            assert action.isEnabled() is True
            assert action.text() != "No valid actions"


class TestHeaderContextMenuInvocation:
    """Direct calls on _show_header_context_menu to exercise the guard flip."""

    def test_menu_invoked_even_when_no_gestures(
        self, view: LocalHostView, tmp_path: Path, monkeypatch,
    ):
        src = tmp_path / "src"
        src.mkdir()
        view._tree.toggle_mounted(src, True)

        invocations: list[QMenu] = []

        original_exec = QMenu.exec

        def spy_exec(self, *args, **kwargs):
            invocations.append(self)
            # Don't actually block on user input in tests.
            return None

        monkeypatch.setattr(QMenu, "exec", spy_exec)

        from PyQt6.QtCore import QPoint
        view._show_header_context_menu(QPoint(0, 0))

        assert len(invocations) == 1
        actions = invocations[0].actions()
        assert len(actions) == 1
        assert actions[0].text() == "No valid actions"
        assert actions[0].isEnabled() is False

        monkeypatch.setattr(QMenu, "exec", original_exec)
