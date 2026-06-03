"""Local Host view — left panel showing folder configuration.

LocalHostView: QWidget wrapping a QTreeView + MountDataTreeModel with
LocalHostDisplayConfig. Shows folders with Mount/Mask/Reveal columns.
No undo integration (deferred to Logic phase — undo.py).
No TreeContext, no QProgressDialog, no UndoStack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QModelIndex
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
from .selection_coordinator import _ClickAwareTreeView
from dataclasses import replace as dc_replace
from .display_config import LocalHostDisplayConfig
from .view_helpers import configure_tree_view, apply_header_config, resolve_action_target


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
    selectionCleared = pyqtSignal()  # emitted when current index becomes invalid (legacy — see selectionChangedPaths)
    selectionChangedPaths = pyqtSignal(list)  # list[Path] of all selected rows; emitted on every selection-set change including clears (empty list)
    folderExpanded = pyqtSignal(Path)  # emitted when user toggles branch indicator on a folder (Bug 3 part 2 mirror chain)
    folderCollapsed = pyqtSignal(Path)  # symmetric to folderExpanded
    syncRequested = pyqtSignal(Path)
    removeSiblingRequested = pyqtSignal(object)  # Path emitted
    convertDeliveryRequested = pyqtSignal(object, str)  # (path, target)
    removeFromContainerRequested = pyqtSignal(object, bool)  # (path, recursive)

    def __init__(
        self, tree: MountDataTree, parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("localHostView")
        self._tree = tree
        self._config = LocalHostDisplayConfig()
        self._model = MountDataTreeModel(tree, self._config)
        self._proxy = DisplayFilterProxy(self._model, self._config)
        self._tree_view = _ClickAwareTreeView()
        self._tree_view.setObjectName("localHostTree")
        # Optional callable() -> bool, set by parent, indicates container exists.
        # When None, container-dependent gestures are hidden.
        self._container_exists_fn = None

        self._setup_ui()
        self._connect_signals()

    def set_container_exists_fn(self, fn) -> None:
        """Inject a zero-arg callable that returns True iff a container exists.

        Used to gate the container-dependent RMB gestures (Remove Folder
        from Container / Remove Folder Tree from Container). When the
        callable is None or returns False, those gestures are hidden.
        """
        self._container_exists_fn = fn

    def _container_exists(self) -> bool:
        if self._container_exists_fn is None:
            return False
        try:
            return bool(self._container_exists_fn())
        except Exception:
            return False

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
        # currentChanged drives the legacy nodeSelected/selectionCleared
        # path (single focused node — used by callers that need just the
        # current index, e.g., tooltip drivers).
        self._tree_view.selectionModel().currentChanged.connect(
            self._on_selection_changed,
        )
        # selectionChanged fires on EVERY change to the selection set,
        # including clearSelection() calls that don't move the current
        # index. Drives the multi-path tracked-overlay chain in ScopeView.
        self._tree_view.selectionModel().selectionChanged.connect(
            self._on_selection_set_changed,
        )
        # Branch-indicator mirror chain (Bug 3 part 2 — one-way LH → Scope).
        # Folder-only; files and stencil nodes are skipped at the handler.
        self._tree_view.expanded.connect(self._on_tree_expanded)
        self._tree_view.collapsed.connect(self._on_tree_collapsed)

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

    def reveal_path(self, path: Path) -> bool:
        """Scroll to and select the row for ``path`` in the local-host tree.

        Mirror of ``ScopeView.reveal_path``. Used by ``MarkedPushDialog``'s
        Reveal action so both panels light up when the user requests
        navigation — the local-host panel is where the host file lives,
        the scope panel shows the container's perspective; revealing in
        both gives consistent feedback regardless of where the user is
        looking.

        Walks the proxy from root toward the target, triggering
        ``fetchMore`` on lazy-loaded folders so the proxy mapping
        actually contains the deeper rows. Expands ancestor folders so
        the target row is reachable; leaves the target itself
        unexpanded. Falls back to revealing the deepest reachable
        ancestor when the exact path is filtered out (e.g., the file is
        under a mask), so the user lands at the closest visible context
        rather than nowhere.

        Returns True iff the exact path was revealed; False if only a
        partial ancestor match was reachable or the path is outside the
        project root.
        """
        root_node = self._tree.root_node
        if root_node is None:
            return False
        try:
            rel = path.relative_to(root_node.path)
        except ValueError:
            return False
        parts = rel.parts
        if not parts:
            return False

        model = self._proxy
        current_parent = QModelIndex()
        matched = QModelIndex()
        deepest = QModelIndex()
        last_idx = len(parts) - 1
        full_match = True
        for i, part in enumerate(parts):
            if self._proxy.canFetchMore(current_parent):
                self._proxy.fetchMore(current_parent)

            found = False
            for row in range(model.rowCount(current_parent)):
                child_proxy = model.index(row, 0, current_parent)
                if not child_proxy.isValid():
                    continue
                source_idx = self._proxy.mapToSource(child_proxy)
                node = source_idx.internalPointer()
                if node is not None and node.path.name == part:
                    if i < last_idx:
                        self._tree_view.expand(child_proxy)
                    current_parent = child_proxy
                    matched = child_proxy
                    deepest = child_proxy
                    found = True
                    break
            if not found:
                full_match = False
                break

        target = matched if full_match else deepest
        if not target.isValid():
            return False
        self._tree_view.scrollTo(target)
        self._tree_view.setCurrentIndex(target)
        return full_match

    @property
    def tree_view(self) -> QTreeView:
        """QTreeView access for external consumers."""
        return self._tree_view

    # ── Selection Sync ──────────────────────────────────────────

    def _on_selection_changed(self, current, previous) -> None:
        """Emit nodeSelected when current index becomes valid; emit selectionCleared otherwise.

        Driven by `currentChanged` — fires when the current (focused) row
        moves. Does NOT fire when only the selection set changes
        (e.g. clearSelection() called programmatically by the coordinator).
        For full-selection tracking, see `_on_selection_set_changed`.
        """
        if not current.isValid():
            self.selectionCleared.emit()
            return
        source_idx = self._proxy.mapToSource(current)
        node = source_idx.internalPointer()
        if node is not None:
            self.nodeSelected.emit(node.path)

    def _on_selection_set_changed(self, selected, deselected) -> None:
        """Emit selectionChangedPaths with the full set of currently-selected rows.

        Driven by `selectionChanged` — fires on EVERY selection-set change,
        including programmatic `clearSelection()` calls that leave the
        current index untouched. Carries `list[Path]` (may be empty).
        """
        sel_model = self._tree_view.selectionModel()
        paths: list[Path] = []
        for idx in sel_model.selectedRows(0):
            source_idx = self._proxy.mapToSource(idx)
            node = source_idx.internalPointer()
            if node is not None:
                paths.append(node.path)
        self.selectionChangedPaths.emit(paths)

    def _on_tree_expanded(self, proxy_index) -> None:
        """Emit folderExpanded(path) when user toggles a folder's branch indicator.

        Driven by `QTreeView.expanded` (Qt-built-in). Folder-only —
        files and stencil nodes do not emit. Powers the one-way
        LocalHost → Scope mirror chain (see ScopeView.expand_path).
        """
        if not proxy_index.isValid():
            return
        source_idx = self._proxy.mapToSource(proxy_index)
        node = source_idx.internalPointer()
        if node is None or node.is_file or node.is_stencil_node:
            return
        self.folderExpanded.emit(node.path)

    def _on_tree_collapsed(self, proxy_index) -> None:
        """Emit folderCollapsed(path); symmetric to _on_tree_expanded."""
        if not proxy_index.isValid():
            return
        source_idx = self._proxy.mapToSource(proxy_index)
        node = source_idx.internalPointer()
        if node is None or node.is_file or node.is_stencil_node:
            return
        self.folderCollapsed.emit(node.path)

    # ── Header Context Menu ──────────────────────────────────────

    def _show_header_context_menu(self, pos: QPoint) -> None:
        """Header RMB: full 6-gesture state machine scoped to host_project_root.

        When no gestures apply (e.g., the header path is an ancestor of an
        existing mount_spec), fall back to a disabled ``No valid actions``
        entry so the RMB is always discoverable.
        """
        root = self._tree.host_project_root
        if root is None:
            return

        menu = QMenu(self)
        self._add_delivery_gestures(menu, root)
        if not menu.actions():
            placeholder = QAction("No valid actions", menu)
            placeholder.setEnabled(False)
            menu.addAction(placeholder)
        menu.exec(self._tree_view.header().mapToGlobal(pos))

    def _add_delivery_gestures(self, menu: QMenu, path: Path) -> None:
        """Append the six-gesture delivery state machine to ``menu``.

        States (UX labels shown; internal delivery values in parens):
          NONE                  → Mount | Virtual Mount | Virtual Folder
          BIND_MOUNTED (bind)   → Unmount | Convert to Virtual Mount
          DETACHED_MOUNTED      → Remove Virtual Mount | Convert to Mount
                                  | Remove But Keep Children
                                  | (if container) Remove Folder from Container
                                  | (if container) Remove Folder Tree from Container

        Virtual Folder produces a host-backed folder-seed detached spec
        (``delivery="detached", content_seed="folder"``); content is mkdir'd
        in the container with no cp walk and is filled via ``pushed_files``
        or inside-container writes.
        """
        is_bind = self._tree.is_in_raw_set("mounted", path)
        is_detached = self._tree.is_in_raw_set("detached_mounted", path)

        if not is_bind and not is_detached:
            if self._tree.can_mount(path):
                a = menu.addAction(f"Mount {path.name}")
                a.triggered.connect(lambda: self._tree.toggle_mounted(path, True))
                a = menu.addAction(f"Virtual Mount {path.name}")
                a.triggered.connect(
                    lambda: self._tree.toggle_detached_mount(path, True),
                )
                a = menu.addAction(f"Virtual Folder {path.name}")
                a.triggered.connect(
                    lambda: self._tree.toggle_detached_folder_mount(path, True),
                )
        elif is_bind:
            a = menu.addAction(f"Unmount {path.name}")
            a.triggered.connect(lambda: self._tree.toggle_mounted(path, False))
            a = menu.addAction("Convert to Virtual Mount")
            a.triggered.connect(
                lambda: self.convertDeliveryRequested.emit(path, "detached"),
            )
        elif is_detached:
            a = menu.addAction(f"Remove Virtual Mount {path.name}")
            a.triggered.connect(
                lambda: self._tree.toggle_detached_mount(path, False),
            )
            a = menu.addAction("Convert to Mount")
            a.triggered.connect(
                lambda: self.convertDeliveryRequested.emit(path, "bind"),
            )
            a = menu.addAction("Remove But Keep Children")
            a.triggered.connect(
                lambda: self._tree.remove_but_keep_children(path),
            )
            if self._container_exists():
                menu.addSeparator()
                a = menu.addAction("Remove Folder from Container")
                a.triggered.connect(
                    lambda: self.removeFromContainerRequested.emit(path, False),
                )
                a = menu.addAction("Remove Folder Tree from Container")
                a.triggered.connect(
                    lambda: self.removeFromContainerRequested.emit(path, True),
                )

    # ── Context Menu ──────────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint) -> None:
        """Cursor-primary RMB: indexAt(pos) drives the action target.

        See `view_helpers.resolve_action_target` for the cursor-vs-selection
        precedence rules. RMB on an unselected row operates on that row
        alone; RMB on a selected row with active multi-select operates on
        the full selection. Empty-area click is a silent no-op (LocalHost
        has no empty-area menu — that's a Scope concept).
        """
        index_at_pos, nodes = resolve_action_target(
            self._tree_view, self._proxy, pos,
        )
        if not index_at_pos.isValid() or not nodes:
            return

        menu = QMenu(self)
        if len(nodes) == 1:
            node = nodes[0]
            if node.is_file:
                self._build_file_menu(menu, node)
            else:
                # Pass proxy index for expand/collapse operations
                self._build_single_select_menu(menu, node, index_at_pos)
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
        if not menu.actions():
            placeholder = QAction("No valid actions", menu)
            placeholder.setEnabled(False)
            menu.addAction(placeholder)
        menu.exec(self._tree_view.viewport().mapToGlobal(pos))

    def _build_single_select_menu(
        self, menu: QMenu, node: MountDataNode, index,
    ) -> None:
        path = node.path
        state = self._tree.get_node_state(path)

        if not node.is_file:
            # ── Folder actions — 6-gesture delivery state machine ──
            self._add_delivery_gestures(menu, path)

            ms = self._tree._find_owning_spec(path)
            if ms and state:
                # Check if THIS folder has its own explicit pattern.
                # `as_posix()` returns canonical forward-slash form across
                # platforms — replaces the prior str(...).replace("\\","/")
                # which was platform-specific string manipulation.
                try:
                    rel = path.relative_to(ms.mount_root).as_posix()
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

        # Batch Remove Virtual Mount when all selected folders are detached-mounted
        if folders and all(
            self._tree.is_in_raw_set("detached_mounted", n.path) for n in folders
        ):
            remove_vm_action = QAction(
                f"Remove Virtual Mount ({len(folders)} folders)", menu,
            )
            remove_vm_action.triggered.connect(
                lambda: [
                    self._tree.toggle_detached_mount(n.path, False) for n in folders
                ]
            )
            menu.addAction(remove_vm_action)
            menu.addSeparator()

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
