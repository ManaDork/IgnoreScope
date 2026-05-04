"""Cross-tree selection coordination for LocalHostView <-> ScopeView.

Single-context selection model: a click in one tree clears the sibling
tree's selection; an empty-space click in either tree clears both.

The coordinator wires `selectionChanged` and `emptySpaceClicked` signals
between the two views and uses a re-entry guard (`_suppress` flag) to
prevent the A->B->A clear cascade.

If drag-drop between trees ever lands, the "clear sibling on selection"
rule will fight the drag gesture — gate `_on_select` on a key modifier
or temporarily suspend the coordinator during drag in that case.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QTreeView


class _ClickAwareTreeView(QTreeView):
    """QTreeView that emits `emptySpaceClicked` on mousePressEvent over non-row area.

    Default Qt behaviour clears local selection on empty-space click; this
    subclass also notifies an external coordinator so it can clear the
    sibling tree's selection in addition to the local one.
    """

    emptySpaceClicked = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.indexAt(event.pos()).isValid():
            self.emptySpaceClicked.emit()
        super().mousePressEvent(event)


class TreeSelectionCoordinator(QObject):
    """Cross-tree single-context selection mediator.

    Wires the two views' `selectionChanged` + `emptySpaceClicked` signals
    so that:
      - Selecting a row in one view clears the sibling view's selection.
      - Empty-space click in either view clears BOTH views' selections.

    A `_suppress` re-entry guard prevents an infinite A->B->A clear cascade
    when one view's `clearSelection()` triggers its own `selectionChanged`
    emission.
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
        self._suppress = False

        view_a.selectionModel().selectionChanged.connect(
            lambda *_: self._on_select(view_a, view_b)
        )
        view_b.selectionModel().selectionChanged.connect(
            lambda *_: self._on_select(view_b, view_a)
        )
        view_a.emptySpaceClicked.connect(self._clear_both)
        view_b.emptySpaceClicked.connect(self._clear_both)

    def _on_select(
        self, active: _ClickAwareTreeView, other: _ClickAwareTreeView,
    ) -> None:
        if self._suppress or not active.selectionModel().hasSelection():
            return
        self._suppress = True
        try:
            other.clearSelection()
        finally:
            self._suppress = False

    def _clear_both(self) -> None:
        self._suppress = True
        try:
            self._a.clearSelection()
            self._b.clearSelection()
        finally:
            self._suppress = False
