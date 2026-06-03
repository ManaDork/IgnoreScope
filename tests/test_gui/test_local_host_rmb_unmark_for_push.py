"""Tests for LocalHostView's RMB "Unmark for Push" action.

Spec: planning/backlog/tree-rmb-unmark-actions.md Gap 1 (narrowed to
Local Host only). Plan + decisions in the session that produced
``feature/rmb-remove-marked-pushed``.

The action is visible iff the file is in marked_push (NodeState.pre_pushed
== True). Clicking removes the path from ``marked_push_scope.json`` and
triggers ``request_recompute`` so the pre_pushed visual clears.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu

from IgnoreScope.core.marked_push import (
    add_marked_push,
    load_marked_push,
)
from IgnoreScope.gui.local_host_view import LocalHostView
from IgnoreScope.gui.mount_data_tree import MountDataNode, MountDataTree
from IgnoreScope.gui.style_engine import StyleGui

SCOPE = "dev"


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
def view_with_file(tmp_path: Path) -> tuple[LocalHostView, Path]:
    """LocalHostView over a tree with tmp_path/src/a.txt; scope=dev."""
    src = tmp_path / "src"
    src.mkdir()
    target = src / "a.txt"
    target.write_text("x", encoding="utf-8")

    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    tree.current_scope = SCOPE
    # Pre-load src's children so the test can build a file node for
    # the RMB target.
    for child in tree.root_node.children:
        if not child.is_file:
            child.load_children(folders_only=False)

    view = LocalHostView(tree)
    return view, target


def _action_texts(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions()]


def _find_action(menu: QMenu, text: str) -> Optional[QAction]:
    for a in menu.actions():
        if a.text() == text:
            return a
    return None


def _file_node_for(view: LocalHostView, path: Path) -> MountDataNode:
    """Walk the tree to find the MountDataNode for ``path``."""
    for child in view._tree.root_node.children:
        if child.path == path.parent:
            for grandchild in child.children:
                if grandchild.path == path:
                    return grandchild
    raise AssertionError(f"node for {path} not found in test tree")


def test_action_visible_when_pre_pushed(view_with_file):
    """File is in marked_push → "Unmark for Push" appears in the RMB menu."""
    view, target = view_with_file
    add_marked_push(view._tree.host_project_root, SCOPE, [target])
    view._tree.request_recompute()  # populate pre_pushed via Stage 4

    node = _file_node_for(view, target)
    menu = QMenu()
    view._build_single_select_menu(menu, node, index=QModelIndex())

    assert "Unmark for Push" in _action_texts(menu)


def test_action_hidden_when_not_pre_pushed(view_with_file):
    """File is NOT in marked_push → no "Unmark for Push" entry."""
    view, target = view_with_file
    # Don't add to marked_push.

    node = _file_node_for(view, target)
    menu = QMenu()
    view._build_single_select_menu(menu, node, index=QModelIndex())

    assert "Unmark for Push" not in _action_texts(menu)


def test_action_hidden_on_folder_nodes(view_with_file):
    """Folders never get the entry — only files end up in marked_push."""
    view, target = view_with_file
    # Seed the folder's name in the queue to be sure it isn't accidentally
    # treated as pre_pushed at the folder level. (Folders don't actually
    # get added in production, but the guard belongs to is_file, not to
    # the absence of a queue entry.)
    add_marked_push(view._tree.host_project_root, SCOPE, [target])
    view._tree.request_recompute()

    folder_node = view._tree.root_node.children[0]  # the src folder
    assert not folder_node.is_file
    menu = QMenu()
    view._build_single_select_menu(menu, folder_node, index=QModelIndex())

    assert "Unmark for Push" not in _action_texts(menu)


def test_action_removes_from_queue_and_clears_pre_pushed(view_with_file):
    """Click the action → queue is empty AND pre_pushed clears on the row."""
    view, target = view_with_file
    add_marked_push(view._tree.host_project_root, SCOPE, [target])
    view._tree.request_recompute()
    assert view._tree.get_node_state(target).pre_pushed is True

    node = _file_node_for(view, target)
    menu = QMenu()
    view._build_single_select_menu(menu, node, index=QModelIndex())
    action = _find_action(menu, "Unmark for Push")
    assert action is not None

    action.trigger()

    # Queue file is deleted by remove_marked_push on empty-after-remove,
    # so load returns the empty set.
    assert load_marked_push(view._tree.host_project_root, SCOPE) == set()
    # State recomputed → pre_pushed back to default False.
    assert view._tree.get_node_state(target).pre_pushed is False


def test_action_handler_safe_with_no_project(tmp_path):
    """Slot guards on missing host_project_root / scope — no crash."""
    tree = MountDataTree()
    # No host_project_root set, no current_scope.
    view = LocalHostView(tree)

    # Should not raise.
    view._on_unmark_for_push(tmp_path / "nonexistent.txt")