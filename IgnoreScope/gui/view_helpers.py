"""Shared tree view setup helpers.

Eliminates duplicated QTreeView configuration and header setup
between LocalHostView and ScopeView.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import (
    QTreeView,
    QHeaderView,
    QAbstractItemView,
)

from .display_config import ColumnDef


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
