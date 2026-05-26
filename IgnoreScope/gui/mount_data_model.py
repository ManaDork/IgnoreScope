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
NodeStencilTierRole = Qt.ItemDataRole.UserRole + 3
NodePathRole = Qt.ItemDataRole.UserRole + 4


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

        # Strong-reference guard. PyQt6's createIndex(row, col, ptr) stores
        # only a void pointer — Python alone holds the MountDataNode reference.
        # If tree mutation (load_config rebuilding sibling/extension subtrees,
        # set_host_project_root replacing the root) drops references while the
        # proxy still holds source indices into those nodes, the next
        # rowCount(parent.internalPointer()) dereferences freed memory and
        # Windows fires an access violation. _handed_out keeps every node
        # the model has indexed alive until the next explicit reset.
        # Cleared on refresh()/reset()/set_host_project_root_and_reset().
        self._handed_out: dict[int, MountDataNode] = {}

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
        self._handed_out.clear()
        self.endResetModel()

    def reset(self) -> None:
        """Explicit model reset for callers outside the model (e.g., the
        structural-delta branch of ``ConfigManager.reload_current_scope``).
        Clears the strong-reference guard so dropped nodes can be GC'd.
        """
        self.beginResetModel()
        self._handed_out.clear()
        self.endResetModel()

    def set_host_project_root_and_reset(self, host_project_root: Path) -> None:
        """Bracket ``MountDataTree.set_host_project_root`` in a model reset.

        ``tree.set_host_project_root`` replaces ``_root_node`` outright, freeing
        every previously-indexed node. Without this bracket the proxy's stale
        source indices dereference freed memory on the next re-filter — the
        ``gui-startup-access-violation`` crash family. Routing the project-root
        replacement through this method guarantees the bracket is always set.

        Single-model variant — when both ``LocalHostView`` and ``ScopeView``
        share the underlying tree, use :meth:`reset_models_around` instead so
        both views' models bracket the mutation atomically.
        """
        self.beginResetModel()
        self._tree.set_host_project_root(host_project_root)
        self._handed_out.clear()
        self.endResetModel()

    @staticmethod
    def reset_models_around(
        models: list["MountDataTreeModel"],
        mutator,
    ) -> None:
        """Bracket multiple models around a shared tree mutation.

        Both ``LocalHostView`` and ``ScopeView`` instantiate their own
        ``MountDataTreeModel`` over the same ``MountDataTree``. A raw tree
        mutation (e.g., ``set_host_project_root``, manual ``load_config``)
        replaces or rebuilds subtrees without giving either model a chance
        to call ``beginResetModel``. The proxy then dereferences freed
        ``MountDataNode`` pointers and the GUI access-violates.

        This helper calls ``beginResetModel`` on every model BEFORE the
        mutator runs, then clears each model's strong-reference guard and
        calls ``endResetModel`` after. Both views see the reset atomically
        — no event-loop tick in which one model is reset and the other is
        mid-mutation.
        """
        for m in models:
            m.beginResetModel()
        try:
            mutator()
        finally:
            for m in models:
                m._handed_out.clear()
                m.endResetModel()

    def _index_for(
        self, row: int, column: int, node: MountDataNode,
    ) -> QModelIndex:
        """createIndex with strong-reference bookkeeping.

        Every node handed out as an ``internalPointer()`` enters ``_handed_out``
        so Python cannot GC it while the proxy may still dereference the index.
        """
        self._handed_out[id(node)] = node
        return self.createIndex(row, column, node)

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
            return self._index_for(row, column, child_node)

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

        return self._index_for(parent_node.row, 0, parent_node)

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

        if role == NodeStencilTierRole:
            return node.stencil_tier if node.is_stencil_node else "mirrored"

        if role == NodePathRole:
            return node.path

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
        if node is None or node.is_file or node.is_stencil_node:
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
        return not node.children_loaded and not node.is_file and not node.is_stencil_node

    def fetchMore(self, parent: QModelIndex) -> None:
        if not parent.isValid():
            return
        node: MountDataNode = parent.internalPointer()
        if node is None or node.children_loaded or node.is_file or node.is_stencil_node:
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
