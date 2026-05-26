"""Model-lifecycle invariants for ``MountDataTreeModel``.

Pinning the Phase A crash fix from
``_workbench/_bugs/files-marked-for-push-fatal-crash.md`` +
``_workbench/_bugs/gui-startup-access-violation.md``:

  * Every node handed to ``createIndex`` is retained in ``_handed_out`` until
    the next model reset — Python cannot GC a node the proxy may still hold
    an ``internalPointer()`` for.
  * ``refresh`` / ``reset`` / ``set_host_project_root_and_reset`` each clear
    ``_handed_out`` as part of the ``beginResetModel`` / ``endResetModel``
    bracket.
  * ``reset_models_around`` brackets multiple models around a shared tree
    mutation so both views' proxies see the reset atomically.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QModelIndex
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.display_config import LocalHostDisplayConfig, ScopeDisplayConfig
from IgnoreScope.gui.mount_data_model import MountDataTreeModel
from IgnoreScope.gui.mount_data_tree import MountDataTree


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def tree(tmp_path):
    """A loaded MountDataTree with at least one child under root."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("x", encoding="utf-8")
    t = MountDataTree()
    t.set_host_project_root(tmp_path)
    return t


@pytest.fixture
def model(tree):
    """A MountDataTreeModel wrapping the loaded tree."""
    return MountDataTreeModel(tree, LocalHostDisplayConfig())


# ── A.1: strong-reference guard ─────────────────────────────────────────────


def test_create_index_populates_handed_out(model, tree):
    """Each createIndex call adds the node to _handed_out (keyed by id)."""
    assert model._handed_out == {}

    # Calling index(0, 0, root) hands out the first child.
    idx = model.index(0, 0, QModelIndex())
    assert idx.isValid()

    child = tree.root_node.children[0]
    assert id(child) in model._handed_out
    assert model._handed_out[id(child)] is child


def test_parent_call_also_populates_handed_out(model, tree):
    """The parent() method also stores its node — covers the second createIndex
    call site at mount_data_model.py:128.
    """
    # Build a 2-level index so parent() does work.
    (Path(tree.root_node.path) / "nested").mkdir()
    (Path(tree.root_node.path) / "nested" / "deep.txt").write_text("y", encoding="utf-8")
    tree.root_node.children_loaded = False
    tree.root_node.load_children(folders_only=False)

    nested_idx = model.index(0, 0, QModelIndex())  # nested folder
    nested = nested_idx.internalPointer()
    nested.load_children(folders_only=False)

    child_idx = model.index(0, 0, nested_idx)
    assert child_idx.isValid()

    parent_idx = model.parent(child_idx)
    assert id(nested) in model._handed_out
    assert parent_idx.internalPointer() is nested


def test_refresh_clears_handed_out(model):
    """refresh() must clear the guard so dropped nodes can be GC'd later."""
    model.index(0, 0, QModelIndex())
    assert len(model._handed_out) >= 1

    model.refresh()
    assert model._handed_out == {}


def test_reset_clears_handed_out(model):
    """Explicit reset() (the structural-delta path's escape hatch) also clears."""
    model.index(0, 0, QModelIndex())
    assert len(model._handed_out) >= 1

    model.reset()
    assert model._handed_out == {}


# ── A.3: set_host_project_root bracket ──────────────────────────────────────


def test_set_host_project_root_and_reset_clears_handed_out(
    model, tree, tmp_path,
):
    """The root-replacement wrapper must clear the guard — the original
    set_host_project_root frees every prior node and the proxy's stale
    indices would dereference freed memory otherwise.
    """
    model.index(0, 0, QModelIndex())
    assert len(model._handed_out) >= 1
    old_root = tree.root_node

    new_root_dir = tmp_path / "fresh"
    new_root_dir.mkdir()
    (new_root_dir / "b.txt").write_text("z", encoding="utf-8")

    model.set_host_project_root_and_reset(new_root_dir)

    # _handed_out cleared.
    assert model._handed_out == {}
    # The tree's root node is now a fresh MountDataNode for the new path.
    assert tree.root_node is not old_root
    assert tree.root_node.path == new_root_dir.resolve()


def test_set_host_project_root_and_reset_emits_reset_signals(
    model, tmp_path,
):
    """beginResetModel/endResetModel must fire — proxy depends on these to
    rebuild its source mapping.
    """
    started = []
    finished = []
    model.modelAboutToBeReset.connect(lambda: started.append(None))
    model.modelReset.connect(lambda: finished.append(None))

    new_root_dir = tmp_path / "another"
    new_root_dir.mkdir()
    model.set_host_project_root_and_reset(new_root_dir)

    assert len(started) == 1
    assert len(finished) == 1


# ── A.3 / shared-tree variant: reset_models_around ──────────────────────────


def test_reset_models_around_brackets_all_models(tree):
    """All models call beginResetModel before the mutator runs, then
    endResetModel after — both views see the reset atomically.
    """
    m1 = MountDataTreeModel(tree, LocalHostDisplayConfig())
    m2 = MountDataTreeModel(tree, ScopeDisplayConfig())

    # Pre-populate both guards.
    m1.index(0, 0, QModelIndex())
    m2.index(0, 0, QModelIndex())
    assert len(m1._handed_out) >= 1
    assert len(m2._handed_out) >= 1

    # Order log: each model emits modelAboutToBeReset before the mutator runs,
    # then modelReset after.
    events: list[str] = []
    m1.modelAboutToBeReset.connect(lambda: events.append("m1.begin"))
    m1.modelReset.connect(lambda: events.append("m1.end"))
    m2.modelAboutToBeReset.connect(lambda: events.append("m2.begin"))
    m2.modelReset.connect(lambda: events.append("m2.end"))

    mutator_ran = []

    def mutator():
        mutator_ran.append(True)
        events.append("mutator")

    MountDataTreeModel.reset_models_around([m1, m2], mutator)

    assert mutator_ran == [True]
    # Both begins must precede the mutator, both ends must follow it.
    assert events == ["m1.begin", "m2.begin", "mutator", "m1.end", "m2.end"]
    # Both guards cleared.
    assert m1._handed_out == {}
    assert m2._handed_out == {}


def test_reset_models_around_clears_on_mutator_exception(tree):
    """If the mutator raises, models must still endResetModel and clear the
    guard — otherwise the proxy is permanently wedged with modelAboutToBeReset
    pending and the GUI freezes.
    """
    m1 = MountDataTreeModel(tree, LocalHostDisplayConfig())
    m1.index(0, 0, QModelIndex())
    started = []
    finished = []
    m1.modelAboutToBeReset.connect(lambda: started.append(None))
    m1.modelReset.connect(lambda: finished.append(None))

    def angry_mutator():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        MountDataTreeModel.reset_models_around([m1], angry_mutator)

    assert started == [None]
    assert finished == [None]
    assert m1._handed_out == {}
