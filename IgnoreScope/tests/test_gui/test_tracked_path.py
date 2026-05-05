"""Tests for ScopeView tracked-path overlay (decoupled from selectionModel).

Covers the design where LocalHostView.nodeSelected drives a Scope-side
visual cue that does NOT touch Scope's selectionModel — preserving
user multi-select and RMB context across LocalHost clicks.

The previous implementation used `setCurrentIndex(ClearAndSelect | Rows)`
on Scope to highlight the auto-followed path; that wiped Scope's prior
selection and conflicted with the cross-tree selection coordinator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.scope_view import ScopeView


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def scope(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main").mkdir()
    (tmp_path / "src" / "main" / "app.py").write_text("# main")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("# lib")

    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    # ScopeDisplayConfig has display_non_mounted=False; with the default
    # NodeState.visibility="restricted", an unmounted tree filters all rows.
    # Simulate a basic mount on `src` so its subtree passes the filter.
    tree.toggle_mounted(tmp_path / "src", True)

    view = ScopeView(tree)
    yield view, tree, tmp_path


class TestTrackedPathState:
    def test_initial_tracked_path_none(self, scope):
        view, _tree, _root = scope
        assert view._delegate._tracked_path is None

    def test_set_tracked_path_updates_delegate(self, scope):
        view, _tree, root = scope
        target = root / "src" / "main"
        view.set_tracked_path(target)
        assert view._delegate._tracked_path == target

    def test_set_tracked_path_none_clears_delegate(self, scope):
        view, _tree, root = scope
        view.set_tracked_path(root / "src")
        assert view._delegate._tracked_path is not None

        view.set_tracked_path(None)
        assert view._delegate._tracked_path is None

    def test_set_tracked_path_outside_project_clears_silently(self, scope, tmp_path):
        """Path outside project root is a no-op for ancestor expansion but
        still updates the delegate (overlay simply won't match any row)."""
        view, _tree, _root = scope
        outside = tmp_path.parent / "other_project" / "file.txt"
        view.set_tracked_path(outside)
        # Delegate stores whatever path was passed; no crash, no exception.
        assert view._delegate._tracked_path == outside


class TestSelectionDecoupling:
    """Tracked-path must NOT touch Scope's selectionModel."""

    def test_set_tracked_path_does_not_select(self, scope):
        view, _tree, root = scope
        assert not view._tree_view.selectionModel().hasSelection()

        view.set_tracked_path(root / "src")

        assert not view._tree_view.selectionModel().hasSelection()

    def test_set_tracked_path_preserves_existing_multi_select(self, scope):
        """Pre-populate Scope with a multi-select; tracked-path update must NOT clear it.

        This is the core contract that the previous expand_to_path violated.
        """
        view, _tree, root = scope
        sel_model = view._tree_view.selectionModel()
        # Programmatically build a 2-row selection on Scope
        idx0 = view._proxy.index(0, 0)  # root row in the proxy
        sel_model.select(idx0, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        # Add second row if available
        idx1 = view._proxy.index(1, 0)
        if idx1.isValid():
            sel_model.select(idx1, QItemSelectionModel.SelectionFlag.Select)
        before = list(sel_model.selectedIndexes())
        assert before  # must have at least one selected before tracked-path update

        view.set_tracked_path(root / "src")

        after = list(sel_model.selectedIndexes())
        assert after == before, "tracked-path update must not disturb selection"


class TestExpandToPathBackcompat:
    """`expand_to_path` is preserved as an alias for set_tracked_path."""

    def test_expand_to_path_routes_to_set_tracked_path(self, scope):
        view, _tree, root = scope
        view.expand_to_path(root / "src" / "main")
        assert view._delegate._tracked_path == root / "src" / "main"

    def test_expand_to_path_does_not_select(self, scope):
        view, _tree, root = scope
        view.expand_to_path(root / "src")
        assert not view._tree_view.selectionModel().hasSelection()


class TestMultiPathTracking:
    """Tracked-paths is a SET — multiple selected LocalHost paths produce
    multiple Scope outlines (one per path)."""

    def test_set_tracked_paths_stores_set(self, scope):
        view, _tree, root = scope
        paths = [root / "src", root / "src" / "main"]
        view.set_tracked_paths(paths)
        assert view._delegate._tracked_paths == set(paths)

    def test_set_tracked_paths_empty_clears(self, scope):
        view, _tree, root = scope
        view.set_tracked_paths([root / "src"])
        assert view._delegate._tracked_paths

        view.set_tracked_paths([])
        assert not view._delegate._tracked_paths

    def test_set_tracked_paths_replaces_not_accumulates(self, scope):
        """Subsequent calls REPLACE the tracked set; tracking does not accumulate."""
        view, _tree, root = scope
        view.set_tracked_paths([root / "src"])
        view.set_tracked_paths([root / "src" / "main"])
        assert view._delegate._tracked_paths == {root / "src" / "main"}
        assert root / "src" not in view._delegate._tracked_paths

    def test_single_path_setter_routes_to_set(self, scope):
        """The single-path convenience wrapper sets a single-element set."""
        view, _tree, root = scope
        view.set_tracked_path(root / "src")
        assert view._delegate._tracked_paths == {root / "src"}

        view.set_tracked_path(None)
        assert view._delegate._tracked_paths == set()


class TestProjectSwitchRegression:
    """Tracked-path must NOT outlive the project / scope switch.

    `MountDataTree.clear()` resets root_node to None and emits
    structureChanged. `ScopeView` listens and validates the tracked-path:
    if the path no longer maps under the (new or absent) root, it clears.
    Pass-2 review F3.
    """

    def test_tree_clear_drops_tracked_path(self, scope):
        view, tree, root = scope
        view.set_tracked_path(root / "src")
        assert view._delegate._tracked_path is not None

        tree.clear()  # simulates project switch / close

        assert view._delegate._tracked_path is None

    def test_clear_then_load_new_project_drops_old_tracked_path(self, scope, tmp_path):
        view, tree, root = scope
        view.set_tracked_path(root / "src")

        # Canonical project-switch flow: clear() first, then load new root.
        # `clear()` emits structureChanged → ScopeView._validate_tracked_path
        # runs → root_node is None → tracked_path cleared.
        tree.clear()
        new_project = tmp_path / "other_project"
        new_project.mkdir()
        (new_project / "lib").mkdir()
        tree.set_host_project_root(new_project)

        assert view._delegate._tracked_path is None


class TestPaintSmoke:
    """Smoke-test the delegate's Layer 4 outline-paint code.

    Verifies that paint() does not raise when called with a tracked-path-
    matching index, and that the painter's setClipping / setPen / drawRect
    contract is exercised. Plan-mandated 'delegate paint state branching'.
    """

    def test_paint_does_not_raise_with_tracked_match(self, scope):
        """Smoke: paint() runs the Layer-4 outline path for a tracked row.

        Uses a real QPainter on a QPixmap because Qt's typed binding rejects
        MagicMock for QStyledItemDelegate.paint(). Asserts only that no
        exception is raised — visual correctness is verified manually.
        """
        from PyQt6.QtGui import QPainter, QPixmap
        from PyQt6.QtWidgets import QStyleOptionViewItem
        view, _tree, root = scope
        view.set_tracked_path(root / "src")

        proxy = view._proxy
        target = None
        for r in range(proxy.rowCount()):
            child = proxy.index(r, 0)
            src = proxy.mapToSource(child)
            if src.isValid() and src.internalPointer().path == root / "src":
                target = child
                break
        assert target is not None

        pixmap = QPixmap(400, 30)
        pixmap.fill()
        painter = QPainter(pixmap)
        try:
            option = QStyleOptionViewItem()
            option.rect = pixmap.rect()
            option.widget = view._tree_view
            view._delegate.paint(painter, option, target)
        finally:
            painter.end()

    def test_paint_does_not_raise_for_untracked_row(self, scope):
        """Smoke: paint() also runs cleanly when row is NOT tracked."""
        from PyQt6.QtGui import QPainter, QPixmap
        from PyQt6.QtWidgets import QStyleOptionViewItem
        view, _tree, _root = scope
        # No set_tracked_path call → _tracked_path stays None
        proxy = view._proxy
        if proxy.rowCount() == 0:
            pytest.skip("fixture produced empty proxy")
        any_idx = proxy.index(0, 0)

        pixmap = QPixmap(400, 30)
        pixmap.fill()
        painter = QPainter(pixmap)
        try:
            option = QStyleOptionViewItem()
            option.rect = pixmap.rect()
            option.widget = view._tree_view
            view._delegate.paint(painter, option, any_idx)
        finally:
            painter.end()


class TestNoFinalFolderExpand:
    """select_path / set_tracked_path expands ancestors only, not the matched folder."""

    def test_matched_folder_remains_collapsed(self, scope):
        view, _tree, root = scope
        target_folder = root / "src"

        view.set_tracked_path(target_folder)

        # Find the proxy index of `src` and assert it's NOT expanded
        proxy = view._proxy
        for row in range(proxy.rowCount()):
            child = proxy.index(row, 0)
            if child.isValid():
                source = proxy.mapToSource(child)
                node = source.internalPointer()
                if node is not None and node.path == target_folder:
                    assert not view._tree_view.isExpanded(child), (
                        "tracked-path on a folder must NOT auto-expand it; "
                        "use folderExpanded chain (Change B) for explicit expand"
                    )
                    return
        pytest.fail("target folder not found in proxy rows")

    def test_ancestors_of_deeper_path_are_expanded(self, scope):
        """Tracking a deep path expands the ancestors so the row is reachable
        but does NOT expand the final matched node."""
        view, _tree, root = scope
        target = root / "src" / "main"  # final folder; should NOT expand

        view.set_tracked_path(target)

        # The ancestor `src` should be expanded so the final `main` row is reachable
        proxy = view._proxy
        for row in range(proxy.rowCount()):
            child = proxy.index(row, 0)
            source = proxy.mapToSource(child)
            node = source.internalPointer() if source.isValid() else None
            if node is not None and node.path == root / "src":
                assert view._tree_view.isExpanded(child), (
                    "ancestor of tracked path must be expanded so the row is visible"
                )
                # Now verify the final matched folder (`main`) is NOT expanded
                for sub_row in range(proxy.rowCount(child)):
                    sub = proxy.index(sub_row, 0, child)
                    sub_source = proxy.mapToSource(sub)
                    sub_node = sub_source.internalPointer() if sub_source.isValid() else None
                    if sub_node is not None and sub_node.path == target:
                        assert not view._tree_view.isExpanded(sub), (
                            "final matched folder must NOT auto-expand on tracked-path"
                        )
                        return
        pytest.fail("target ancestor not found")
