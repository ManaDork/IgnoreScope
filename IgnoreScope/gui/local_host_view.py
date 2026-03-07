"""Local Host view — left panel showing folder configuration.

LocalHostView: QWidget wrapping a QTreeView + MountDataTreeModel with
LocalHostDisplayConfig. Shows folders with Mount/Mask/Reveal columns.
No undo integration (deferred to Logic phase — undo.py).
No TreeContext, no QProgressDialog, no UndoStack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QTreeView,
    QWidget,
    QVBoxLayout,
    QHeaderView,
    QAbstractItemView,
    QMenu,
)

from .delegates import TreeStyleDelegate
from .display_filter_proxy import DisplayFilterProxy
from .mount_data_tree import MountDataTree, MountDataNode, NodeSource
from .mount_data_model import MountDataTreeModel
from dataclasses import replace as dc_replace
from .display_config import ColumnDef, LocalHostDisplayConfig
from .view_helpers import configure_tree_view, apply_header_config


# Column indices matching LocalHostDisplayConfig.columns order
_COL_MOUNT = 1
_COL_MASK = 2
_COL_REVEAL = 3
_COL_PUSH = 4


class LocalHostView(QWidget):
    """Left panel: folder configuration with Mount/Mask/Reveal columns.

    Wraps a QTreeView + MountDataTreeModel filtered through
    LocalHostDisplayConfig. Context menu dispatches single/multi
    toggle operations directly via model.setData().

    Signals:
        stateChanged: Forwarded from model for app-level handlers.
    """

    stateChanged = pyqtSignal()
    nodeSelected = pyqtSignal(Path)
    syncRequested = pyqtSignal(Path)
    removeSiblingRequested = pyqtSignal(object)  # Path emitted

    def __init__(
        self, tree: MountDataTree, parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._tree = tree
        self._config = LocalHostDisplayConfig()
        self._model = MountDataTreeModel(tree, self._config)
        self._proxy = DisplayFilterProxy(self._model, self._config)
        self._tree_view = QTreeView()

        self._setup_ui()
        self._connect_signals()

    # ── UI Setup ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._delegate = TreeStyleDelegate(self._config, self._tree_view)
        configure_tree_view(
            self._tree_view, self._proxy, self._delegate,
            self._config.columns, self._show_context_menu,
        )

        layout.addWidget(self._tree_view)

    def _connect_signals(self) -> None:
        self._model.stateChanged.connect(self.stateChanged.emit)
        self._tree_view.selectionModel().currentChanged.connect(
            self._on_selection_changed,
        )

    # ── Public API ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Refresh the model after external data changes."""
        # Dynamic column header: show project folder name or default
        root = self._tree.host_project_root
        header = f"./{root.name}" if root else "Local Host"
        self._config.columns[0] = dc_replace(self._config.columns[0], header=header)

        self._model.refresh()
        apply_header_config(self._tree_view, self._config.columns)

        # Expand root
        root_index = self._proxy.index(0, 0)
        if root_index.isValid():
            self._tree_view.expand(root_index)

    @property
    def tree_view(self) -> QTreeView:
        """QTreeView access for external consumers."""
        return self._tree_view

    # ── Selection Sync ──────────────────────────────────────────

    def _on_selection_changed(self, current, previous) -> None:
        """Emit nodeSelected when any node is selected."""
        if not current.isValid():
            return
        source_idx = self._proxy.mapToSource(current)
        node = source_idx.internalPointer()
        if node is not None:
            self.nodeSelected.emit(node.path)

    # ── Context Menu ──────────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint) -> None:
        selected_indexes = self._tree_view.selectionModel().selectedRows(0)
        if not selected_indexes:
            return

        nodes: list[MountDataNode] = []
        for idx in selected_indexes:
            source_idx = self._proxy.mapToSource(idx)
            node = source_idx.internalPointer()
            if node is not None:
                nodes.append(node)
        if not nodes:
            return

        menu = QMenu(self)
        if len(nodes) == 1:
            node = nodes[0]
            if node.is_file:
                self._build_file_menu(menu, node)
            else:
                # Pass proxy index for expand/collapse operations
                self._build_single_select_menu(menu, node, selected_indexes[0])
        else:
            # Separate files and folders for multi-select
            file_nodes = [n for n in nodes if n.is_file]
            folder_nodes = [n for n in nodes if not n.is_file]
            if file_nodes and not folder_nodes:
                self._build_multi_select_file_menu(menu, file_nodes)
            elif folder_nodes and not file_nodes:
                self._build_multi_select_menu(menu, folder_nodes)
            else:
                info = QAction(
                    f"{len(nodes)} items (mixed files/folders)", menu,
                )
                info.setEnabled(False)
                menu.addAction(info)
        if menu.actions():
            menu.exec(self._tree_view.viewport().mapToGlobal(pos))

    def _build_single_select_menu(
        self, menu: QMenu, node: MountDataNode, index,
    ) -> None:
        path = node.path

        self._add_checkable_action(
            menu, "Mount", "mounted", _COL_MOUNT,
            self._tree.can_check_mounted, node,
        )
        self._add_checkable_action(
            menu, "Mask", "masked", _COL_MASK,
            self._tree.can_check_masked, node,
        )
        self._add_checkable_action(
            menu, "Reveal", "revealed", _COL_REVEAL,
            self._tree.can_check_revealed, node,
        )

        menu.addSeparator()

        # Folder navigation actions
        if not node.is_file:
            if self._tree_view.isExpanded(index):
                collapse_action = QAction("Collapse", menu)
                collapse_action.triggered.connect(
                    lambda: self._tree_view.collapse(index),
                )
                menu.addAction(collapse_action)
            else:
                expand_action = QAction("Expand", menu)
                expand_action.triggered.connect(
                    lambda: self._tree_view.expand(index),
                )
                menu.addAction(expand_action)

            expand_all_action = QAction("Expand All", menu)
            expand_all_action.triggered.connect(
                lambda: self._expand_recursive(index),
            )
            menu.addAction(expand_all_action)

        # Sibling root removal
        if node.source == NodeSource.SIBLING and node.parent == self._tree.root_node:
            menu.addSeparator()
            remove_sib_action = QAction("Remove Sibling", menu)
            remove_sib_action.triggered.connect(
                lambda: self.removeSiblingRequested.emit(node.path),
            )
            menu.addAction(remove_sib_action)

    def _build_multi_select_menu(
        self, menu: QMenu, nodes: list[MountDataNode],
    ) -> None:
        # Only siblings (same parent)
        parents = {n.path.parent for n in nodes}
        if len(parents) != 1:
            info = QAction(
                f"{len(nodes)} items selected (not siblings)", menu,
            )
            info.setEnabled(False)
            menu.addAction(info)
            return

        # Mount — uniform state check
        all_mounted = all(
            self._tree.is_in_raw_set("mounted", n.path) for n in nodes
        )
        none_mounted = all(
            not self._tree.is_in_raw_set("mounted", n.path) for n in nodes
        )
        all_can_mount = all(
            self._tree.can_check_mounted(n.path) for n in nodes
        )
        if (all_mounted or none_mounted) and (all_can_mount or all_mounted):
            mount_action = QAction(f"Mount ({len(nodes)} items)", menu)
            mount_action.setCheckable(True)
            mount_action.setChecked(all_mounted)
            mount_action.triggered.connect(
                lambda checked: self._toggle_multi(nodes, _COL_MOUNT, checked),
            )
            menu.addAction(mount_action)

        # Mask — uniform state check
        all_masked = all(
            self._tree.is_in_raw_set("masked", n.path) for n in nodes
        )
        none_masked = all(
            not self._tree.is_in_raw_set("masked", n.path) for n in nodes
        )
        all_can_mask = all(
            self._tree.can_check_masked(n.path) for n in nodes
        )
        if (all_masked or none_masked) and (all_can_mask or all_masked):
            mask_action = QAction(f"Mask ({len(nodes)} items)", menu)
            mask_action.setCheckable(True)
            mask_action.setChecked(all_masked)
            mask_action.triggered.connect(
                lambda checked: self._toggle_multi(nodes, _COL_MASK, checked),
            )
            menu.addAction(mask_action)

        # Reveal — uniform state check
        all_revealed = all(
            self._tree.is_in_raw_set("revealed", n.path) for n in nodes
        )
        none_revealed = all(
            not self._tree.is_in_raw_set("revealed", n.path) for n in nodes
        )
        all_can_reveal = all(
            self._tree.can_check_revealed(n.path) for n in nodes
        )
        if (all_revealed or none_revealed) and (all_can_reveal or all_revealed):
            reveal_action = QAction(f"Reveal ({len(nodes)} items)", menu)
            reveal_action.setCheckable(True)
            reveal_action.setChecked(all_revealed)
            reveal_action.triggered.connect(
                lambda checked: self._toggle_multi(
                    nodes, _COL_REVEAL, checked,
                ),
            )
            menu.addAction(reveal_action)

        # Fallback for mixed states
        if menu.isEmpty():
            info = QAction(
                f"{len(nodes)} items (mixed states)", menu,
            )
            info.setEnabled(False)
            menu.addAction(info)

    def _build_file_menu(self, menu: QMenu, node: MountDataNode) -> None:
        """File context menu — push/sync/remove (per file_actions)."""
        is_pushed = self._tree.is_pushed(node.path)

        if not is_pushed and "push" in self._config.file_actions:
            push_action = QAction("Push", menu)
            push_action.triggered.connect(
                lambda: self._model.pushToggleRequested.emit(node.path, True),
            )
            menu.addAction(push_action)
        elif is_pushed:
            if "push" in self._config.file_actions:
                sync_action = QAction("Sync", menu)
                sync_action.triggered.connect(
                    lambda: self.syncRequested.emit(node.path),
                )
                menu.addAction(sync_action)
            if "remove" in self._config.file_actions:
                remove_action = QAction("Remove", menu)
                remove_action.triggered.connect(
                    lambda: self._model.pushToggleRequested.emit(node.path, False),
                )
                menu.addAction(remove_action)

    def _build_multi_select_file_menu(
        self, menu: QMenu, file_nodes: list[MountDataNode],
    ) -> None:
        """Multi-select file context menu — batch push/remove."""
        all_pushed = all(
            self._tree.is_in_raw_set("pushed", n.path) for n in file_nodes
        )
        none_pushed = all(
            not self._tree.is_in_raw_set("pushed", n.path) for n in file_nodes
        )

        if none_pushed and "push" in self._config.file_actions:
            push_action = QAction(f"Push ({len(file_nodes)} files)", menu)
            push_action.triggered.connect(
                lambda: self._batch_toggle(file_nodes, True),
            )
            menu.addAction(push_action)
        elif all_pushed and "remove" in self._config.file_actions:
            remove_action = QAction(f"Remove ({len(file_nodes)} files)", menu)
            remove_action.triggered.connect(
                lambda: self._batch_toggle(file_nodes, False),
            )
            menu.addAction(remove_action)
        else:
            info = QAction(
                f"{len(file_nodes)} files (mixed push states)", menu,
            )
            info.setEnabled(False)
            menu.addAction(info)

    # ── Batch File Operations ─────────────────────────────────────

    def _batch_toggle(self, nodes: list[MountDataNode], toggle_value: bool) -> None:
        """Batch toggle multiple files via pushToggleRequested signals."""
        self._tree.begin_batch()
        for node in nodes:
            self._model.pushToggleRequested.emit(node.path, toggle_value)
        self._tree.end_batch()
        self._clear_selection()

    # ── Toggle Helpers ────────────────────────────────────────────

    def _add_checkable_action(
        self, menu: QMenu, label: str, set_name: str,
        column: int, can_check_fn, node: MountDataNode,
    ) -> QAction:
        """Add a checkable context menu action for a folder toggle column."""
        action = QAction(label, menu)
        action.setCheckable(True)
        action.setChecked(self._tree.is_in_raw_set(set_name, node.path))
        action.setEnabled(
            can_check_fn(node.path)
            or self._tree.is_in_raw_set(set_name, node.path)
        )
        action.triggered.connect(
            lambda checked: self._toggle_single(node, column, checked),
        )
        menu.addAction(action)
        return action

    def _toggle_single(
        self, node: MountDataNode, column: int, checked: bool,
    ) -> None:
        """Toggle a single node via model.setData()."""
        check_state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        index = self._model.createIndex(node.row, column, node)
        self._model.setData(index, check_state, Qt.ItemDataRole.CheckStateRole)
        self._clear_selection()

    def _toggle_multi(
        self, nodes: list[MountDataNode], column: int, checked: bool,
    ) -> None:
        """Batch toggle multiple nodes with suppressed intermediate signals."""
        check_state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self._tree.begin_batch()
        for node in nodes:
            index = self._model.createIndex(node.row, column, node)
            self._model.setData(
                index, check_state, Qt.ItemDataRole.CheckStateRole,
            )
        self._tree.end_batch()
        self._clear_selection()

    def _clear_selection(self) -> None:
        self._tree_view.selectionModel().clearSelection()

    def _expand_recursive(self, index) -> None:
        """Expand a node and all its descendants."""
        self._tree_view.expand(index)
        model = self._tree_view.model()
        for row in range(model.rowCount(index)):
            child_index = model.index(row, 0, index)
            if child_index.isValid():
                self._expand_recursive(child_index)
