"""Tests for the cursor-primary RMB resolution helper.

`view_helpers.resolve_action_target` decouples "what was clicked" from
"what was selected" per the file-manager UX pattern:

- RMB on an unselected row → operate on that row alone.
- RMB on a row that's part of an active multi-select → operate on the
  full selection.
- RMB on a single-row selection → operate on that row (cursor or selected,
  always the same row).
- RMB on empty area → return invalid index + empty list.

This decoupling fixed two pre-existing bugs:
1. LocalHostView previously read selectedRows() only and ignored
   indexAt(pos), so RMB on an unselected row showed nothing.
2. ScopeView's empty-area fallback also fired on selection-empty even
   when the click was on a valid row, hiding the per-row menu.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QItemSelectionModel, QPoint
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.local_host_view import LocalHostView
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.scope_view import ScopeView
from IgnoreScope.gui.view_helpers import resolve_action_target


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def view_with_rows(tmp_path: Path):
    """Set up a LocalHostView with a few visible rows for RMB tests.

    LocalHostDisplayConfig has display_hidden=True / display_non_mounted=True
    so default-state rows appear without needing a mount.
    """
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "gamma").mkdir()

    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    view = LocalHostView(tree)
    yield view, tree, tmp_path


def _row_pos(view, row: int) -> QPoint:
    """Compute the QPoint for the visual rect of a top-level row."""
    proxy = view._proxy
    idx = proxy.index(row, 0)
    rect = view._tree_view.visualRect(idx)
    # Center of the row's rect — guaranteed to hit the row
    return QPoint(rect.x() + rect.width() // 2, rect.y() + rect.height() // 2)


def _select_proxy_row(view, row: int, *, add: bool = False) -> None:
    proxy = view._proxy
    idx = proxy.index(row, 0)
    flag = (
        QItemSelectionModel.SelectionFlag.Select
        if add
        else QItemSelectionModel.SelectionFlag.ClearAndSelect
    )
    view._tree_view.selectionModel().select(idx, flag)


class TestResolveActionTarget:
    def test_empty_area_returns_invalid_and_empty(self, view_with_rows):
        view, _tree, _root = view_with_rows
        # Position far below any rendered row — empty area
        pos = QPoint(10, 10000)
        idx, nodes = resolve_action_target(view._tree_view, view._proxy, pos)
        assert not idx.isValid()
        assert nodes == []

    def test_unselected_row_returns_cursor_node(self, view_with_rows):
        view, _tree, root = view_with_rows
        # Nothing selected; RMB on row 0 → cursor target
        pos = _row_pos(view, 0)
        idx, nodes = resolve_action_target(view._tree_view, view._proxy, pos)
        assert idx.isValid()
        assert len(nodes) == 1
        assert nodes[0].path.name == "alpha"

    def test_unselected_row_with_other_selection_uses_cursor(self, view_with_rows):
        view, _tree, _root = view_with_rows
        # Select row 0 (alpha); RMB on row 1 (beta — NOT in selection).
        # Cursor wins; selection ignored.
        _select_proxy_row(view, 0)
        pos = _row_pos(view, 1)
        idx, nodes = resolve_action_target(view._tree_view, view._proxy, pos)
        assert idx.isValid()
        assert len(nodes) == 1
        assert nodes[0].path.name == "beta"

    def test_selected_row_with_multi_uses_selection(self, view_with_rows):
        view, _tree, _root = view_with_rows
        # Select rows 0, 1, 2; RMB on row 1 (in selection)
        _select_proxy_row(view, 0)
        _select_proxy_row(view, 1, add=True)
        _select_proxy_row(view, 2, add=True)
        pos = _row_pos(view, 1)
        idx, nodes = resolve_action_target(view._tree_view, view._proxy, pos)
        assert idx.isValid()
        names = {n.path.name for n in nodes}
        assert names == {"alpha", "beta", "gamma"}

    def test_unselected_row_with_multi_uses_cursor_only(self, view_with_rows):
        view, _tree, _root = view_with_rows
        # Multi-select rows 0 and 1; RMB on row 2 (NOT in selection).
        # Cursor wins; the unrelated multi-selection is ignored.
        _select_proxy_row(view, 0)
        _select_proxy_row(view, 1, add=True)
        pos = _row_pos(view, 2)
        idx, nodes = resolve_action_target(view._tree_view, view._proxy, pos)
        assert idx.isValid()
        assert len(nodes) == 1
        assert nodes[0].path.name == "gamma"

    def test_single_select_returns_cursor_target_alone(self, view_with_rows):
        view, _tree, _root = view_with_rows
        # Single-row selection on row 0; RMB on row 0 — len(selection) == 1
        # so the helper takes the cursor-target path (which is the same row).
        _select_proxy_row(view, 0)
        pos = _row_pos(view, 0)
        idx, nodes = resolve_action_target(view._tree_view, view._proxy, pos)
        assert idx.isValid()
        assert len(nodes) == 1
        assert nodes[0].path.name == "alpha"


class TestPathAsPosixNormalization:
    """The Mask/Reveal pattern check at local_host_view.py used to do
    `str(path.relative_to(...)).replace("\\\\", "/")`. The fix uses
    `path.relative_to(...).as_posix()` which is canonical and
    platform-uniform.
    """

    def test_as_posix_on_nested_path(self, tmp_path: Path):
        rel = (tmp_path / "src" / "main").relative_to(tmp_path)
        # On Windows, rel as a string would have backslashes; as_posix
        # always returns forward-slashes.
        assert rel.as_posix() == "src/main"

    def test_pattern_membership_uses_canonical_form(self, tmp_path: Path):
        # Mirror the pattern: `f"{rel}/" in patterns` set
        rel = (tmp_path / "src" / "main").relative_to(tmp_path)
        patterns = {"src/main/", "vendor/"}
        assert f"{rel.as_posix()}/" in patterns


class TestScopeViewEmptyAreaFallback:
    """ScopeView's empty-area fallback used to fire when selection was
    empty even if the click landed on a valid row. After the fix, the
    fallback fires ONLY when the cursor is on truly empty area.
    """

    def test_resolve_on_valid_row_returns_node_even_with_no_selection(
        self, tmp_path: Path,
    ):
        (tmp_path / "src").mkdir()
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        # Mount src so it passes Scope's filter (display_non_mounted=False)
        tree.toggle_mounted(tmp_path / "src", True)

        view = ScopeView(tree)
        proxy = view._proxy
        if proxy.rowCount() == 0:
            pytest.skip("scope proxy filter rejected fixture — config drift")

        # Pick a real row's center pos
        idx0 = proxy.index(0, 0)
        rect = view._tree_view.visualRect(idx0)
        pos = QPoint(rect.x() + rect.width() // 2, rect.y() + rect.height() // 2)

        # No selection in scope. resolve_action_target should still return
        # the cursor-target node (NOT empty-area fallback).
        assert not view._tree_view.selectionModel().hasSelection()
        idx, nodes = resolve_action_target(view._tree_view, view._proxy, pos)
        assert idx.isValid()
        assert len(nodes) == 1
