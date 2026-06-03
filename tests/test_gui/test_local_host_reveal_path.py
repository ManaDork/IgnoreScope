"""Tests for ``LocalHostView.reveal_path`` — Phase B.5.

Mirrors the scope-side reveal_path tests; the local-host panel is where
the host file actually lives, so the dialog's Reveal needs both views to
navigate (previously only Scope did anything).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.local_host_view import LocalHostView
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.style_engine import StyleGui


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_style_singleton():
    StyleGui._reset()
    yield
    StyleGui._reset()


@pytest.fixture
def view_with_files(tmp_path: Path) -> tuple[LocalHostView, Path]:
    """LocalHostView over a tree containing tmp_path/src/a.txt."""
    src = tmp_path / "src"
    src.mkdir()
    target = src / "a.txt"
    target.write_text("x", encoding="utf-8")

    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    # Pre-load children so a.txt is reachable without lazy-load races.
    for child in tree.root_node.children:
        if not child.is_file:
            child.load_children(folders_only=False)

    view = LocalHostView(tree)
    # LocalHostDisplayConfig defaults — flip the same filters as the
    # scope-side test so unconfigured fixture rows surface.
    view._config.display_hidden = True
    view._config.display_files = True
    view._proxy.invalidateFilter()
    return view, target


def test_reveal_path_returns_true_and_sets_current(view_with_files):
    view, target = view_with_files
    ok = view.reveal_path(target)
    assert ok is True

    current = view._tree_view.currentIndex()
    assert current.isValid()
    source_idx = view._proxy.mapToSource(current)
    node = source_idx.internalPointer()
    assert node is not None
    assert node.path.name == target.name


def test_reveal_path_expands_ancestor_folder(view_with_files):
    """Parent folder must be expanded so the row is reachable."""
    view, target = view_with_files
    ok = view.reveal_path(target)
    assert ok is True

    model = view._proxy
    src_proxy = model.index(0, 0)
    assert src_proxy.isValid()
    assert view._tree_view.isExpanded(src_proxy), (
        "reveal_path must expand ancestor folders so the target row is reachable"
    )


def test_reveal_path_outside_project_returns_false(view_with_files, tmp_path):
    view, _ = view_with_files
    other = tmp_path.parent / "elsewhere" / "x.txt"
    ok = view.reveal_path(other)
    assert ok is False


def test_reveal_path_falls_back_to_deepest_ancestor(view_with_files, tmp_path):
    """When the exact file is filtered out (e.g., under a mask) the user
    still lands at the closest visible ancestor — not at the root.
    """
    view, _ = view_with_files
    missing_under_existing = tmp_path / "src" / "does_not_exist.txt"
    ok = view.reveal_path(missing_under_existing)
    # The exact file isn't there → full_match=False → returns False
    assert ok is False
    # But the current index should be the deepest ancestor (src), not invalid.
    current = view._tree_view.currentIndex()
    assert current.isValid(), (
        "reveal_path should still scroll/select the deepest reachable "
        "ancestor when the exact path isn't reachable — gives the user "
        "context instead of nothing"
    )
    src_node = view._proxy.mapToSource(current).internalPointer()
    assert src_node is not None
    assert src_node.path.name == "src"
