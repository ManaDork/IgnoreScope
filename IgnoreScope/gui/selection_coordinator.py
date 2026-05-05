"""Cross-tree selection coordination for LocalHostView <-> ScopeView.

Symmetric single-context selection model:
  - User click on EITHER tree clears the other tree's selection.
  - Empty-space click in either tree clears BOTH selections.

The coordinator wires the two views' `userRowClicked` and `emptySpaceClicked`
signals — both fired from `_ClickAwareTreeView.mousePressEvent` ONLY on a
user mouse press. Programmatic selection changes (e.g., from
`selectionChangedPaths -> set_tracked_paths`) do NOT trigger cross-tree
clearing, so the tracked-overlay chain remains independent.

The tracked-path overlay (separate visual layer in `delegates.py`) is
orthogonal to this coordinator: clearing Scope's `selectionModel` does
not clear the tracked outline. The outline auto-clears only when LocalHost's
own selection becomes empty (which fires `selectionChangedPaths([])`).

Keyboard navigation in one tree does not clear the other (intentional —
arrow-key nav is exploration, not single-context selection). If desired
later, override `keyPressEvent` and emit `userRowClicked` from there.

If drag-drop between trees ever lands, the cross-tree clear rule will
fight the drag gesture — gate `_on_user_select` on a key modifier or
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
    """Cross-tree symmetric single-context selection mediator.

    Wires user-gesture signals so that:
      - A user click on EITHER view clears the sibling view's selection.
      - Empty-space click in either view clears BOTH views' selections.

    The tracked-path overlay (separate visual layer) is independent of this
    coordinator. When a Scope click clears LocalHost's selection, LocalHost
    fires `selectionChangedPaths([])`, which separately clears the Scope
    tracked outline via the chain in `app.py`. The two layers compose
    without interfering.

    Constructor positional order is `(local_host_view, scope_view, parent)`
    by convention — but the coordinator is fully symmetric so swapping
    them produces the same behavior.
    """

    def __init__(
        self,
        local_host_view: _ClickAwareTreeView,
        scope_view: _ClickAwareTreeView,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._local_host = local_host_view
        self._scope = scope_view

        # Symmetric: each view's click clears the sibling.
        local_host_view.userRowClicked.connect(
            lambda: self._on_user_select(local_host_view, scope_view)
        )
        scope_view.userRowClicked.connect(
            lambda: self._on_user_select(scope_view, local_host_view)
        )
        # Empty-space click clears both, regardless of which tree fired it.
        local_host_view.emptySpaceClicked.connect(self._clear_both)
        scope_view.emptySpaceClicked.connect(self._clear_both)

    def _on_user_select(
        self, active: _ClickAwareTreeView, other: _ClickAwareTreeView,
    ) -> None:
        if not active.selectionModel().hasSelection():
            return
        other.clearSelection()

    def _clear_both(self) -> None:
        self._local_host.clearSelection()
        self._scope.clearSelection()
