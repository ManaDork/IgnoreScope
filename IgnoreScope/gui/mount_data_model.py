"""Qt model adapter for MountDataTree + TreeDisplayConfig.

MountDataTreeModel: QAbstractItemModel wrapping a MountDataTree filtered
through a TreeDisplayConfig. Two instances exist — one for LocalHostView,
one for ScopeView — sharing the same underlying MountDataTree.

One tree, two models, two views (DATAFLOWCHART Rule 4):
  MountDataTreeModel(tree, LocalHostDisplayConfig) → left panel (folders, 4 columns)
  MountDataTreeModel(tree, ScopeDisplayConfig)     → right panel (files+folders, 2 columns)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Any

from PyQt6.QtCore import Qt, QAbstractItemModel, QModelIndex, pyqtSignal

from .mount_data_tree import MountDataTree, MountDataNode, NodeSource
from .display_config import TreeDisplayConfig


# ── Constants ─────────────────────────────────────────────────────

NodeStateRole = Qt.ItemDataRole.UserRole + 1
NodeIsFileRole = Qt.ItemDataRole.UserRole + 2


# ── Model ─────────────────────────────────────────────────────────

class MountDataTreeModel(QAbstractItemModel):
    """Qt model presenting MountDataTree through a TreeDisplayConfig lens.

    Handles:
    - Column layout from TreeDisplayConfig.columns
    - NodeStateRole for delegate access to frozen CORE NodeState
    - Lazy loading delegation to MountDataNode
    - Signal forwarding from tree.stateChanged

    Signals:
        stateChanged: Forwarded from tree — used for app-level handlers.
        pushToggleRequested(object, bool): Emitted by context menus for push/remove
            (requires docker cp — handled by FileOperationsHandler).
    """

    stateChanged = pyqtSignal()
    pushToggleRequested = pyqtSignal(object, bool)

    def __init__(
        self,
        tree: MountDataTree,
        config: TreeDisplayConfig,
        parent=None,
    ):
        super().__init__(parent)
        self._tree = tree
        self._config = config

        # Connect tree signals to trigger model refresh
        self._tree.stateChanged.connect(self._on_tree_changed)

    # ── Signal Handlers ───────────────────────────────────────────

    def _on_tree_changed(self) -> None:
        """Handle tree state change — refresh all visible data."""
        rows = self.rowCount()
        cols = len(self._config.columns)
        if self._tree.root_node and rows > 0 and cols > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(rows - 1, cols - 1)
            if top_left.isValid() and bottom_right.isValid():
                self.dataChanged.emit(top_left, bottom_right)
        self.stateChanged.emit()

    # ── Public API ────────────────────────────────────────────────

    @property
    def tree(self) -> MountDataTree:
        """Access the underlying MountDataTree for proxy filtering."""
        return self._tree

    def begin_batch(self) -> None:
        """Begin batch — suppress intermediate stateChanged signals."""
        self._tree.begin_batch()

    def end_batch(self) -> None:
        """End batch — emit single stateChanged after all mutations."""
        self._tree.end_batch()

    def refresh(self) -> None:
        """Notify views that the root node has changed."""
        self.beginResetModel()
        self.endResetModel()

    # ── QAbstractItemModel: Tree Structure ────────────────────────

    def index(
        self, row: int, column: int, parent: QModelIndex = QModelIndex(),
    ) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_node = self._tree.root_node
        else:
            parent_node = parent.internalPointer()

        if parent_node and row < len(parent_node.children):
            child_node = parent_node.children[row]
            return self.createIndex(row, column, child_node)

        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        child_node: MountDataNode = index.internalPointer()
        if child_node is None:
            return QModelIndex()
        parent_node = child_node.parent

        if parent_node is None or parent_node == self._tree.root_node:
            return QModelIndex()

        return self.createIndex(parent_node.row, 0, parent_node)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            node = self._tree.root_node
        else:
            node = parent.internalPointer()

        if node is None:
            return 0

        return len(node.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._config.columns)

    # ── QAbstractItemModel: Data Access ───────────────────────────

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None

        node: MountDataNode = index.internalPointer()
        if node is None:
            return None

        col_idx = index.column()
        col_def = self._config.columns[col_idx]

        if role == Qt.ItemDataRole.DisplayRole:
            if col_idx == 0:
                name = node.name
                if node.source == NodeSource.SIBLING and node.parent == self._tree.root_node:
                    name += " [Sibling]"
                return name
            return None

        if role == NodeStateRole:
            return self._tree.get_node_state(node.path)

        if role == NodeIsFileRole:
            return node.is_file

        if role == Qt.ItemDataRole.ToolTipRole:
            return self._get_tooltip(node)

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if index.internalPointer() is None:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def headerData(
        self, section: int, orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            if 0 <= section < len(self._config.columns):
                return self._config.columns[section].header
        return None

    # ── QAbstractItemModel: Lazy Loading ──────────────────────────

    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:
        if not parent.isValid():
            root = self._tree.root_node
            return root is not None and len(root.children) > 0

        node: MountDataNode = parent.internalPointer()
        if node is None or node.is_file or node.is_virtual:
            return False

        if not node.children_loaded:
            return True

        return len(node.children) > 0

    def canFetchMore(self, parent: QModelIndex) -> bool:
        if not parent.isValid():
            return False
        node: MountDataNode = parent.internalPointer()
        if node is None:
            return False
        return not node.children_loaded and not node.is_file and not node.is_virtual

    def fetchMore(self, parent: QModelIndex) -> None:
        if not parent.isValid():
            return
        node: MountDataNode = parent.internalPointer()
        if node is None or node.children_loaded or node.is_file or node.is_virtual:
            return
        node.load_children(folders_only=not self._config.display_files)
        # Recompute states BEFORE announcing rows to proxy.
        # If states are computed after beginInsertRows, the proxy's
        # filterAcceptsRow sees default "hidden" state for new rows —
        # ScopeView (display_hidden=False) rejects them on insertion,
        # and Qt's proxy may not re-include them on later invalidation.
        self._tree.begin_batch()
        self._tree.request_recompute()
        if node.children:
            self.beginInsertRows(parent, 0, len(node.children) - 1)
            self.endInsertRows()
        self._tree.end_batch()

    # ── Helpers ───────────────────────────────────────────────────

    def _get_tooltip(self, node: MountDataNode) -> Optional[str]:
        """Build tooltip showing path + CORE visibility state."""
        parts = [str(node.path)]
        state = self._tree.get_node_state(node.path)
        parts.append(f"Visibility: {state.visibility}")

        if node.is_file:
            if state.pushed:
                parts.append("Status: In container")
            elif state.container_orphaned:
                parts.append("Status: Container-orphaned")

        return "\n".join(parts)
