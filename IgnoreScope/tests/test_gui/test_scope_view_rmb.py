"""Tests for the Scope Config Tree RMB state machine (Phase 3 Task 4.6).

Covers the new RMB gestures on the ScopeView:

  - Empty-area / non-spec node → full gesture set (Make Folder,
    Make Permanent Folder ▸ No Recreate / Volume Mount).
  - Existing detached+folder spec → Mark Permanent | Unmark Permanent + Remove.
  - Existing volume spec → Remove only.
  - Make Folder dialog path wires through to add_stencil_folder.
  - Make Permanent Folder → Volume Mount prompts recreate confirmation when a
    container exists.
  - Header RMB follows the Phase 2 silent-no-op fallback pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QInputDialog, QMenu

from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.gui.mount_data_tree import MountDataNode, MountDataTree
from IgnoreScope.gui.scope_view import ScopeView
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
def view(tmp_path: Path) -> ScopeView:
    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    return ScopeView(tree)


def _action_texts(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions()]


def _find_action(menu: QMenu, text: str) -> Optional[QAction]:
    for a in menu.actions():
        if a.text() == text:
            return a
    return None


def _find_submenu(menu: QMenu, title: str) -> Optional[QMenu]:
    for a in menu.actions():
        if a.menu() is not None and a.text() == title:
            return a.menu()
    return None


class TestScopeGesturesEmptyArea:
    """Empty-area / non-spec click → full Make Folder gesture set."""

    def test_empty_area_shows_full_gesture_set(
        self, view: ScopeView,
    ):
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=None)

        texts = _action_texts(menu)
        assert "Make Folder" in texts
        assert "Make Permanent Folder" in texts

        perm = _find_submenu(menu, "Make Permanent Folder")
        assert perm is not None
        perm_texts = _action_texts(perm)
        assert "No Recreate" in perm_texts
        assert "Volume Mount" in perm_texts

    def test_non_spec_folder_node_shows_full_gesture_set(
        self, view: ScopeView, tmp_path: Path,
    ):
        """Clicking a folder node with no spec at its path → full gesture set."""
        node = MountDataNode(path=tmp_path / "some" / "unmapped")

        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        texts = _action_texts(menu)
        assert "Make Folder" in texts
        assert "Make Permanent Folder" in texts


class TestScopeGesturesStencilFolder:
    """Existing detached+folder spec → Mark/Unmark + Remove."""

    def test_non_permanent_detached_folder_offers_mark(
        self, view: ScopeView, tmp_path: Path,
    ):
        container_path = Path("/opt/cache")
        view._tree.add_stencil_folder(container_path)

        node = MountDataNode(path=container_path)
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        texts = _action_texts(menu)
        assert "Mark Permanent" in texts
        assert "Unmark Permanent" not in texts
        assert "Remove" in texts
        assert "Make Folder" not in texts

    def test_permanent_detached_folder_offers_unmark(
        self, view: ScopeView, tmp_path: Path,
    ):
        container_path = Path("/opt/cache")
        view._tree.add_stencil_folder(container_path, preserve_on_update=True)

        node = MountDataNode(path=container_path)
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        texts = _action_texts(menu)
        assert "Unmark Permanent" in texts
        assert "Mark Permanent" not in texts
        assert "Remove" in texts

    def test_mark_permanent_trigger_flips_flag(
        self, view: ScopeView,
    ):
        container_path = Path("/opt/cache")
        view._tree.add_stencil_folder(container_path)

        node = MountDataNode(path=container_path)
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        mark = _find_action(menu, "Mark Permanent")
        assert mark is not None
        mark.trigger()

        spec = view._tree.get_spec_at(container_path)
        assert spec is not None
        assert spec.preserve_on_update is True

    def test_unmark_permanent_trigger_flips_flag(
        self, view: ScopeView,
    ):
        container_path = Path("/opt/cache")
        view._tree.add_stencil_folder(container_path, preserve_on_update=True)

        node = MountDataNode(path=container_path)
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        unmark = _find_action(menu, "Unmark Permanent")
        assert unmark is not None
        unmark.trigger()

        spec = view._tree.get_spec_at(container_path)
        assert spec is not None
        assert spec.preserve_on_update is False

    def test_remove_trigger_drops_spec(
        self, view: ScopeView,
    ):
        container_path = Path("/opt/cache")
        view._tree.add_stencil_folder(container_path)

        node = MountDataNode(path=container_path)
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        remove = _find_action(menu, "Remove")
        assert remove is not None
        remove.trigger()

        assert view._tree.get_spec_at(container_path) is None


class TestScopeGesturesStencilVolume:
    """Existing delivery='volume' spec → Remove only (no tier changes)."""

    def test_volume_spec_shows_only_remove(
        self, view: ScopeView,
    ):
        container_path = Path("/var/data")
        view._tree.add_stencil_volume(container_path)

        node = MountDataNode(path=container_path)
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        texts = _action_texts(menu)
        assert texts == ["Remove"]
        assert "Mark Permanent" not in texts
        assert "Unmark Permanent" not in texts

    def test_volume_remove_drops_spec(
        self, view: ScopeView,
    ):
        container_path = Path("/var/data")
        view._tree.add_stencil_volume(container_path)

        node = MountDataNode(path=container_path)
        menu = QMenu()
        view._add_scope_config_gestures(menu, node=node)

        remove = _find_action(menu, "Remove")
        assert remove is not None
        remove.trigger()

        assert view._tree.get_spec_at(container_path) is None


class TestMakeFolderDialog:
    """Make Folder prompts for container-side path and wires to add_stencil_folder."""

    def test_make_folder_happy_path(
        self, view: ScopeView, monkeypatch,
    ):
        monkeypatch.setattr(
            QInputDialog, "getText",
            lambda *a, **kw: ("/opt/cache", True),
        )

        view._on_make_folder()

        spec = view._tree.get_spec_at(Path("/opt/cache"))
        assert spec is not None
        assert spec.delivery == "detached"
        assert spec.content_seed == "folder"
        assert spec.preserve_on_update is False
        assert spec.host_path is None

    def test_make_folder_cancel_is_noop(
        self, view: ScopeView, monkeypatch,
    ):
        monkeypatch.setattr(
            QInputDialog, "getText",
            lambda *a, **kw: ("", False),
        )

        view._on_make_folder()

        assert view._tree._mount_specs == []

    def test_make_folder_empty_input_is_noop(
        self, view: ScopeView, monkeypatch,
    ):
        monkeypatch.setattr(
            QInputDialog, "getText",
            lambda *a, **kw: ("   ", True),
        )

        view._on_make_folder()

        assert view._tree._mount_specs == []

    def test_make_permanent_no_recreate_sets_preserve_flag(
        self, view: ScopeView, monkeypatch,
    ):
        monkeypatch.setattr(
            QInputDialog, "getText",
            lambda *a, **kw: ("/opt/db", True),
        )

        view._on_make_permanent_no_recreate()

        spec = view._tree.get_spec_at(Path("/opt/db"))
        assert spec is not None
        assert spec.delivery == "detached"
        assert spec.content_seed == "folder"
        assert spec.preserve_on_update is True


class TestMakePermanentVolume:
    """Volume Mount gesture: emits recreateRequested iff container exists.

    Confirmation of the destructive recreate is owned by the host-app
    ``recreate_container`` slot, not by ScopeView — see the
    ``recreateRequested`` connect in ``app._connect_signals`` and the
    richer ``QMessageBox`` in ``container_ops_ui.recreate_container``.
    """

    def test_volume_mount_no_container_skips_recreate(
        self, view: ScopeView, monkeypatch,
    ):
        monkeypatch.setattr(
            QInputDialog, "getText",
            lambda *a, **kw: ("/var/data", True),
        )
        monkeypatch.setattr(view, "_container_exists", lambda: False)

        recreate_signals: list = []
        view.recreateRequested.connect(lambda: recreate_signals.append(None))

        view._on_make_permanent_volume()

        spec = view._tree.get_spec_at(Path("/var/data"))
        assert spec is not None
        assert spec.delivery == "volume"
        assert recreate_signals == []

    def test_volume_mount_container_exists_emits_recreate(
        self, view: ScopeView, monkeypatch,
    ):
        monkeypatch.setattr(
            QInputDialog, "getText",
            lambda *a, **kw: ("/var/data", True),
        )
        monkeypatch.setattr(view, "_container_exists", lambda: True)

        recreate_signals: list = []
        view.recreateRequested.connect(lambda: recreate_signals.append(None))

        view._on_make_permanent_volume()

        spec = view._tree.get_spec_at(Path("/var/data"))
        assert spec is not None
        assert spec.delivery == "volume"
        assert recreate_signals == [None]


class TestHeaderFallback:
    """Scope header RMB: always exec, append 'No valid actions' when empty."""

    def test_header_with_no_scope_shows_fallback(
        self, view: ScopeView, monkeypatch,
    ):
        invocations: list[QMenu] = []

        def spy_exec(self, *args, **kwargs):
            invocations.append(self)
            return None

        monkeypatch.setattr(QMenu, "exec", spy_exec)

        view._show_header_context_menu(QPoint(0, 0))

        assert len(invocations) == 1
        actions = invocations[0].actions()
        assert len(actions) == 1
        assert actions[0].text() == "No valid actions"
        assert actions[0].isEnabled() is False


class TestEmptyAreaMenu:
    """Clicking empty viewport space still pops the gesture menu."""

    def test_empty_viewport_exec_pops_gesture_menu(
        self, view: ScopeView, monkeypatch,
    ):
        invocations: list[QMenu] = []

        def spy_exec(self, *args, **kwargs):
            invocations.append(self)
            return None

        monkeypatch.setattr(QMenu, "exec", spy_exec)

        # No indexAt(pos) hit — triggers empty-area branch.
        view._show_context_menu(QPoint(5000, 5000))

        assert len(invocations) == 1
        texts = _action_texts(invocations[0])
        assert "Make Folder" in texts
        assert "Make Permanent Folder" in texts
