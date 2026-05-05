"""Tests for cross-tree selection coordination.

Covers the bug where LocalHost and Scope tree selections accumulated
independently — see `_workbench/_bugs/cross-tree-selection-coordination.md`.

The coordinator reacts to USER GESTURES only (`userRowClicked`,
`emptySpaceClicked`), not arbitrary `selectionChanged`. This avoids a
feedback loop with the existing
`LocalHostView.nodeSelected -> ScopeView.expand_to_path` chain in
`app.py`, which programmatically updates ScopeView selection — without
the user-gesture gate, that programmatic change would trigger the
coordinator to clear LocalHost's selection, breaking multi-select.

Tests synthesize the user gesture by emitting `userRowClicked` /
`emptySpaceClicked` directly after setting up the underlying selection
state programmatically. This mirrors the runtime path: Qt's mousePressEvent
updates selection via `super().mousePressEvent`, then the override emits
the user-gesture signal.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QItemSelectionModel, QStringListModel
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.selection_coordinator import (
    TreeSelectionCoordinator,
    _ClickAwareTreeView,
)


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def two_views():
    """Two `_ClickAwareTreeView` instances backed by simple QStringListModels.

    Avoids spinning up a full IgnoreScopeApp — the coordinator only depends
    on the QTreeView contract (selectionModel + clearSelection + the new
    userRowClicked / emptySpaceClicked signals).

    Note: the constructor positional order is `(local_host, scope, parent)`
    — view_a (first) plays the LocalHost role, view_b plays Scope. Asymmetric
    coordinator: only Scope→LocalHost click clears.
    """
    model_a = QStringListModel(["a0", "a1", "a2", "a3"])  # plays LocalHost
    model_b = QStringListModel(["b0", "b1", "b2"])         # plays Scope

    view_a = _ClickAwareTreeView()
    view_a.setModel(model_a)
    view_b = _ClickAwareTreeView()
    view_b.setModel(model_b)

    coord = TreeSelectionCoordinator(view_a, view_b)
    yield view_a, view_b, coord


def _select_row(view, row: int) -> None:
    """Programmatic selection update — does NOT trigger coordinator."""
    idx = view.model().index(row, 0)
    view.selectionModel().select(
        idx, QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )


def _add_row(view, row: int) -> None:
    """Programmatic selection add — does NOT trigger coordinator."""
    idx = view.model().index(row, 0)
    view.selectionModel().select(
        idx, QItemSelectionModel.SelectionFlag.Select,
    )


def _user_click_row(view, row: int) -> None:
    """Synthesize a user click on a valid row.

    In the runtime path, Qt's `mousePressEvent.super()` updates the
    selection and then `_ClickAwareTreeView.mousePressEvent` emits
    `userRowClicked`. The test mirrors this by setting the selection
    programmatically THEN emitting the signal.
    """
    _select_row(view, row)
    view.userRowClicked.emit()


def _user_ctrl_click_row(view, row: int) -> None:
    """Synthesize a user Ctrl+click adding `row` to the existing selection."""
    _add_row(view, row)
    view.userRowClicked.emit()


class TestSelectionCoordinator:
    def test_local_host_click_clears_scope(self, two_views):
        """Symmetric: clicking LocalHost clears Scope's selection (single-context)."""
        local_host, scope, _coord = two_views
        _select_row(scope, 0)
        _add_row(scope, 1)
        assert scope.selectionModel().hasSelection()

        _user_click_row(local_host, 2)

        assert local_host.selectionModel().hasSelection()
        assert not scope.selectionModel().hasSelection()

    def test_scope_click_clears_local_host(self, two_views):
        """Symmetric: clicking Scope clears LocalHost's selection (single-context)."""
        local_host, scope, _coord = two_views
        _select_row(local_host, 0)
        _add_row(local_host, 1)
        assert local_host.selectionModel().hasSelection()

        _user_click_row(scope, 1)

        assert scope.selectionModel().hasSelection()
        assert not local_host.selectionModel().hasSelection()

    def test_ctrl_multi_click_within_tree_does_not_clear_own(self, two_views):
        """Ctrl+click multi-select within one tree must not collapse to single row.

        The previous (selectionChanged-wired) coordinator fired on every
        selection change including programmatic ones, so each Ctrl+click
        triggered a cascade that wiped its own selection. The user-gesture-
        wired coordinator only fires on mousePress, so Ctrl+click adds to
        the active tree's selection without disturbing it.
        """
        local_host, _scope, _coord = two_views
        _user_click_row(local_host, 0)
        _user_ctrl_click_row(local_host, 1)

        rows = {i.row() for i in local_host.selectionModel().selectedIndexes()}
        assert rows == {0, 1}

    def test_programmatic_selection_does_not_clear_other(self, two_views):
        """Setting selection programmatically (no userRowClicked emit) does NOT
        trigger the coordinator — this is the contract that protects the
        nodeSelected -> expand_to_path chain in app.py.
        """
        view_a, view_b, _coord = two_views
        _select_row(view_a, 0)  # programmatic — coordinator should ignore
        # Now programmatically set view_b's selection (simulating expand_to_path)
        _select_row(view_b, 0)
        # Both views still have their selections — coordinator did not interfere
        assert view_a.selectionModel().hasSelection()
        assert view_b.selectionModel().hasSelection()

    def test_empty_space_click_on_a_clears_a(self, two_views):
        view_a, view_b, _coord = two_views
        _user_click_row(view_a, 0)
        _user_ctrl_click_row(view_a, 1)
        assert view_a.selectionModel().hasSelection()

        view_a.emptySpaceClicked.emit()

        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_empty_space_click_on_b_clears_a(self, two_views):
        """Empty-space click on the EMPTY tree still clears the OTHER tree's selection.

        The coordinator's empty-space handler is symmetric — it clears
        BOTH views regardless of which view the click landed in.
        """
        view_a, view_b, _coord = two_views
        _user_click_row(view_a, 0)
        _user_ctrl_click_row(view_a, 1)
        assert view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

        view_b.emptySpaceClicked.emit()

        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_clear_both_handles_already_empty_state(self, two_views):
        view_a, view_b, coord = two_views
        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

        coord._clear_both()  # must not raise / hang

        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_scope_re_click_still_clears_local_host(self, two_views):
        """Re-clicking the same row in Scope still clears LocalHost — the
        coordinator runs on every user click, not just selection changes.
        """
        local_host, scope, _coord = two_views
        _user_click_row(scope, 0)
        _select_row(local_host, 0)
        assert local_host.selectionModel().hasSelection()

        # User re-clicks the same row in Scope
        _user_click_row(scope, 0)

        assert scope.selectionModel().hasSelection()
        assert not local_host.selectionModel().hasSelection()
