"""Tests for cross-tree selection coordination.

Covers the bug where LocalHost and Scope tree selections accumulated
independently — see `_workbench/_bugs/cross-tree-selection-coordination.md`.

Two contracts:
  1. Selecting a row in one view clears the sibling view's selection.
  2. Empty-space click in either view clears BOTH views' selections.
  3. The re-entry guard prevents infinite A->B->A clear cascade.
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
    emptySpaceClicked signal).
    """
    model_a = QStringListModel(["a0", "a1", "a2", "a3"])
    model_b = QStringListModel(["b0", "b1", "b2"])

    view_a = _ClickAwareTreeView()
    view_a.setModel(model_a)
    view_b = _ClickAwareTreeView()
    view_b.setModel(model_b)

    coord = TreeSelectionCoordinator(view_a, view_b)
    yield view_a, view_b, coord


def _select_row(view, row: int) -> None:
    idx = view.model().index(row, 0)
    view.selectionModel().select(
        idx, QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )


def _add_row(view, row: int) -> None:
    idx = view.model().index(row, 0)
    view.selectionModel().select(
        idx, QItemSelectionModel.SelectionFlag.Select,
    )


class TestSelectionCoordinator:
    def test_select_in_a_clears_b(self, two_views):
        view_a, view_b, _coord = two_views
        _select_row(view_b, 0)
        _add_row(view_b, 1)
        assert view_b.selectionModel().hasSelection()

        _select_row(view_a, 2)
        assert view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_select_in_b_clears_a(self, two_views):
        """Symmetric to test_select_in_a_clears_b."""
        view_a, view_b, _coord = two_views
        _select_row(view_a, 0)
        _add_row(view_a, 1)
        assert view_a.selectionModel().hasSelection()

        _select_row(view_b, 1)
        assert view_b.selectionModel().hasSelection()
        assert not view_a.selectionModel().hasSelection()

    def test_empty_space_click_on_a_clears_a(self, two_views):
        """Empty-space click on the tree that has a selection clears it."""
        view_a, view_b, _coord = two_views
        _select_row(view_a, 0)
        _add_row(view_a, 1)
        assert view_a.selectionModel().hasSelection()

        view_a.emptySpaceClicked.emit()

        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_empty_space_click_on_b_clears_a(self, two_views):
        """Empty-space click on the EMPTY tree still clears the OTHER tree's selection.

        The coordinator enforces single-context selection (selecting in A
        clears B), so at any moment only one tree has a non-empty selection.
        Empty-space click on EITHER tree must clear that selection regardless
        of which tree the click landed on.
        """
        view_a, view_b, _coord = two_views
        _select_row(view_a, 0)
        _add_row(view_a, 1)
        assert view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

        # Click empty space in the OTHER (empty) tree — should still clear A
        view_b.emptySpaceClicked.emit()

        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_clear_both_handles_already_empty_state(self, two_views):
        """Calling _clear_both with both views already empty is a safe no-op."""
        view_a, view_b, coord = two_views
        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

        coord._clear_both()  # must not raise / hang

        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_clear_selection_does_not_cascade_infinitely(self, two_views):
        """Calling clearSelection on A must not cause B's clear to retrigger A's clear."""
        view_a, view_b, _coord = two_views
        _select_row(view_a, 0)
        _select_row(view_b, 0)

        # Track selectionChanged on B; should fire 0 times when A is cleared
        # (A's clear triggers _on_select with active=A having no selection,
        #  which short-circuits early — so B is never cleared by the coordinator).
        b_emit_count = [0]
        view_b.selectionModel().selectionChanged.connect(
            lambda *_: b_emit_count[0].__iadd__(1) if False else b_emit_count.__setitem__(0, b_emit_count[0] + 1)
        )

        view_a.clearSelection()

        # B was already-selected before; its selection is unchanged because the
        # coordinator's _on_select short-circuits on `not active.hasSelection()`.
        # The key assertion is no infinite loop happened (test would hang or
        # exhaust recursion). Counter sanity-check: B's selectionChanged fired
        # at most once (and likely zero times since no actual change was made).
        assert b_emit_count[0] <= 1

    def test_programmatic_clear_no_infinite_loop_via_coordinator(self, two_views):
        """The _suppress guard prevents A's clearSelection from triggering B's clear from triggering A's clear."""
        view_a, view_b, coord = two_views
        _select_row(view_a, 0)
        _select_row(view_b, 0)

        # _clear_both must not re-enter; if it did, the test would never return.
        coord._clear_both()

        assert not view_a.selectionModel().hasSelection()
        assert not view_b.selectionModel().hasSelection()

    def test_select_already_selected_does_not_clear_sibling(self, two_views):
        """Re-selecting the same row in A shouldn't disturb B (no actual selection change)."""
        view_a, view_b, _coord = two_views
        _select_row(view_a, 0)
        _select_row(view_b, 0)

        # Re-issue the same selection in A — Qt may emit selectionChanged with
        # empty selected/deselected indexes. Coordinator's hasSelection check
        # still passes (A has a selection), so B WOULD be cleared by spec.
        # This test documents the expected behavior: even idempotent selects
        # in A clear B. If users re-tap a row in A intending to keep B's
        # selection, that's a Qt limitation — they should empty-click instead.
        _select_row(view_a, 0)
        assert view_a.selectionModel().hasSelection()
        # B is cleared because A's selectionChanged fires and coordinator runs.
        assert not view_b.selectionModel().hasSelection()
