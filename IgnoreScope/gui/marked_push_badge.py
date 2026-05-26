"""Status-bar badge displaying the marked-push queue count.

Phase B.3 of bugfix/gui-model-lifecycle-and-marked-push-ux. The user
returning to a project with a non-empty queue mid-session needs a
visible affordance to review/act on the list independent of the
scope-load modal (which only fires once on project open / scope switch).

The badge:
  - Reads ``load_marked_push`` + ``load_marked_staged`` for the current
    scope, displays the combined count.
  - Hidden when count == 0 — no badge until the queue has entries.
  - Clickable — emits ``clicked`` to open ``MarkedPushDialog``.
  - Refresh signal: connect to ``MountDataTree.stateChanged`` so the
    count updates whenever the queue mutates (enqueue, drain, scope
    switch).

Cross-references:
  - ``_workbench/_bugs/start-container-no-drain.md`` candidate fix #2
    (status-bar badge) — this widget implements that half.
  - ``files-marked-for-push-fatal-crash.md`` Design UX pass #3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

if TYPE_CHECKING:
    from .app import IgnoreScopeApp


class MarkedPushBadge(QWidget):
    """Status-bar widget showing "N marked for push" — clickable.

    Visible iff count > 0. Click emits :attr:`clicked` so the host app
    can open ``MarkedPushDialog``. Refresh by calling :meth:`update_count`
    or by connecting :meth:`update_count` to a refresh signal (the
    typical wiring is ``MountDataTree.stateChanged.connect(badge.update_count)``).
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        app: "IgnoreScopeApp",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self.setObjectName("markedPushBadge")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self._label = QLabel("0 marked for push", self)
        self._label.setObjectName("markedPushBadgeLabel")
        layout.addWidget(self._label)

        # Hidden by default — surfaces only when the queue is non-empty.
        self._count = 0
        self.setVisible(False)

    def update_count(self) -> None:
        """Re-read both queues and update the visible count / visibility.

        Reads the app's current ``host_project_root`` / ``_current_scope``
        on every call — no parallel state to keep in sync. Idempotent;
        safe to call on every ``stateChanged`` emit. Queue reads are
        best-effort; an unreadable queue file is treated as empty.
        """
        host_project_root = getattr(self._app, "host_project_root", None)
        scope = getattr(self._app, "_current_scope", None)
        if host_project_root is None or not scope:
            self._count = 0
        else:
            try:
                from ..core.marked_push import load_marked_push
                from ..core.marked_staged import load_marked_staged
                host_q = load_marked_push(host_project_root, scope)
                staged_q = load_marked_staged(host_project_root, scope)
                self._count = len(host_q) + len(staged_q)
            except Exception:
                self._count = 0

        self._label.setText(f"{self._count} marked for push")
        self.setVisible(self._count > 0)

    @property
    def count(self) -> int:
        """Current count — exposed for tests."""
        return self._count

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
