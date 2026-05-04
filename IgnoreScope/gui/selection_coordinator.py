"""Cross-tree selection coordination for LocalHostView <-> ScopeView.

Single-context selection model: a USER click on a row in one tree clears
the sibling tree's selection; an empty-space click in either tree clears
both.

The coordinator wires the two views' `userRowClicked` and `emptySpaceClicked`
signals — both fired from `_ClickAwareTreeView.mousePressEvent` ONLY on a
user mouse press. Programmatic selection changes (e.g., from
`LocalHostView.nodeSelected -> ScopeView.expand_to_path` chain in app.py)
do NOT trigger cross-tree clearing, so multi-select within a single tree
remains intact and the auto-expand-to-path UX continues to work.

Keyboard navigation in one tree does not clear the other (intentional —
arrow-key nav is exploration, not single-context selection). If desired
later, override `keyPressEvent` and emit `userRowClicked` from there.

If drag-drop between trees ever lands, the "clear sibling on click" rule
will fight the drag gesture — gate `_on_user_select` on a key modifier or
suspend the coordinator during drag in that case.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QTreeView


class _ClickAwareTreeView(QTreeView):
    """QTreeView that emits user-gesture signals from `mousePressEvent`.

    - `userRowClicked` fires when the press lands on a valid row index
      (after Qt's default selection update via super().mousePressEvent).
    - `emptySpaceClicked` fires when the press lands on non-row area.

    Both signals fire ONLY on user mouse press — programmatic selection
    changes do not trigger them. This is the load-bearing distinction
    that lets a coordinator react to user intent without interfering
    with programmatic selection chains.
    """

    userRowClicked = pyqtSignal()
    emptySpaceClicked = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        valid = self.indexAt(event.pos()).isValid()
        super().mousePressEvent(event)
        if valid:
            self.userRowClicked.emit()
        else:
            self.emptySpaceClicked.emit()


class TreeSelectionCoordinator(QObject):
    """Cross-tree single-context selection mediator.

    Wires the two views' user-gesture signals so that:
      - A user click on a row in one view clears the sibling view's selection.
      - An empty-space click in either view clears BOTH views' selections.

    No `_suppress` re-entry guard is needed because the signals are user-
    gesture-only — clearing one view programmatically does NOT re-trigger
    the coordinator.
    """

    def __init__(
        self,
        view_a: _ClickAwareTreeView,
        view_b: _ClickAwareTreeView,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._a = view_a
        self._b = view_b

        view_a.userRowClicked.connect(lambda: self._on_user_select(view_a, view_b))
        view_b.userRowClicked.connect(lambda: self._on_user_select(view_b, view_a))
        view_a.emptySpaceClicked.connect(self._clear_both)
        view_b.emptySpaceClicked.connect(self._clear_both)

    def _on_user_select(
        self, active: _ClickAwareTreeView, other: _ClickAwareTreeView,
    ) -> None:
        if not active.selectionModel().hasSelection():
            return
        other.clearSelection()

    def _clear_both(self) -> None:
        self._a.clearSelection()
        self._b.clearSelection()
