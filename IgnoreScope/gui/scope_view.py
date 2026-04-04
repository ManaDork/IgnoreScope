"""Scope View — right panel showing container file view.

ScopeView: QWidget wrapping a QTreeView + MountDataTreeModel with
ScopeDisplayConfig. Shows files and folders visible in the container.
All file operations (Push/Remove) via RMB context menu + signal emission.

No TreeContext, no UndoStack, no QProgressDialog.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QModelIndex
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeView,
    QHeaderView,
    QAbstractItemView,
    QMenu,
)

from .delegates import TreeStyleDelegate
from .display_filter_proxy import DisplayFilterProxy
from .mount_data_tree import MountDataTree, MountDataNode
from .mount_data_model import MountDataTreeModel
from .display_config import ScopeDisplayConfig
from .view_helpers import configure_tree_view, apply_header_config


# Column index matching ScopeDisplayConfig.columns order
_COL_PUSH = 1


def _query_container_state(
    host_project_root: Optional[Path], scope_name: str,
) -> tuple[str, bool]:
    """Query container state for header display.

    Returns:
        (status_suffix, show_pushed_column)
        status_suffix: "-not created", "-running", "-stopped", or ""
        show_pushed_column: True only when container exists AND is running
    """
    if not host_project_root or not scope_name:
        return ("", False)
    from ..gui.app import PLACEHOLDER_SCOPE
    if scope_name == PLACEHOLDER_SCOPE:
        return ("", False)
    from ..docker.names import build_docker_name
    from ..docker.container_ops import get_container_info
    docker_name = build_docker_name(host_project_root, scope_name)
    info = get_container_info(docker_name)
    if info is None:
        return ("-not created", False)
    if info.get("running", False):
        return ("-running", True)
    return ("-stopped", False)


class ScopeView(QWidget):
    """Right panel: container view. Push/Remove via RMB.

    File operations (push/pull/remove) are emitted as signals.
    FileOperationsHandler (Logic phase) will connect to them.

    Signals:
        stateChanged: Forwarded from model for app-level handlers.
        pushRequested(Path): Push file to container via docker cp.
        updateRequested(Path): Re-push (overwrite) in container.
        pullRequested(Path): Copy from container to host.
        removeRequested(Path): Remove from container.
    """

    stateChanged = pyqtSignal()
    pushRequested = pyqtSignal(Path)
    updateRequested = pyqtSignal(Path)
    pullRequested = pyqtSignal(Path)
    removeRequested = pyqtSignal(Path)
    startContainerRequested = pyqtSignal()
    stopContainerRequested = pyqtSignal()

    def __init__(
        self, tree: MountDataTree, parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("scopeView")

        self._tree = tree
        self._config = ScopeDisplayConfig()
        self._model = MountDataTreeModel(tree, self._config)
        self._proxy = DisplayFilterProxy(self._model, self._config)
        self._tree_view = QTreeView()
        self._tree_view.setObjectName("scopeTree")

        self._setup_ui()
        self._connect_signals()

    # ── UI Setup ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setObjectName("scope_viewLayout")
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

    # ── Public API ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Refresh the model after external data changes."""
        # Dynamic column 0 header: "Container: {scope} {status}"
        scope_name = self._tree.current_scope
        status_suffix, show_pushed = _query_container_state(
            self._tree.host_project_root, scope_name,
        )
        suffix_part = f" {status_suffix}" if status_suffix else ""
        header = f"Container: {scope_name}{suffix_part}" if scope_name else "Container Scope"
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

    # ── Header Context Menu ──────────────────────────────────────

    def _show_header_context_menu(self, pos: QPoint) -> None:
        """Header RMB: Start/Stop container based on current state."""
        scope_name = self._tree.current_scope
        if not scope_name:
            return
        from ..gui.app import PLACEHOLDER_SCOPE
        if scope_name == PLACEHOLDER_SCOPE:
            return

        from ..docker.names import build_docker_name
        from ..docker.container_ops import get_container_info
        docker_name = build_docker_name(self._tree.host_project_root, scope_name)
        info = get_container_info(docker_name)
        if info is None:
            return

        menu = QMenu(self)
        if info.get("running", False):
            stop_action = QAction("Stop Container", menu)
            stop_action.triggered.connect(self.stopContainerRequested.emit)
            menu.addAction(stop_action)
        else:
            start_action = QAction("Start Container", menu)
            start_action.triggered.connect(self.startContainerRequested.emit)
            menu.addAction(start_action)

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
            proxy_index = selected_indexes[0]
            if node.is_file:
                self._build_file_menu(menu, node)
            else:
                self._build_folder_menu(menu, node, proxy_index)
        else:
            self._build_multi_select_menu(menu, nodes)

        if menu.actions():
            menu.exec(self._tree_view.viewport().mapToGlobal(pos))

    def _build_file_menu(self, menu: QMenu, node: MountDataNode) -> None:
        """File context menu — state-dependent push/update/pull/remove."""
        is_pushed = self._tree.is_pushed(node.path)
        is_container = self._tree.is_container_file(node.path)

        if not is_pushed and not is_container:
            push_action = QAction("Push", menu)
            push_action.triggered.connect(lambda: self._on_push(node.path))
            menu.addAction(push_action)
        elif is_pushed or is_container:
            update_action = QAction("Sync", menu)
            update_action.triggered.connect(
                lambda: self._on_update(node.path),
            )
            menu.addAction(update_action)

            pull_action = QAction("Pull", menu)
            pull_action.triggered.connect(lambda: self._on_pull(node.path))
            menu.addAction(pull_action)

            remove_action = QAction("Remove", menu)
            remove_action.triggered.connect(
                lambda: self._on_remove(node.path),
            )
            menu.addAction(remove_action)

    def _build_folder_menu(
        self, menu: QMenu, node: MountDataNode, index,
    ) -> None:
        """Folder context menu — navigation + scan placeholder."""
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

        menu.addSeparator()

        scan_action = QAction("Scan for New Files", menu)
        scan_action.setEnabled(False)
        scan_action.setToolTip("Query container to find files created inside")
        menu.addAction(scan_action)

    def _build_multi_select_menu(
        self, menu: QMenu, nodes: list[MountDataNode],
    ) -> None:
        """Multi-select context menu — batch Push/Remove for files."""
        # Filter to files only (folders don't have Push checkbox)
        file_nodes = [n for n in nodes if n.is_file]
        if not file_nodes:
            info = QAction(
                f"{len(nodes)} folders selected (no file actions)", menu,
            )
            info.setEnabled(False)
            menu.addAction(info)
            return

        # Push — uniform state check
        all_pushed = all(
            self._tree.is_in_raw_set("pushed", n.path) for n in file_nodes
        )
        none_pushed = all(
            not self._tree.is_in_raw_set("pushed", n.path) for n in file_nodes
        )

        if none_pushed:
            # All unpushed — offer batch push
            push_action = QAction(f"Push ({len(file_nodes)} files)", menu)
            push_action.triggered.connect(
                lambda: self._batch_toggle(file_nodes, True),
            )
            menu.addAction(push_action)
        elif all_pushed:
            # All pushed — offer batch remove
            remove_action = QAction(f"Remove ({len(file_nodes)} files)", menu)
            remove_action.triggered.connect(
                lambda: self._batch_toggle(file_nodes, False),
            )
            menu.addAction(remove_action)
        else:
            # Mixed states — no toggle action
            info = QAction(
                f"{len(file_nodes)} files (mixed push states)", menu,
            )
            info.setEnabled(False)
            menu.addAction(info)

    # ── Batch Operations ──────────────────────────────────────────

    def _batch_toggle(self, nodes: list[MountDataNode], toggle_value: bool) -> None:
        """Batch toggle multiple files via pushToggleRequested signals."""
        self._tree.begin_batch()
        for node in nodes:
            self._model.pushToggleRequested.emit(node.path, toggle_value)
        self._tree.end_batch()
        self._clear_selection()

    def _clear_selection(self) -> None:
        self._tree_view.selectionModel().clearSelection()

    # ── File Operation Emitters ───────────────────────────────────

    def _on_push(self, path: Path) -> None:
        self.pushRequested.emit(path)

    def _on_update(self, path: Path) -> None:
        self.updateRequested.emit(path)

    def _on_pull(self, path: Path) -> None:
        self.pullRequested.emit(path)

    def _on_remove(self, path: Path) -> None:
        self.removeRequested.emit(path)

    # ── Selection Sync ────────────────────────────────────────────

    def expand_to_path(self, path: Path) -> None:
        """Expand tree to show a path, select and scroll to it.

        Walks proxy indices from invisible root, expanding each level
        until the target path is found or the walk runs out of matches.
        """
        root_node = self._tree.root_node
        if root_node is None:
            return
        try:
            rel = path.relative_to(root_node.path)
        except ValueError:
            return
        parts = rel.parts
        if not parts:
            return

        current_parent = QModelIndex()  # invisible root
        model = self._proxy
        matched = QModelIndex()

        for part in parts:
            found = False
            for row in range(model.rowCount(current_parent)):
                child_proxy = model.index(row, 0, current_parent)
                if not child_proxy.isValid():
                    continue
                source_idx = self._proxy.mapToSource(child_proxy)
                node = source_idx.internalPointer()
                if node is not None and node.path.name == part:
                    self._tree_view.expand(child_proxy)
                    current_parent = child_proxy
                    matched = child_proxy
                    found = True
                    break
            if not found:
                break

        if matched.isValid():
            self._tree_view.selectionModel().setCurrentIndex(
                matched,
                self._tree_view.selectionModel().SelectionFlag.ClearAndSelect
                | self._tree_view.selectionModel().SelectionFlag.Rows,
            )
            self._tree_view.scrollTo(matched)

    # ── Helpers ───────────────────────────────────────────────────

    def _expand_recursive(self, index) -> None:
        """Expand a node and all its descendants."""
        self._tree_view.expand(index)
        model = self._tree_view.model()
        for row in range(model.rowCount(index)):
            child_index = model.index(row, 0, index)
            if child_index.isValid():
                self._expand_recursive(child_index)
