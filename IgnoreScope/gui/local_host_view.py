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
from .display_config import LocalHostDisplayConfig
from .view_helpers import configure_tree_view, apply_header_config


# Column indices matching LocalHostDisplayConfig.columns order
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

        self.setObjectName("localHostView")
        self._tree = tree
        self._config = LocalHostDisplayConfig()
        self._model = MountDataTreeModel(tree, self._config)
        self._proxy = DisplayFilterProxy(self._model, self._config)
        self._tree_view = QTreeView()
        self._tree_view.setObjectName("localHostTree")

        self._setup_ui()
        self._connect_signals()

    # ── UI Setup ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setObjectName("localHost_viewLayout")
        layout.setContentsMargins(0, 0, 0, 0)

        self._delegate = TreeStyleDelegate(self._config, self._tree_view)
        configure_tree_view(
            self._tree_view, self._proxy, self._delegate,
            self._config.columns, self._show_context_menu,
        )

        header = self._tree_view.header()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)

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

    # ── Header Context Menu ──────────────────────────────────────

    def _show_header_context_menu(self, pos: QPoint) -> None:
        """Header RMB: toggle mount for host_project_root."""
        root = self._tree.host_project_root
        if root is None:
            return

        menu = QMenu(self)
        is_mounted = self._tree.is_in_raw_set("mounted", root)
        label = f"Unmount {root.name}" if is_mounted else f"Mount {root.name}"
        mount_action = QAction(label, menu)
        mount_action.triggered.connect(
            lambda: self._tree.toggle_mounted(root, not is_mounted),
        )
        menu.addAction(mount_action)
        menu.exec(self._tree_view.header().mapToGlobal(pos))

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
        state = self._tree.get_node_state(path)

        if not node.is_file:
            # ── Folder actions — state-driven ──
            is_mounted = self._tree.is_in_raw_set("mounted", path)
            ms = self._tree._find_owning_spec(path)

            # Mount / Unmount
            if is_mounted:
                a = menu.addAction(f"Unmount {path.name}")
                a.triggered.connect(lambda: self._tree.toggle_mounted(path, False))
            elif self._tree.can_check_mounted(path):
                a = menu.addAction(f"Mount {path.name}")
                a.triggered.connect(lambda: self._tree.toggle_mounted(path, True))

            if ms and state:
                # Check if THIS folder has its own explicit pattern
                try:
                    rel = str(path.relative_to(ms.mount_root)).replace("\\", "/")
                except ValueError:
                    rel = None

                has_mask_pattern = rel and f"{rel}/" in ms.patterns
                has_reveal_pattern = rel and f"!{rel}/" in ms.patterns

                # Mask: allowed when mounted AND not already masked
                # Use has_reveal_pattern instead of state.revealed to allow nesting:
                # nodes revealed by ancestor (has_reveal_pattern=False, state.revealed=True)
                # can be masked (creating mask-within-reveal per architecture)
                can_mask = state.mounted and not state.masked and not has_reveal_pattern
                if has_mask_pattern:
                    a = menu.addAction(f"Unmask {path.name}")
                    a.triggered.connect(lambda: self._tree.remove_mask(path))
                elif can_mask and rel:
                    a = menu.addAction(f"Mask {path.name}")
                    a.triggered.connect(lambda: self._tree.add_mask(path))

                # Reveal: allowed when masked by ancestor (not own pattern) and no reveal pattern yet
                # Don't offer Reveal on folder with own mask pattern — use Unmask instead
                if has_reveal_pattern:
                    a = menu.addAction(f"Unreveal {path.name}")
                    a.triggered.connect(lambda: self._tree.remove_reveal(path))
                elif state.masked and rel and not has_mask_pattern:
                    a = menu.addAction(f"Reveal {path.name}")
                    a.triggered.connect(lambda: self._tree.add_reveal(path))

            menu.addSeparator()

        # ── File actions ──
        if node.is_file:
            is_pushed = self._tree.is_pushed(path)
            if is_pushed:
                remove_action = QAction("Remove from Container", menu)
                remove_action.triggered.connect(
                    lambda: self._model.pushToggleRequested.emit(path, False)
                )
                menu.addAction(remove_action)
            else:
                push_action = QAction("Push to Container", menu)
                push_action.triggered.connect(
                    lambda: self._model.pushToggleRequested.emit(path, True)
                )
                menu.addAction(push_action)
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
        count = len(nodes)
        folders = [n for n in nodes if not n.is_file]
        files = [n for n in nodes if n.is_file]

        # Folder batch actions
        if folders:
            mask_action = QAction(f"Mask ({len(folders)} folders)", menu)
            mask_action.triggered.connect(
                lambda: [self._tree.add_mask(n.path) for n in folders]
            )
            menu.addAction(mask_action)

            reveal_action = QAction(f"Reveal ({len(folders)} folders)", menu)
            reveal_action.triggered.connect(
                lambda: [self._tree.add_reveal(n.path) for n in folders]
            )
            menu.addAction(reveal_action)

        # File batch actions
        if files:
            if folders:
                menu.addSeparator()
            push_action = QAction(f"Push ({len(files)} files)", menu)
            push_action.triggered.connect(
                lambda: [self._model.pushToggleRequested.emit(n.path, True) for n in files]
            )
            menu.addAction(push_action)

        if not folders and not files:
            info = QAction(f"{count} items selected", menu)
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
