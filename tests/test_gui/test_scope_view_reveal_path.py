"""Tests for ``ScopeView.reveal_path`` — Phase B.4 (the Reveal-in-tree
action from ``MarkedPushDialog``).

reveal_path expands ancestors so the target row is reachable, then
scrollTo + setCurrentIndex on the tree view. Returns True iff the path
was found in the proxy mapping.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.scope_view import ScopeView
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
def view_with_files(tmp_path: Path) -> tuple[ScopeView, Path]:
    """ScopeView over a tree containing tmp_path/src/a.txt.

    The default ``ScopeDisplayConfig`` hides restricted (unmounted) files
    and folders — that's the right product behavior, but it makes a
    test-fixture file invisible to the proxy. Flip ``display_hidden``
    on so the file surfaces in the proxy mapping; reveal_path can then
    find it.
    """
    src = tmp_path / "src"
    src.mkdir()
    target = src / "a.txt"
    target.write_text("x", encoding="utf-8")

    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    # Pre-load src's children so a.txt is reachable without lazy-load
    # races. Production code triggers fetchMore via tree-view expansion;
    # the test pre-loads to keep the assertion focused on reveal_path,
    # not on the lazy-load chain (which has its own coverage).
    for child in tree.root_node.children:
        if not child.is_file:
            child.load_children(folders_only=False)

    view = ScopeView(tree)
    # Surface all rows for the test — ScopeDisplayConfig hides
    # non-mounted/restricted nodes by default. Flip every relevant
    # filter so the test sees the tree at face value.
    view._config.display_hidden = True
    view._config.display_non_mounted = True
    view._config.display_masked_dead_branches = True
    view._proxy.invalidateFilter()
    return view, target


def test_reveal_path_returns_true_and_sets_current(view_with_files):
    """Found path → returns True, tree's currentIndex points at the row."""
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
    """The target file's parent folder must be expanded so the row is
    actually reachable to scrollTo / setCurrentIndex.
    """
    view, target = view_with_files
    ok = view.reveal_path(target)
    assert ok is True

    # `src` is the only top-level child of the project root.
    model = view._proxy
    src_proxy = model.index(0, 0)
    assert src_proxy.isValid()
    assert view._tree_view.isExpanded(src_proxy), (
        "reveal_path must expand ancestor folders so the target row is reachable"
    )


def test_reveal_path_outside_project_returns_false(view_with_files, tmp_path):
    """A path outside the project root is unreachable → False."""
    view, _ = view_with_files
    other = tmp_path.parent / "elsewhere" / "x.txt"
    ok = view.reveal_path(other)
    assert ok is False


def test_reveal_path_unknown_file_returns_false(view_with_files, tmp_path):
    """A path inside the project root but not present in the tree → False."""
    view, _ = view_with_files
    missing = tmp_path / "src" / "does_not_exist.txt"
    ok = view.reveal_path(missing)
    assert ok is False


def test_reveal_path_empty_relpath_returns_false(view_with_files, tmp_path):
    """The project root itself has no parts → False (no row to select)."""
    view, _ = view_with_files
    ok = view.reveal_path(tmp_path)
    assert ok is False