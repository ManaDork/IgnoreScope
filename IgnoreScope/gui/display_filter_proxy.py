"""Display Filter Proxy for tree views.

QSortFilterProxyModel that enforces TreeDisplayConfig filter booleans
(display_files, display_virtual_nodes, display_hidden, display_orphaned,
display_non_mounted, display_masked_dead_branches). Sits between
MountDataTreeModel and QTreeView.

Standard Qt proxy pattern — handles row index mapping and parent
remapping automatically. No recursive filtering: if a parent is
rejected, its children are hidden too (correct for container perspective).
"""

from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QSortFilterProxyModel, QTimer

from .display_config import TreeDisplayConfig
from .mount_data_model import MountDataTreeModel
from .mount_data_tree import MountDataNode


class DisplayFilterProxy(QSortFilterProxyModel):
    """Proxy that filters tree rows based on TreeDisplayConfig booleans.

    Constructor connects source_model.stateChanged to invalidateFilter
    so the proxy re-evaluates visibility whenever CORE state changes.
    """

    def __init__(
        self,
        source_model: MountDataTreeModel,
        config: TreeDisplayConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self.setSourceModel(source_model)

        # Re-filter when tree state changes (deferred to next event loop cycle).
        # Direct invalidateFilter() inside the setData→stateChanged call stack
        # rebuilds proxy mapping mid-paint, causing access violations on stale
        # indices. QTimer(0) defers to next cycle; rapid changes coalesce.
        # See: MEMORY.md → "Qt Proxy invalidateFilter Crash Pattern"
        self._invalidate_timer = QTimer(self)
        self._invalidate_timer.setSingleShot(True)
        self._invalidate_timer.setInterval(0)
        self._invalidate_timer.timeout.connect(self.invalidateFilter)
        source_model.stateChanged.connect(self._invalidate_timer.start)

    def begin_batch(self) -> None:
        """Forward batch begin to source model."""
        self.sourceModel().begin_batch()

    def end_batch(self) -> None:
        """Forward batch end to source model."""
        self.sourceModel().end_batch()

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex,
    ) -> bool:
        """Check all 6 filter booleans against the node at source_row."""
        source_index = self.sourceModel().index(source_row, 0, source_parent)
        if not source_index.isValid():
            return False

        node: MountDataNode = source_index.internalPointer()
        if node is None:
            return False

        # ── File filter ───────────────────────────────────────
        if not self._config.display_files and node.is_file:
            return False

        # ── Virtual node filter ───────────────────────────────
        if not self._config.display_virtual_nodes and node.is_virtual:
            return False

        # State-dependent filters require CORE state
        source_model: MountDataTreeModel = self.sourceModel()
        state = source_model.tree.get_node_state(node.path)

        # ── Hidden filter ─────────────────────────────────────
        if not self._config.display_hidden and state.visibility == "hidden":
            if not state.pushed and not state.has_pushed_descendant:
                return False

        # ── Orphaned filter ───────────────────────────────────
        if not self._config.display_orphaned and state.visibility == "orphaned":
            return False

        # ── Non-mounted folder filter ─────────────────────────
        if (
            not self._config.display_non_mounted
            and not node.is_file
            and not state.mounted
            and state.visibility == "hidden"
        ):
            if not state.pushed and not state.has_pushed_descendant:
                return False

        # ── Masked dead branch filter ─────────────────────────
        if (
            not self._config.display_masked_dead_branches
            and not node.is_file
            and state.visibility == "masked"
            and not state.has_direct_visible_child
            and not state.has_pushed_descendant
        ):
            return False

        return True
