"""Session History Panel.

Bottom dock panel showing chronological undo/redo entries from both panels
(Folder Config + Scope Config). Uses QListView with HistoryDelegate for
per-row gradient painting via HISTORY_ states.

Contains:
  - HistoryEntryType enum + HistoryEntry dataclass (data types)
  - resolve_history_state() MatrixState truth table
  - HistoryStateRole custom data role
  - HistoryModel (QAbstractListModel)
  - SessionHistory (QWidget wrapper)

Undo integration deferred — panel is a passive view with public API
(add_entry, set_current, clear). undo.py wires in during Logic phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from PyQt6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QPersistentModelIndex,
)
from PyQt6.QtWidgets import QListView, QVBoxLayout, QWidget


# ── Data Types ────────────────────────────────────────────────────

class HistoryEntryType(Enum):
    """Type of history operation."""
    NORMAL = auto()
    DESTRUCTIVE = auto()


@dataclass
class HistoryEntry:
    """Single undo/redo history entry."""
    description: str
    entry_type: HistoryEntryType
    is_current: bool = False


# ── Custom Role ───────────────────────────────────────────────────

HistoryStateRole = Qt.ItemDataRole.UserRole + 2


# ── MatrixState Resolution ────────────────────────────────────────

def resolve_history_state(
    entry_type: HistoryEntryType,
    is_current: bool,
    above_cursor: bool,
) -> str:
    """Resolve history visual state from entry flags.

    Truth table (GUI_LAYOUT_SPECS Section 12E)::

        entry_type   | is_current | above_cursor | → State
        -------------|-----------|-------------|---------------------------
        NORMAL       | True      | —           | HISTORY_UNDO_CURRENT
        NORMAL       | False     | True        | HISTORY_REDO_AVAILABLE
        NORMAL       | False     | False       | HISTORY_NORMAL
        DESTRUCTIVE  | True      | —           | HISTORY_DESTRUCTIVE_SELECTED
        DESTRUCTIVE  | False     | True        | HISTORY_REDO_AVAILABLE
        DESTRUCTIVE  | False     | False       | HISTORY_DESTRUCTIVE
    """
    if is_current:
        if entry_type == HistoryEntryType.DESTRUCTIVE:
            return "HISTORY_DESTRUCTIVE_SELECTED"
        return "HISTORY_UNDO_CURRENT"

    if above_cursor:
        return "HISTORY_REDO_AVAILABLE"

    if entry_type == HistoryEntryType.DESTRUCTIVE:
        return "HISTORY_DESTRUCTIVE"

    return "HISTORY_NORMAL"


# ── Model ─────────────────────────────────────────────────────────

class HistoryModel(QAbstractListModel):
    """List model for session history entries.

    Stores HistoryEntry items with a movable cursor that determines
    which entry is "current" and which are above/below for undo/redo
    state resolution.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[HistoryEntry] = []
        self._cursor_index: int = -1

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None

        entry = self._items[row]

        if role == Qt.ItemDataRole.DisplayRole:
            return entry.description

        if role == HistoryStateRole:
            above_cursor = row > self._cursor_index and self._cursor_index >= 0
            return resolve_history_state(
                entry.entry_type, entry.is_current, above_cursor,
            )

        return None

    def add_entry(
        self,
        description: str,
        entry_type: HistoryEntryType = HistoryEntryType.NORMAL,
    ) -> None:
        """Append a history entry and set it as current.

        Truncates any entries above the current cursor position
        (standard undo behavior — new action discards redo stack).
        """
        # Truncate redo entries above cursor
        if self._cursor_index >= 0 and self._cursor_index < len(self._items) - 1:
            remove_start = self._cursor_index + 1
            self.beginRemoveRows(QModelIndex(), remove_start, len(self._items) - 1)
            del self._items[remove_start:]
            self.endRemoveRows()

        # Append new entry
        new_row = len(self._items)
        self.beginInsertRows(QModelIndex(), new_row, new_row)
        entry = HistoryEntry(
            description=description,
            entry_type=entry_type,
            is_current=True,
        )
        self._items.append(entry)
        self.endInsertRows()

        # Move cursor to new entry
        old_cursor = self._cursor_index
        self._cursor_index = new_row
        self._recompute_current(old_cursor)

    def set_current(self, row: int) -> None:
        """Move the cursor to the given row, recomputing all states."""
        if row < 0 or row >= len(self._items):
            return
        old_cursor = self._cursor_index
        self._cursor_index = row
        self._recompute_current(old_cursor)

    def clear(self) -> None:
        """Remove all entries and reset cursor."""
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self._cursor_index = -1
        self.endResetModel()

    def _recompute_current(self, old_cursor: int) -> None:
        """Update is_current flags and emit dataChanged for affected rows."""
        for i, entry in enumerate(self._items):
            entry.is_current = (i == self._cursor_index)

        # Emit dataChanged for the range covering old and new cursor
        if old_cursor < 0:
            old_cursor = 0
        lo = min(old_cursor, self._cursor_index)
        hi = max(old_cursor, self._cursor_index)
        lo = max(lo, 0)
        hi = min(hi, len(self._items) - 1)
        if lo <= hi:
            self.dataChanged.emit(
                self.index(lo), self.index(hi),
                [Qt.ItemDataRole.DisplayRole, HistoryStateRole],
            )


# ── Widget ────────────────────────────────────────────────────────

class SessionHistory(QWidget):
    """Session History panel widget.

    Passive view — exposes add_entry(), set_current(), clear() for
    undo.py to wire into during Logic phase.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Imports here to avoid circular import at module level
        from .list_display_config import ListDisplayConfig
        from .delegates import HistoryDelegate

        self._config = ListDisplayConfig()
        self._model = HistoryModel(self)
        self._delegate = HistoryDelegate(self._config, self)
        self._list_view = QListView(self)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Configure QListView and layout."""
        view = self._list_view
        view.setModel(self._model)
        view.setItemDelegate(self._delegate)
        view.setAlternatingRowColors(False)
        view.setSelectionMode(QListView.SelectionMode.NoSelection)
        view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

    # ── Public API (delegated to model) ───────────────────────────

    def add_entry(
        self,
        description: str,
        entry_type: HistoryEntryType = HistoryEntryType.NORMAL,
    ) -> None:
        """Add a history entry and set it as current."""
        self._model.add_entry(description, entry_type)

    def set_current(self, index: int) -> None:
        """Move the cursor to the given index."""
        self._model.set_current(index)

    def clear(self) -> None:
        """Remove all history entries."""
        self._model.clear()
