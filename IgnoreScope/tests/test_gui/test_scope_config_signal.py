"""Tests for scopeConfigChanged signal wiring (Task 2.9).

Covers:
  - MountDataTree.mountSpecsChanged emits after every mount_specs mutation.
  - ConfigManager.scopeConfigChanged forwards mountSpecsChanged emissions.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.config_manager import ConfigManager
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


@pytest.fixture
def cm(tree: MountDataTree) -> ConfigManager:
    """ConfigManager only touches app._mount_data_tree in __init__ — stub it."""
    app_stub = SimpleNamespace(_mount_data_tree=tree)
    return ConfigManager(app_stub)  # type: ignore[arg-type]


# ──────────────────────────────────────────────
# MountDataTree.mountSpecsChanged
# ──────────────────────────────────────────────

class TestMountSpecsChanged:
    def test_emits_on_toggle_mounted(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        emitted = []
        tree.mountSpecsChanged.connect(lambda: emitted.append(True))
        tree.toggle_mounted(src, True)
        assert len(emitted) == 1

    def test_emits_on_toggle_virtual_mounted(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        emitted = []
        tree.mountSpecsChanged.connect(lambda: emitted.append(True))
        tree.toggle_virtual_mounted(src, True)
        assert len(emitted) == 1

    def test_emits_on_convert_delivery(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        emitted = []
        tree.mountSpecsChanged.connect(lambda: emitted.append(True))
        tree.convert_delivery(src, "detached")
        assert len(emitted) == 1

    def test_convert_noop_does_not_emit(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        emitted = []
        tree.mountSpecsChanged.connect(lambda: emitted.append(True))
        assert tree.convert_delivery(src, "bind") is False
        assert emitted == []

    def test_emits_on_remove_but_keep_children(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        parent = tmp_path / "parent"
        (parent / "a").mkdir(parents=True)
        (parent / "b").mkdir()
        tree.toggle_virtual_mounted(parent, True)
        emitted = []
        tree.mountSpecsChanged.connect(lambda: emitted.append(True))
        assert tree.remove_but_keep_children(parent) is True
        assert len(emitted) == 1

    def test_emits_on_remove(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        emitted = []
        tree.mountSpecsChanged.connect(lambda: emitted.append(True))
        tree.toggle_mounted(src, False)
        assert len(emitted) == 1


# ──────────────────────────────────────────────
# ConfigManager forwarding
# ──────────────────────────────────────────────

class TestScopeConfigChangedForwarding:
    def test_forwards_on_toggle_mounted(
        self, cm: ConfigManager, tree: MountDataTree, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        emitted = []
        cm.scopeConfigChanged.connect(lambda: emitted.append(True))
        tree.toggle_mounted(src, True)
        assert len(emitted) == 1

    def test_forwards_on_toggle_virtual_mounted(
        self, cm: ConfigManager, tree: MountDataTree, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        emitted = []
        cm.scopeConfigChanged.connect(lambda: emitted.append(True))
        tree.toggle_virtual_mounted(src, True)
        assert len(emitted) == 1

    def test_forwards_on_convert_delivery(
        self, cm: ConfigManager, tree: MountDataTree, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        emitted = []
        cm.scopeConfigChanged.connect(lambda: emitted.append(True))
        tree.convert_delivery(src, "detached")
        assert len(emitted) == 1

    def test_forwards_on_remove_but_keep_children(
        self, cm: ConfigManager, tree: MountDataTree, tmp_path: Path,
    ):
        parent = tmp_path / "parent"
        (parent / "a").mkdir(parents=True)
        tree.toggle_virtual_mounted(parent, True)
        emitted = []
        cm.scopeConfigChanged.connect(lambda: emitted.append(True))
        tree.remove_but_keep_children(parent)
        assert len(emitted) == 1
