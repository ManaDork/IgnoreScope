"""Tests for LocalHostView's RMB "Unmark for Push" action.

Spec: planning/backlog/tree-rmb-unmark-actions.md Gap 1 (narrowed to
Local Host only). Plan + decisions in the session that produced
``feature/rmb-remove-marked-pushed``.

After the routing-fix correction:
  * Single-file Unmark for Push lives in ``_build_file_menu`` (was
    incorrectly placed in ``_build_single_select_menu`` in commit 500aea7).
  * Multi-file all-queued case gets "Unmark for Push (N files)" via
    ``_build_multi_select_file_menu``.

The action is visible iff the file is in marked_push (``NodeState.pre_pushed``
== True) AND ``"push"`` is in ``file_actions``. Clicking removes the path(s)
from ``marked_push_scope.json`` and triggers ``request_recompute`` so the
visual clears.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from PyQt6.QtCore import QModelIndex, QPoint
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
    # Pre-load children so file nodes exist for the RMB target.
    for child in tree.root_node.children:
        if not child.is_file:
            child.load_children(folders_only=False)

    view = LocalHostView(tree)
    return view, target


@pytest.fixture
def view_with_files(tmp_path: Path) -> tuple[LocalHostView, list[Path]]:
    """LocalHostView over a tree with 3 sibling files; scope=dev."""
    src = tmp_path / "src"
    src.mkdir()
    files = []
    for name in ("a.txt", "b.txt", "c.txt"):
        f = src / name
        f.write_text("x", encoding="utf-8")
        files.append(f)

    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    tree.current_scope = SCOPE
    for child in tree.root_node.children:
        if not child.is_file:
            child.load_children(folders_only=False)

    view = LocalHostView(tree)
    return view, files


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


# ── Single-file tests (retargeted to _build_file_menu per F.1) ──────────────


def test_action_visible_when_pre_pushed(view_with_file):
    """File in marked_push → "Unmark for Push" in _build_file_menu."""
    view, target = view_with_file
    add_marked_push(view._tree.host_project_root, SCOPE, [target])
    view._tree.request_recompute()

    node = _file_node_for(view, target)
    menu = QMenu()
    view._build_file_menu(menu, node)

    assert "Unmark for Push" in _action_texts(menu)
    # When pre_pushed, Push is suppressed — they're mutually exclusive.
    assert "Push" not in _action_texts(menu)


def test_action_hidden_when_not_pre_pushed(view_with_file):
    """File NOT in marked_push → no Unmark entry; standard Push shown."""
    view, target = view_with_file
    # No add_marked_push call.

    node = _file_node_for(view, target)
    menu = QMenu()
    view._build_file_menu(menu, node)

    assert "Unmark for Push" not in _action_texts(menu)
    assert "Push" in _action_texts(menu)


def test_unmark_removes_from_queue_and_clears_pre_pushed(view_with_file):
    """Click the action → queue is empty AND pre_pushed clears."""
    view, target = view_with_file
    add_marked_push(view._tree.host_project_root, SCOPE, [target])
    view._tree.request_recompute()
    assert view._tree.get_node_state(target).pre_pushed is True

    node = _file_node_for(view, target)
    menu = QMenu()
    view._build_file_menu(menu, node)
    action = _find_action(menu, "Unmark for Push")
    assert action is not None

    action.trigger()

    assert load_marked_push(view._tree.host_project_root, SCOPE) == set()
    assert view._tree.get_node_state(target).pre_pushed is False


def test_handler_safe_with_no_project(tmp_path):
    """Slot guards on missing host_project_root / scope — no crash."""
    tree = MountDataTree()
    # No host_project_root set, no current_scope.
    view = LocalHostView(tree)
    view._on_unmark_for_push(tmp_path / "nonexistent.txt")  # must not raise


# ── End-to-end test via _show_context_menu (F.6 — catches "wrong method") ───


def test_rmb_dispatch_routes_file_to_build_file_menu(view_with_file, monkeypatch):
    """End-to-end dispatch check: a single-file RMB calls _build_file_menu,
    NOT _build_single_select_menu.

    This is the test that would have caught commit 500aea7's "wrong method"
    bug — the original action was placed in _build_single_select_menu (the
    folder builder) and never reached for file nodes.
    """
    view, target = view_with_file
    add_marked_push(view._tree.host_project_root, SCOPE, [target])
    view._tree.request_recompute()

    # Capture which builders dispatch invokes.
    file_menu_calls: list[MountDataNode] = []
    single_select_calls: list[MountDataNode] = []
    orig_file_menu = view._build_file_menu
    orig_single_select = view._build_single_select_menu

    def spy_file_menu(menu, node):
        file_menu_calls.append(node)
        orig_file_menu(menu, node)

    def spy_single_select(menu, node, index):
        single_select_calls.append(node)
        orig_single_select(menu, node, index)

    monkeypatch.setattr(view, "_build_file_menu", spy_file_menu)
    monkeypatch.setattr(view, "_build_single_select_menu", spy_single_select)
    monkeypatch.setattr(QMenu, "exec", lambda self, *a, **kw: None)

    # Build a valid proxy index for the target so the dispatcher's
    # `index_at_pos.isValid()` guard passes.
    node = _file_node_for(view, target)
    # Walk proxy → find target's index. The src folder is the first row;
    # target is the first file under it.
    src_proxy = view._proxy.index(0, 0)
    assert src_proxy.isValid(), "test fixture: src/ should be top-level row"
    target_proxy = view._proxy.index(0, 0, src_proxy)
    if not target_proxy.isValid():
        # Default filter may hide unmounted files. Loosen for the test.
        view._config.display_hidden = True
        view._config.display_files = True
        view._proxy.invalidateFilter()
        target_proxy = view._proxy.index(0, 0, src_proxy)
    assert target_proxy.isValid(), "test fixture: target proxy index should be valid"

    def fake_resolve(tree_view, proxy, pos):
        return target_proxy, [node]
    import IgnoreScope.gui.local_host_view as lhv_mod
    monkeypatch.setattr(lhv_mod, "resolve_action_target", fake_resolve)

    view._show_context_menu(QPoint(0, 0))

    assert len(file_menu_calls) == 1, (
        f"expected _build_file_menu invoked once for a file node; "
        f"got {len(file_menu_calls)} file-menu + {len(single_select_calls)} single-select"
    )
    assert len(single_select_calls) == 0, (
        f"_build_single_select_menu should NOT be invoked for a file node; "
        f"got {len(single_select_calls)} calls"
    )
    assert file_menu_calls[0] is node


# ── Multi-select tests (F.2 + F.6) ──────────────────────────────────────────


def test_multi_all_pre_pushed_shows_batch_unmark(view_with_files):
    """All N files queued → "Unmark for Push (N files)" appears.
    Push and Remove are suppressed (their gating conditions don't hold).
    """
    view, files = view_with_files
    add_marked_push(view._tree.host_project_root, SCOPE, files)
    view._tree.request_recompute()

    nodes = [_file_node_for(view, p) for p in files]
    menu = QMenu()
    view._build_multi_select_file_menu(menu, nodes)

    assert f"Unmark for Push ({len(files)} files)" in _action_texts(menu)
    assert not any(t.startswith("Push (") for t in _action_texts(menu))
    assert not any(t.startswith("Remove (") for t in _action_texts(menu))


def test_multi_batch_unmark_drops_all_from_queue(view_with_files):
    """Trigger the batch Unmark → all paths removed from marked_push."""
    view, files = view_with_files
    add_marked_push(view._tree.host_project_root, SCOPE, files)
    view._tree.request_recompute()

    nodes = [_file_node_for(view, p) for p in files]
    menu = QMenu()
    view._build_multi_select_file_menu(menu, nodes)
    action = _find_action(menu, f"Unmark for Push ({len(files)} files)")
    assert action is not None

    action.trigger()

    assert load_marked_push(view._tree.host_project_root, SCOPE) == set()
    for p in files:
        assert view._tree.get_node_state(p).pre_pushed is False


def test_multi_none_pushed_or_queued_shows_push(view_with_files):
    """No files in container, no files queued → "Push (N files)" appears."""
    view, files = view_with_files

    nodes = [_file_node_for(view, p) for p in files]
    menu = QMenu()
    view._build_multi_select_file_menu(menu, nodes)

    assert f"Push ({len(files)} files)" in _action_texts(menu)
    assert not any("Unmark" in t for t in _action_texts(menu))


def test_multi_mixed_pushed_and_pre_pushed_shows_disabled(view_with_files):
    """Some pushed, some pre_pushed → no batch action; disabled info shown.

    Both subsets are individually actionable but the multi-select API
    doesn't model "act only on the subset"; flagging as disabled is the
    honest UX.
    """
    view, files = view_with_files
    # Half queued, half "pushed" (push the second half directly into pushed_files).
    add_marked_push(view._tree.host_project_root, SCOPE, [files[0]])
    view._tree._pushed_files.add(files[1])
    view._tree.request_recompute()

    nodes = [_file_node_for(view, p) for p in files]
    menu = QMenu()
    view._build_multi_select_file_menu(menu, nodes)

    texts = _action_texts(menu)
    assert any("mixed states" in t for t in texts), f"expected disabled mixed-info, got {texts}"
    # The mixed-info action should be disabled.
    for action in menu.actions():
        if "mixed states" in action.text():
            assert not action.isEnabled()


def test_multi_all_pushed_shows_remove(view_with_files):
    """Regression: all files pushed → "Remove (N files)" still works."""
    view, files = view_with_files
    for p in files:
        view._tree._pushed_files.add(p)
    view._tree.request_recompute()

    nodes = [_file_node_for(view, p) for p in files]
    menu = QMenu()
    view._build_multi_select_file_menu(menu, nodes)

    assert f"Remove ({len(files)} files)" in _action_texts(menu)
    assert not any("Unmark" in t for t in _action_texts(menu))
