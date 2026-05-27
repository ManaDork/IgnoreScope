"""Marked-Push review dialog.

Phase B.3 / B.4 of bugfix/gui-model-lifecycle-and-marked-push-ux. A
dedicated surface for reviewing/acting on the marked-push queue
independent of the once-per-scope-load modal. Opens from
``MarkedPushBadge`` (status bar), the Container → View Marked for Push
menu entry, or the scope-load prompt itself (modally, when the container
exists).

Each row lists one queued path. Buttons:
  * **Reveal in tree** — scroll the scope view to the path and select it.
    This is also the UX path to unmark a file: reveal first, then use
    the tree's RMB. *(Today the tree's RMB does NOT yet expose unmark
    actions for marked_push / pushed_files — tracked in
    planning/backlog/tree-rmb-unmark-actions.md.)*
  * **Push Marked Files** — runs the full drain via
    ``FileOperationsHandler.drain_marked_push_now()`` then closes the
    dialog. Per-file drain is deferred (the engine currently errors on
    the file-missing-from-list path and that case lacks test coverage —
    see ``planning/backlog/per-file-drain-with-filter.md``).
  * **Close** — dismiss; queue stays intact; the badge remains visible.

Cross-references:
  - ``files-marked-for-push-fatal-crash.md`` Design UX pass #3.
  - ``_workbench/_bugs/start-container-no-drain.md`` candidate fix #2.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .app import IgnoreScopeApp


class MarkedPushDialog(QDialog):
    """Modeless dialog listing the marked-push queue with per-row actions."""

    revealRequested = pyqtSignal(Path)

    def __init__(
        self,
        app: "IgnoreScopeApp",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self.setWindowTitle("Files Marked for Push")
        self.setMinimumSize(560, 320)
        self.setModal(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._summary = QLabel("", self)
        self._summary.setObjectName("markedPushDialogSummary")
        root.addWidget(self._summary)

        self._list = QListWidget(self)
        self._list.setObjectName("markedPushDialogList")
        self._list.setAlternatingRowColors(True)
        # Double-clicking a row is a shortcut for the "Reveal in tree"
        # button — same handler, same revealRequested emit. Staged rows
        # remain a no-op (no host-tree path to reveal).
        self._list.itemDoubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self._list, stretch=1)

        button_row = QHBoxLayout()
        self._reveal_btn = QPushButton("Reveal in tree", self)
        self._reveal_btn.clicked.connect(self._on_reveal)
        button_row.addWidget(self._reveal_btn)

        button_row.addStretch(1)

        self._push_btn = QPushButton("Push Marked Files", self)
        self._push_btn.setDefault(True)
        self._push_btn.clicked.connect(self._on_push_now)
        button_row.addWidget(self._push_btn)

        self._close_btn = QPushButton("Close", self)
        self._close_btn.clicked.connect(self.close)
        button_row.addWidget(self._close_btn)

        root.addLayout(button_row)

        self._refresh()

    # ── Population ─────────────────────────────────────────────────

    def _refresh(self) -> None:
        """Re-read both queues and rebuild the list rows."""
        self._list.clear()
        host_q, staged_q = self._read_queues()
        n = len(host_q) + len(staged_q)

        if n == 0:
            self._summary.setText("Queue is empty.")
        else:
            self._summary.setText(f"{n} file(s) marked for push")

        # Host queue rows — full paths with kind tag.
        for p in sorted(host_q):
            item = QListWidgetItem(f"{p}")
            item.setData(Qt.ItemDataRole.UserRole, ("host", p))
            self._list.addItem(item)

        # Staged queue rows — these come from preserved container snapshots.
        # No path-reveal target (the source lives under .ignore_scope/.../_snapshots).
        for entry in sorted(staged_q, key=lambda e: (e.target, e.source.as_posix())):
            label = f"[staged] {entry.target}  ←  {entry.source}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ("staged", entry))
            self._list.addItem(item)

    def _read_queues(self) -> tuple[set[Path], set]:
        """Best-effort read of both queue files."""
        if self._app.host_project_root is None:
            return set(), set()
        scope = getattr(self._app, "_current_scope", None)
        if not scope:
            return set(), set()
        try:
            from ..core.marked_push import load_marked_push
            from ..core.marked_staged import load_marked_staged
            return (
                load_marked_push(self._app.host_project_root, scope),
                load_marked_staged(self._app.host_project_root, scope),
            )
        except Exception:
            return set(), set()

    def _selected_row(self) -> Optional[tuple]:
        """Return the selected row's (kind, payload) tuple, or None."""
        items = self._list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    # ── Actions ────────────────────────────────────────────────────

    def _on_reveal(self) -> None:
        sel = self._selected_row()
        if sel is None:
            return
        kind, payload = sel
        # Only host queue entries map to a host-tree path. Staged entries
        # are snapshot blobs under .ignore_scope/<scope>/_snapshots/.
        if kind != "host":
            return
        self.revealRequested.emit(payload)

    def _on_row_double_clicked(self, item: QListWidgetItem) -> None:
        """Double-click shortcut for the Reveal-in-tree action.

        Identical effect to selecting the row + clicking the Reveal button.
        Staged rows have no host-tree path, so the emit is suppressed for
        them (same as :meth:`_on_reveal`).
        """
        payload = item.data(Qt.ItemDataRole.UserRole)
        if payload is None:
            return
        kind, value = payload
        if kind != "host":
            return
        self.revealRequested.emit(value)

    def _on_push_now(self) -> None:
        """Trigger the full drain (per Decision lock in plan §B.3).

        Per-file "push only this row" drain is deferred — the engine
        currently errors on the file-missing-from-list path and that
        case lacks test coverage. Plan tracks the work at
        planning/backlog/per-file-drain-with-filter.md.
        """
        handler = getattr(self._app, "file_ops_handler", None)
        if handler is None:
            return
        handler.drain_marked_push_now()
        # Drain mutates the queue — refresh before close so the user
        # sees the result if they re-open.
        self._refresh()
        self.close()
