"""Tests for MountDataTree.show_hidden toggle behavior.

Covers the bug where toggling Display Hidden Items off then on did not restore
dotfile nodes — see `_workbench/_bugs/visible-invisible-mode-bug.md`.

Root cause was `_rebuild_tree` only resetting `children_loaded=False` on the
root node; expanded subdirectories kept their cached children list and Qt's
lazy `fetchMore` early-returned, so dotfiles inside them never re-scanned.

The fix recurses `_invalidate_loaded` over root + sibling subtrees and calls
`_recompute_states()` so newly-loaded nodes get fresh NodeState before proxy
queries.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.mount_data_tree import MountDataTree


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def tree(tmp_path: Path) -> MountDataTree:
    t = MountDataTree()
    t.set_host_project_root(tmp_path)
    return t


def _child_names(node) -> set[str]:
    return {c.name for c in node.children}


class TestShowHiddenToggleRoundtrip:
    def test_dotfile_under_root_reappears_after_recheck(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        """Round-trip True->False->True must restore root-level dotfile."""
        (tmp_path / ".local").mkdir()
        (tmp_path / "src").mkdir()

        # Initial: show_hidden defaults to False, so .local was filtered on
        # the initial set_host_project_root scan
        tree.show_hidden = True
        assert ".local" in _child_names(tree.root_node)
        assert "src" in _child_names(tree.root_node)

        tree.show_hidden = False
        assert ".local" not in _child_names(tree.root_node)
        assert "src" in _child_names(tree.root_node)

        tree.show_hidden = True
        # The bug: this used to fail because _rebuild_tree was non-recursive
        # but for a root-level dotfile the root reload itself is sufficient,
        # so this case actually passed pre-fix. Kept for symmetry.
        assert ".local" in _child_names(tree.root_node)

    def test_dotfile_in_expanded_subdir_reappears(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        """The harder case: dotfile inside a subdir that was already expanded.

        Before the fix, `_rebuild_tree` only reloaded root, leaving
        `src.children_loaded=True` so the .cache child never re-scanned.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / ".cache").mkdir()
        (src / "main.py").write_text("")

        tree.show_hidden = True
        # Force lazy-load of src/ to mimic user expansion in the tree view
        src_node = next(c for c in tree.root_node.children if c.name == "src")
        src_node.load_children(folders_only=False)
        assert ".cache" in _child_names(src_node)
        assert "main.py" in _child_names(src_node)

        tree.show_hidden = False
        # After toggle off, src should be reloaded with .cache filtered out
        src_node = next(c for c in tree.root_node.children if c.name == "src")
        # src has been recreated by the recursive invalidate; trigger lazy load
        src_node.load_children(folders_only=False)
        assert ".cache" not in _child_names(src_node)
        assert "main.py" in _child_names(src_node)

        tree.show_hidden = True
        # The bug-fixing assertion: .cache must reappear inside the expanded subdir
        src_node = next(c for c in tree.root_node.children if c.name == "src")
        src_node.load_children(folders_only=False)
        assert ".cache" in _child_names(src_node)

    def test_structure_changed_emits_on_toggle(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        """Each show_hidden setter call that actually changes the value emits structureChanged once."""
        (tmp_path / "src").mkdir()
        emissions: list[None] = []
        tree.structureChanged.connect(lambda: emissions.append(None))

        tree.show_hidden = True
        first = len(emissions)
        assert first == 1

        # Setting to same value is a no-op (guarded by `if self._show_hidden != value:`)
        tree.show_hidden = True
        assert len(emissions) == first  # no extra emission

        tree.show_hidden = False
        assert len(emissions) == first + 1

    def test_invalidate_loaded_skips_files_and_stencils(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        """Files and stencil nodes are leaves and must not recurse into."""
        from IgnoreScope.gui.mount_data_tree import MountDataNode, NodeSource

        # File node — must early-return without resetting
        file_node = MountDataNode(
            path=tmp_path / "f.txt",
            is_file=True,
            children_loaded=True,
        )
        tree._invalidate_loaded(file_node)
        # children_loaded stays True for files (they were never "loaded" in the dir sense)
        assert file_node.children_loaded is True

        # Stencil node — must early-return
        stencil_node = MountDataNode(
            path=tmp_path / "stencil",
            is_stencil_node=True,
            children_loaded=True,
            source=NodeSource.STENCIL,
        )
        tree._invalidate_loaded(stencil_node)
        assert stencil_node.children_loaded is True
