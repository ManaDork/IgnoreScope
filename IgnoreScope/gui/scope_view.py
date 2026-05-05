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
    QInputDialog,
    QMenu,
)

from .delegates import TreeStyleDelegate
from .display_filter_proxy import DisplayFilterProxy
from .mount_data_tree import MountDataTree, MountDataNode
from .mount_data_model import MountDataTreeModel
from .selection_coordinator import _ClickAwareTreeView
from .display_config import ScopeDisplayConfig
from .style_engine import ScopeHeaderSignals, resolve_scope_header_signals
from .view_helpers import configure_tree_view, apply_header_config


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


def _query_is_container_running(
    host_project_root: Optional[Path], scope_name: str,
) -> bool:
    """Return True iff the scope's docker container is running.

    Thin wrapper around ``get_container_info(docker_name)['running']`` for
    the Scope Config Tree header's 3-signal aggregate (Phase 3). Returns
    False for placeholder / empty scope and for missing containers — the
    header should show the "off" state in those cases.
    """
    if not host_project_root or not scope_name:
        return False
    from ..gui.app import PLACEHOLDER_SCOPE
    if scope_name == PLACEHOLDER_SCOPE:
        return False
    from ..docker.names import build_docker_name
    from ..docker.container_ops import get_container_info
    info = get_container_info(build_docker_name(host_project_root, scope_name))
    return bool(info and info.get("running", False))


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
    recreateRequested = pyqtSignal()

    def __init__(
        self, tree: MountDataTree, parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("scopeView")

        self._tree = tree
        self._config = ScopeDisplayConfig()
        self._model = MountDataTreeModel(tree, self._config)
        self._proxy = DisplayFilterProxy(self._model, self._config)
        self._tree_view = _ClickAwareTreeView()
        self._tree_view.setObjectName("scopeTree")

        self._setup_ui()
        self._connect_signals()
        # Drop tracked_path automatically on project/scope switch so a
        # stale outline doesn't follow the user into an unrelated tree.
        self._tree.structureChanged.connect(self._validate_tracked_path)

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
        # Re-render the container header's 3-signal encoding whenever
        # mount_specs mutate. refresh() recomputes both the dot prefix and
        # the QHeaderView stylesheet in one pass.
        self._tree.mountSpecsChanged.connect(self.refresh)

    # ── Public API ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Refresh the model after external data changes."""
        # Dynamic column 0 header: "{dot} Container: {scope} {status}"
        signals = self._compute_header_signals()
        scope_name = self._tree.current_scope
        status_suffix, show_pushed = _query_container_state(
            self._tree.host_project_root, scope_name,
        )
        suffix_part = f" {status_suffix}" if status_suffix else ""
        from ..gui.app import PLACEHOLDER_SCOPE
        show_dot = bool(scope_name) and scope_name != PLACEHOLDER_SCOPE
        dot_prefix = (
            f"{'●' if signals.container_running else '○'} " if show_dot else ""
        )
        header = (
            f"{dot_prefix}Container: {scope_name}{suffix_part}"
            if scope_name else "Container Scope"
        )
        self._config.columns[0] = dc_replace(self._config.columns[0], header=header)

        self._model.refresh()
        apply_header_config(self._tree_view, self._config.columns)
        self._apply_header_signals(signals)

        # Expand root
        root_index = self._proxy.index(0, 0)
        if root_index.isValid():
            self._tree_view.expand(root_index)

    @property
    def tree_view(self) -> QTreeView:
        """QTreeView access for external consumers."""
        return self._tree_view

    # ── Scope Config Tree Container Header (Phase 3) ──────────────

    def _compute_header_signals(self) -> ScopeHeaderSignals:
        """Compute the current 3-signal aggregate for this scope's container header.

        Queries live container state and composes ``ScopeHeaderSignals`` from
        the tree's unified ``mount_specs`` list (user + extension-synthesized).
        """
        running = _query_is_container_running(
            self._tree.host_project_root, self._tree.current_scope,
        )
        return resolve_scope_header_signals(
            running, self._tree.unified_mount_specs(),
        )

    def _apply_header_signals(self, signals: ScopeHeaderSignals) -> None:
        """Apply the 3-signal visual encoding to the Scope Config Tree header.

        ``fully_virtual`` → ``QHeaderView::section background-color`` reusing
        theme key ``visibility.virtual``.
        ``has_mounts``    → ``QHeaderView::section border-bottom`` = 3px solid
        ``config.mount``.
        ``container_running`` is rendered as a text-prefix dot on column 0
        (handled in ``refresh()``), not in the stylesheet — keeps the three
        channels orthogonal.
        """
        header = self._tree_view.header()
        rules: list[str] = []
        if signals.fully_virtual:
            color = self._config.color_vars.get("visibility.virtual")
            if color:
                rules.append(f"background-color: {color};")
        if signals.has_mounts:
            color = self._config.color_vars.get("config.mount")
            if color:
                rules.append(f"border-bottom: 3px solid {color};")
        if not rules:
            header.setStyleSheet("")
            return
        header.setStyleSheet("QHeaderView::section { " + " ".join(rules) + " }")

    # ── Header Context Menu ──────────────────────────────────────

    def _show_header_context_menu(self, pos: QPoint) -> None:
        """Header RMB: Start/Stop container, with Phase 2 silent-no-op fallback."""
        menu = QMenu(self)

        info = self._get_container_info()
        if info is not None:
            if info.get("running", False):
                stop_action = QAction("Stop Container", menu)
                stop_action.triggered.connect(self.stopContainerRequested.emit)
                menu.addAction(stop_action)
            else:
                start_action = QAction("Start Container", menu)
                start_action.triggered.connect(self.startContainerRequested.emit)
                menu.addAction(start_action)

        self._append_fallback_if_empty(menu)
        menu.exec(self._tree_view.header().mapToGlobal(pos))

    # ── Context Menu ──────────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint) -> None:
        index_at_pos = self._tree_view.indexAt(pos)
        selected_indexes = self._tree_view.selectionModel().selectedRows(0)

        menu = QMenu(self)

        # Empty area click — Scope Config gesture set.
        if not index_at_pos.isValid() or not selected_indexes:
            self._add_scope_config_gestures(menu, node=None)
            self._append_fallback_if_empty(menu)
            menu.exec(self._tree_view.viewport().mapToGlobal(pos))
            return

        nodes: list[MountDataNode] = []
        for idx in selected_indexes:
            source_idx = self._proxy.mapToSource(idx)
            node = source_idx.internalPointer()
            if node is not None:
                nodes.append(node)
        if not nodes:
            self._add_scope_config_gestures(menu, node=None)
            self._append_fallback_if_empty(menu)
            menu.exec(self._tree_view.viewport().mapToGlobal(pos))
            return

        if len(nodes) == 1:
            node = nodes[0]
            proxy_index = selected_indexes[0]
            any_spec = self._tree.get_any_spec_at(node.path)
            if (
                any_spec is not None
                and any_spec.delivery == "volume"
                and any_spec.owner.startswith("extension:")
            ):
                # Extension-owned volume specs are lifecycle-managed — read-only.
                # Empty menu falls through to _append_fallback_if_empty.
                pass
            elif node.is_file:
                self._build_file_menu(menu, node)
            elif self._tree.get_spec_at(node.path) is not None:
                self._add_scope_config_gestures(menu, node=node)
            else:
                self._build_folder_menu(menu, node, proxy_index)
        else:
            self._build_multi_select_menu(menu, nodes)

        self._append_fallback_if_empty(menu)
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

    # ── Scope Config Gesture State Machine ───────────────────────

    def _add_scope_config_gestures(
        self, menu: QMenu, node: Optional[MountDataNode],
    ) -> None:
        """Append the Scope Config Tree RMB state machine to ``menu``.

        States (UX labels; internal delivery/content_seed in parens):
          Empty-area / non-spec node:
            Make Folder                          (detached / folder, host_path=None)
            Make Permanent Folder ▸
                No Recreate                      (detached / folder, preserve_on_update=True)
                Volume Mount                     (volume / folder)
          Existing detached+folder spec:
            Mark Permanent | Unmark Permanent   (flip preserve_on_update)
            Remove
          Existing volume spec:
            Remove
        """
        if node is None:
            self._add_make_folder_actions(menu)
            return

        spec = self._tree.get_spec_at(node.path)
        if spec is None:
            self._add_make_folder_actions(menu)
            return

        if spec.delivery == "volume":
            a = menu.addAction("Remove")
            a.triggered.connect(lambda: self._on_remove_spec(node.path))
            return

        if spec.delivery == "detached" and spec.content_seed == "folder":
            if spec.preserve_on_update:
                a = menu.addAction("Unmark Permanent")
                a.triggered.connect(
                    lambda: self._tree.unmark_permanent(node.path),
                )
            else:
                a = menu.addAction("Mark Permanent")
                a.triggered.connect(
                    lambda: self._tree.mark_permanent(node.path),
                )
            menu.addSeparator()
            a = menu.addAction("Remove")
            a.triggered.connect(lambda: self._on_remove_spec(node.path))

    def _add_make_folder_actions(self, menu: QMenu) -> None:
        a = menu.addAction("Make Folder")
        a.triggered.connect(self._on_make_folder)

        perm_menu = menu.addMenu("Make Permanent Folder")
        a = perm_menu.addAction("No Recreate")
        a.triggered.connect(self._on_make_permanent_no_recreate)
        a = perm_menu.addAction("Volume Mount")
        a.triggered.connect(self._on_make_permanent_volume)

    # ── Scope Config Handlers ────────────────────────────────────

    def _on_make_folder(self) -> None:
        path = self._prompt_container_path(
            "Make Folder", "Container-side path:",
        )
        if path is None:
            return
        self._tree.add_stencil_folder(path, preserve_on_update=False)

    def _on_make_permanent_no_recreate(self) -> None:
        path = self._prompt_container_path(
            "Make Permanent Folder — No Recreate", "Container-side path:",
        )
        if path is None:
            return
        self._tree.add_stencil_folder(path, preserve_on_update=True)

    def _on_make_permanent_volume(self) -> None:
        path = self._prompt_container_path(
            "Make Permanent Folder — Volume Mount", "Container-side path:",
        )
        if path is None:
            return
        if self._tree.add_stencil_volume(path) and self._container_exists():
            # recreate_container (host-app slot) owns the destructive-action
            # confirmation dialog — richer wording than a bare "Continue?".
            self.recreateRequested.emit()

    def _on_remove_spec(self, path: Path) -> None:
        self._tree.remove_spec_at(path)

    # ── Dialog + Container Helpers ───────────────────────────────

    def _prompt_container_path(
        self, title: str, label: str,
    ) -> Optional[Path]:
        """QInputDialog prompt for a container-side absolute path.

        Returns None on cancel or empty input. Accepts any non-empty string;
        validator gates in LocalMountConfig reject bad paths.
        """
        text, accepted = QInputDialog.getText(self, title, label)
        if not accepted:
            return None
        stripped = text.strip()
        if not stripped:
            return None
        return Path(stripped)

    def _get_container_info(self) -> Optional[dict]:
        """Query the current scope's container info, returns None if absent."""
        scope_name = self._tree.current_scope
        if not scope_name:
            return None
        from ..gui.app import PLACEHOLDER_SCOPE
        if scope_name == PLACEHOLDER_SCOPE:
            return None
        host_root = self._tree.host_project_root
        if host_root is None:
            return None
        from ..docker.names import build_docker_name
        from ..docker.container_ops import get_container_info
        docker_name = build_docker_name(host_root, scope_name)
        return get_container_info(docker_name)

    def _container_exists(self) -> bool:
        return self._get_container_info() is not None

    def _append_fallback_if_empty(self, menu: QMenu) -> None:
        """Phase 2 silent-no-op fix: menus always exec with a discoverable entry."""
        if menu.actions():
            return
        placeholder = QAction("No valid actions", menu)
        placeholder.setEnabled(False)
        menu.addAction(placeholder)

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

    def _validate_tracked_path(self) -> None:
        """Drop stale tracked-paths after project switch / scope switch / clear.

        Wired to `tree.structureChanged` so a tracked_paths set that points
        outside the new root (or has no root at all) is cleared — otherwise
        the delegate retains a phantom outline on an unrelated row in the
        new project.
        """
        if not self._delegate._tracked_paths:
            return
        root = self._tree.root_node
        if root is None:
            self.set_tracked_paths([])
            return
        kept = []
        for p in self._delegate._tracked_paths:
            try:
                p.relative_to(root.path)
                kept.append(p)
            except ValueError:
                pass
        if len(kept) != len(self._delegate._tracked_paths):
            self.set_tracked_paths(kept)

    def set_tracked_paths(self, paths) -> None:
        """Update the tracked-paths overlay (decoupled from selectionModel).

        Accepts an iterable of `Path` objects (may be empty to clear).
        Walks the tree expanding only ANCESTORS of each path so each row
        is reachable, then stores all paths in the delegate's set. Paint
        renders one outline per tracked path. Scope's own user-driven
        selection is left untouched.

        Used by `app.py`'s `LocalHostView.selectionChangedPaths -> set_tracked_paths`
        chain — fires on every LocalHost selection-set change including
        clears (empty list).
        """
        paths_list = [p for p in paths if p is not None]
        self._delegate.set_tracked_paths(paths_list)

        if not paths_list:
            self._tree_view.viewport().update()
            return

        root_node = self._tree.root_node
        if root_node is None:
            self._tree_view.viewport().update()
            return

        # For each tracked path: expand its ancestors. Track the first matched
        # proxy index so we scroll to it (showing the user where the new
        # selection landed in Scope without forcing a scroll-jump per path).
        first_matched = QModelIndex()
        model = self._proxy
        for path in paths_list:
            try:
                rel = path.relative_to(root_node.path)
            except ValueError:
                continue
            parts = rel.parts
            if not parts:
                continue
            current_parent = QModelIndex()
            matched = QModelIndex()
            last_idx = len(parts) - 1
            for i, part in enumerate(parts):
                found = False
                for row in range(model.rowCount(current_parent)):
                    child_proxy = model.index(row, 0, current_parent)
                    if not child_proxy.isValid():
                        continue
                    source_idx = self._proxy.mapToSource(child_proxy)
                    node = source_idx.internalPointer()
                    if node is not None and node.path.name == part:
                        # Expand ancestors only; leave the final matched
                        # folder closed (Bug 3 contract). Chevron-mirror
                        # chain (Change B) handles explicit expansion.
                        if i < last_idx:
                            self._tree_view.expand(child_proxy)
                        current_parent = child_proxy
                        matched = child_proxy
                        found = True
                        break
                if not found:
                    break
            if matched.isValid() and not first_matched.isValid():
                first_matched = matched

        if first_matched.isValid():
            self._tree_view.scrollTo(first_matched)
        self._tree_view.viewport().update()

    # Single-path convenience wrapper — used internally by _validate and
    # callers that only have one path. Routes to the set form.
    def set_tracked_path(self, path: Optional[Path]) -> None:
        """Set a single tracked path (or clear with None). Wraps set_tracked_paths."""
        self.set_tracked_paths([path] if path is not None else [])

    # Backwards-compat alias — kept for any stale external callers.
    def expand_to_path(self, path: Path) -> None:
        """DEPRECATED — use `set_tracked_path` / `set_tracked_paths`."""
        self.set_tracked_path(path)

    # ── Branch-Indicator Mirror Chain ─────────────────────────────
    #
    # `expand_path` / `collapse_path` mirror LocalHost's branch-indicator
    # toggles (see LocalHostView.folderExpanded / folderCollapsed).
    # Icon-agnostic — works regardless of how the indicator renders
    # (currently a small square placeholder; chevron icon work tracked
    # separately). One-way chain: LocalHost drives Scope. NO reverse
    # mirror, so no re-entry guard is needed; if Scope→LocalHost is
    # ever added, a guard MUST be introduced to prevent feedback loops.

    def expand_path(self, path: Path) -> None:
        """Expand the proxy row matching `path` (and all ancestors).

        Walks the tree, calling `_tree_view.expand` on each matched part
        INCLUDING the final folder. Used by the LocalHost→Scope mirror
        chain for explicit user expand. Does NOT touch tracked_paths or
        selection. Silently no-ops if path is outside root or filter-rejected.
        """
        target = self._walk_to_path(path, expand_during_walk=True)
        # `target` is the final matched proxy index; the walk already
        # called expand on each part. Nothing else needed.

    def collapse_path(self, path: Path) -> None:
        """Collapse the proxy row matching `path`.

        Walks the tree without expanding, then collapses the matched
        final folder. Used by the LocalHost→Scope mirror chain for
        explicit user collapse. Does NOT touch tracked_paths or selection.
        Silently no-ops if path is outside root or filter-rejected.
        """
        target = self._walk_to_path(path, expand_during_walk=False)
        if target.isValid():
            self._tree_view.collapse(target)

    def _walk_to_path(
        self, path: Path, *, expand_during_walk: bool,
    ) -> QModelIndex:
        """Walk the proxy tree to find the row matching `path`.

        Returns the final matched proxy QModelIndex (or invalid if any
        part doesn't match — e.g., path outside root, lazy-not-loaded
        ancestor, or filter-rejected row). When `expand_during_walk` is
        True, calls `_tree_view.expand` on each matched part during the
        walk (used by `expand_path`); when False, walks without expanding
        (used by `collapse_path`).
        """
        root_node = self._tree.root_node
        if root_node is None:
            return QModelIndex()
        try:
            rel = path.relative_to(root_node.path)
        except ValueError:
            return QModelIndex()
        parts = rel.parts
        if not parts:
            return QModelIndex()

        current_parent = QModelIndex()
        model = self._proxy
        matched = QModelIndex()
        for part in parts:
            # Trigger lazy-load if children haven't been fetched yet so the
            # walk can see deeper subtrees that haven't been expanded by the
            # user. Required for both expand_path / collapse_path / tracking
            # of paths inside not-yet-fetched subdirs.
            if model.canFetchMore(current_parent):
                model.fetchMore(current_parent)
            found = False
            for row in range(model.rowCount(current_parent)):
                child_proxy = model.index(row, 0, current_parent)
                if not child_proxy.isValid():
                    continue
                source_idx = self._proxy.mapToSource(child_proxy)
                node = source_idx.internalPointer()
                if node is not None and node.path.name == part:
                    if expand_during_walk:
                        self._tree_view.expand(child_proxy)
                    current_parent = child_proxy
                    matched = child_proxy
                    found = True
                    break
            if not found:
                return QModelIndex()
        return matched

    # ── Helpers ───────────────────────────────────────────────────

    def _expand_recursive(self, index) -> None:
        """Expand a node and all its descendants."""
        self._tree_view.expand(index)
        model = self._tree_view.model()
        for row in range(model.rowCount(index)):
            child_index = model.index(row, 0, index)
            if child_index.isValid():
                self._expand_recursive(child_index)
