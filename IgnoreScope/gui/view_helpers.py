"""Shared tree view setup helpers.

Eliminates duplicated QTreeView configuration and header setup
between LocalHostView and ScopeView. Also hosts `resolve_action_target`
— the cursor-primary RMB resolution helper used by both views.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from PyQt6.QtCore import Qt, QPoint, QModelIndex
from PyQt6.QtWidgets import (
    QTreeView,
    QHeaderView,
    QAbstractItemView,
)

from .display_config import ColumnDef

if TYPE_CHECKING:
    from .mount_data_tree import MountDataNode


def configure_tree_view(
    tree_view: QTreeView,
    proxy,
    delegate,
    columns: list[ColumnDef],
    context_menu_handler: Callable[[QPoint], None],
) -> None:
    """Apply standard tree view configuration shared by all tree panels.

    Sets model, delegate, selection behavior, context menu policy,
    and header column widths/visibility from ColumnDef list.

    Args:
        tree_view: Target QTreeView to configure.
        proxy: Proxy model to set on the view.
        delegate: Item delegate to set on the view.
        columns: ColumnDef list for header configuration.
        context_menu_handler: Slot for customContextMenuRequested signal.
    """
    tree_view.setModel(proxy)
    tree_view.setAlternatingRowColors(False)
    tree_view.setItemDelegate(delegate)
    tree_view.setSelectionMode(
        QAbstractItemView.SelectionMode.ExtendedSelection,
    )
    tree_view.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows,
    )
    tree_view.setUniformRowHeights(True)
    tree_view.setAnimated(True)
    tree_view.setSortingEnabled(False)
    tree_view.setExpandsOnDoubleClick(True)
    tree_view.setIndentation(20)

    tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    tree_view.customContextMenuRequested.connect(context_menu_handler)

    apply_header_config(tree_view, columns)


def apply_header_config(
    tree_view: QTreeView,
    columns: list[ColumnDef],
) -> None:
    """Apply column widths and visibility from ColumnDef list.

    Args:
        tree_view: Target QTreeView.
        columns: ColumnDef list defining header layout.
    """
    header = tree_view.header()
    header.setStretchLastSection(False)
    for i, col_def in enumerate(columns):
        if col_def.width == "stretch":
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(i, col_def.width)
        tree_view.setColumnHidden(i, not col_def.visible)


def resolve_action_target(
    tree_view: QTreeView, proxy, pos: QPoint,
) -> tuple[QModelIndex, list]:
    """Cursor-primary RMB resolution — the file-manager UX pattern.

    Returns ``(index_at_pos, action_target_nodes)`` where:

    - ``index_at_pos`` is the proxy index at the cursor (may be invalid
      → empty-area click).
    - ``action_target_nodes`` is the list of `MountDataNode` instances
      the menu should operate on, computed as:
        * empty list if cursor is on empty area or maps to nothing
        * [cursor_node] if the cursor target is NOT in the current
          selection, OR if there is no multi-select (selection size <= 1).
          This is the unselected-row-RMB case AND the selected-single-row
          case — both target the cursor row only.
        * [...all selected nodes...] if the cursor target IS in the
          current selection AND len(selection) > 1 — multi-select RMB
          extends to all selected rows.

    This decouples "what was clicked" from "what was selected" and
    matches the standard file-manager pattern: RMB on an unselected
    row operates on that row alone; RMB on a selected row operates
    on the entire selection set when there is one.
    """
    index_at_pos = tree_view.indexAt(pos)
    if not index_at_pos.isValid():
        return index_at_pos, []

    target_source = proxy.mapToSource(index_at_pos)
    target_node = target_source.internalPointer()
    if target_node is None:
        return index_at_pos, []

    selected = tree_view.selectionModel().selectedRows(0)
    if len(selected) <= 1:
        return index_at_pos, [target_node]

    selected_paths: set = set()
    for idx in selected:
        s = proxy.mapToSource(idx)
        n = s.internalPointer()
        if n is not None:
            selected_paths.add(n.path)

    if target_node.path not in selected_paths:
        # Cursor row is OUTSIDE the current multi-select — operate on cursor only.
        return index_at_pos, [target_node]

    # Cursor row IS in the multi-select — extend to the full selection.
    nodes: list = []
    for idx in selected:
        s = proxy.mapToSource(idx)
        n = s.internalPointer()
        if n is not None:
            nodes.append(n)
    return index_at_pos, nodes
