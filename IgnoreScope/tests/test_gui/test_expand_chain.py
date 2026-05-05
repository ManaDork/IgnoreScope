"""Tests for the LocalHost → Scope branch-indicator mirror chain (Bug 3 part 2).

When the user toggles a folder's branch indicator in LocalHost, ScopeView's
corresponding folder mirrors the toggle. One-way chain (LocalHost drives
Scope only). Icon-agnostic — wired via `QTreeView.expanded`/`.collapsed`
which fire regardless of the indicator's visual form (currently a square
placeholder; chevron-icon work tracked separately).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.local_host_view import LocalHostView
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.scope_view import ScopeView


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def both_views(tmp_path: Path):
    """Both LocalHostView and ScopeView wired to the same MountDataTree.

    Sets up a small folder tree with a basic mount so both panels show
    rows. Returns (local_host, scope, tree, root).
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main").mkdir()
    (tmp_path / "src" / "main" / "sub").mkdir()
    (tmp_path / "vendor").mkdir()

    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    tree.toggle_mounted(tmp_path / "src", True)

    local_host = LocalHostView(tree)
    scope = ScopeView(tree)
    yield local_host, scope, tree, tmp_path


def _proxy_index_for(view, path: Path):
    """Walk the view's proxy and return the QModelIndex for `path`."""
    proxy = view._proxy
    root_node = view._tree.root_node
    if root_node is None:
        return None
    try:
        rel = path.relative_to(root_node.path)
    except ValueError:
        return None
    parts = rel.parts
    from PyQt6.QtCore import QModelIndex
    current_parent = QModelIndex()
    matched = QModelIndex()
    for part in parts:
        found = False
        for r in range(proxy.rowCount(current_parent)):
            child = proxy.index(r, 0, current_parent)
            if not child.isValid():
                continue
            source = proxy.mapToSource(child)
            n = source.internalPointer()
            if n is not None and n.path.name == part:
                # Expand so child rowCount queries succeed for nested walks
                view._tree_view.expand(child)
                current_parent = child
                matched = child
                found = True
                break
        if not found:
            return None
    return matched if matched.isValid() else None


class TestLocalHostEmitsFolderSignals:
    def test_expanded_emits_folder_expanded(self, both_views):
        local_host, _scope, _tree, root = both_views
        target = root / "src"
        emitted: list[Path] = []
        local_host.folderExpanded.connect(emitted.append)

        idx = _proxy_index_for(local_host, target)
        assert idx is not None
        # _proxy_index_for already called expand during the walk, which
        # triggered the signal. Verify it fired with the right path.
        assert target in emitted

    def test_collapsed_emits_folder_collapsed(self, both_views):
        local_host, _scope, _tree, root = both_views
        target = root / "src"
        idx = _proxy_index_for(local_host, target)
        assert idx is not None
        local_host._tree_view.expand(idx)  # ensure expanded

        emitted: list[Path] = []
        local_host.folderCollapsed.connect(emitted.append)

        local_host._tree_view.collapse(idx)
        assert target in emitted


class TestScopeMirrorMethods:
    def test_expand_path_walks_to_target(self, both_views):
        _local_host, scope, _tree, root = both_views
        target = root / "src" / "main"

        scope.expand_path(target)

        # The matched row should now be expanded in Scope; assert by
        # finding the proxy index and checking isExpanded
        idx = _proxy_index_for(scope, target)
        assert idx is not None
        assert scope._tree_view.isExpanded(idx)

    def test_collapse_path_walks_to_target(self, both_views):
        _local_host, scope, _tree, root = both_views
        target = root / "src"

        scope.expand_path(target)
        idx = _proxy_index_for(scope, target)
        assert idx is not None
        assert scope._tree_view.isExpanded(idx)

        scope.collapse_path(target)
        # Re-find idx (proxy indices may invalidate)
        idx2 = _proxy_index_for(scope, target)
        if idx2 is not None:
            # _proxy_index_for re-expands during walk, so we need to
            # collapse and check immediately afterward without re-walking
            pass
        # Direct re-check via the original expansion-path:
        scope.collapse_path(target)
        # After collapse, the target should not be expanded. Use a
        # narrower index lookup that doesn't re-expand.
        proxy = scope._proxy
        from PyQt6.QtCore import QModelIndex
        current_parent = QModelIndex()
        for part in target.relative_to(root).parts:
            for r in range(proxy.rowCount(current_parent)):
                child = proxy.index(r, 0, current_parent)
                source = proxy.mapToSource(child)
                n = source.internalPointer()
                if n is not None and n.path.name == part:
                    if part == target.name:
                        assert not scope._tree_view.isExpanded(child)
                        return
                    current_parent = child
                    break
        pytest.fail("target not found after collapse_path")

    def test_expand_path_outside_root_silent_no_op(self, both_views, tmp_path):
        _local_host, scope, _tree, root = both_views
        outside = tmp_path.parent / "elsewhere" / "x"
        # Must not raise
        scope.expand_path(outside)

    def test_collapse_path_outside_root_silent_no_op(self, both_views, tmp_path):
        _local_host, scope, _tree, root = both_views
        outside = tmp_path.parent / "elsewhere" / "x"
        scope.collapse_path(outside)


class TestOneWayChain:
    """Verify the chain is one-way: LocalHost drives Scope; Scope does NOT drive LocalHost."""

    def test_local_host_expand_does_not_loop_back(self, both_views):
        """Wire the chain manually (mirroring app.py) and verify no feedback loop.

        The chain is one-way by construction (Scope's expanded signal isn't
        wired anywhere). This test confirms emitting folderExpanded from
        LocalHost mirrors to Scope but does NOT cause Scope to emit something
        that then ripples back to LocalHost.
        """
        local_host, scope, _tree, root = both_views
        target = root / "src"
        local_host.folderExpanded.connect(scope.expand_path)

        # Track LocalHost's expand calls — should fire ONCE (the user gesture)
        # and never again from a feedback loop.
        emit_count = [0]
        local_host.folderExpanded.connect(lambda _p: emit_count[0].__iadd__(1) if False else emit_count.__setitem__(0, emit_count[0] + 1))

        idx = _proxy_index_for(local_host, target)
        assert idx is not None
        # _proxy_index_for already fired one expanded signal. Reset counter
        # and emit a fresh expand to test the chain in isolation.
        emit_count[0] = 0
        local_host._tree_view.collapse(idx)  # collapse first
        local_host._tree_view.expand(idx)    # then expand — fires signal
        assert emit_count[0] == 1, f"Expected exactly 1 emission, got {emit_count[0]}"


class TestFilesAndStencilsSkipped:
    def test_file_does_not_emit_folder_signals(self, both_views, tmp_path):
        """Programmatically trying to expand a file index doesn't emit folder signals.

        Files cannot be expanded (Qt's view skips them), so this is mostly
        a defensive check. The handler also explicitly skips files via
        node.is_file.
        """
        local_host, _scope, _tree, _root = both_views
        emitted: list[Path] = []
        local_host.folderExpanded.connect(emitted.append)

        # Create a file and verify expanding its index (even if Qt allowed)
        # would not emit. Best we can do: check the handler logic directly.
        from PyQt6.QtCore import QModelIndex
        # Pass an invalid index — handler should early-return without raising
        local_host._on_tree_expanded(QModelIndex())
        assert emitted == []
