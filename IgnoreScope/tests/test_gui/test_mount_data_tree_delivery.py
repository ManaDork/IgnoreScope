"""Tests for MountDataTree per-spec delivery API.

Covers:
  - toggle_virtual_mounted(path, True/False)
  - convert_delivery(path, target)
  - remove_but_keep_children(path)
  - is_in_raw_set('mounted' | 'virtual_mounted', path) filter semantics
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


class TestToggleVirtualMounted:
    def test_adds_detached_spec(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_virtual_mounted(src, True)
        assert tree.is_in_raw_set("virtual_mounted", src) is True
        assert tree.is_in_raw_set("mounted", src) is False

    def test_remove_detached_spec(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_virtual_mounted(src, True)
        tree.toggle_virtual_mounted(src, False)
        assert tree.is_in_raw_set("virtual_mounted", src) is False

    def test_overlap_blocks_virtual(self, tree: MountDataTree, tmp_path: Path):
        parent = tmp_path / "parent"
        (parent / "child").mkdir(parents=True)
        tree.toggle_mounted(parent, True)
        tree.toggle_virtual_mounted(parent / "child", True)
        # Overlap blocks the virtual mount — child not added
        assert tree.is_in_raw_set("virtual_mounted", parent / "child") is False


class TestIsInRawSetDeliveryFilter:
    def test_bind_not_reported_as_virtual(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        assert tree.is_in_raw_set("mounted", src) is True
        assert tree.is_in_raw_set("virtual_mounted", src) is False

    def test_virtual_not_reported_as_bind(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_virtual_mounted(src, True)
        assert tree.is_in_raw_set("virtual_mounted", src) is True
        assert tree.is_in_raw_set("mounted", src) is False


class TestConvertDelivery:
    def test_bind_to_detached(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        assert tree.convert_delivery(src, "detached") is True
        assert tree.is_in_raw_set("virtual_mounted", src) is True
        assert tree.is_in_raw_set("mounted", src) is False

    def test_detached_to_bind(self, tree: MountDataTree, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_virtual_mounted(src, True)
        assert tree.convert_delivery(src, "bind") is True
        assert tree.is_in_raw_set("mounted", src) is True

    def test_no_match_returns_false(self, tree: MountDataTree, tmp_path: Path):
        assert tree.convert_delivery(tmp_path / "missing", "detached") is False

    def test_already_at_target_returns_false(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        assert tree.convert_delivery(src, "bind") is False


class TestRemoveButKeepChildren:
    def test_splits_parent_into_child_specs(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        parent = tmp_path / "parent"
        (parent / "a").mkdir(parents=True)
        (parent / "b").mkdir()
        tree.toggle_virtual_mounted(parent, True)

        assert tree.remove_but_keep_children(parent) is True
        assert tree.is_in_raw_set("virtual_mounted", parent / "a") is True
        assert tree.is_in_raw_set("virtual_mounted", parent / "b") is True
        assert tree.is_in_raw_set("virtual_mounted", parent) is False

    def test_no_children_returns_false(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        parent = tmp_path / "empty_parent"
        parent.mkdir()
        tree.toggle_virtual_mounted(parent, True)
        assert tree.remove_but_keep_children(parent) is False
        # Parent still present
        assert tree.is_in_raw_set("virtual_mounted", parent) is True

    def test_no_match_returns_false(self, tree: MountDataTree, tmp_path: Path):
        assert tree.remove_but_keep_children(tmp_path / "missing") is False
