"""Tests for LocalMountConfig descendant query methods.

Tests:
  LMC-1: has_pushed_descendant()
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.local_mount_config import LocalMountConfig
from IgnoreScope.core.mount_spec_path import MountSpecPath


# ──────────────────────────────────────────────
# LMC-1: has_pushed_descendant()
# ──────────────────────────────────────────────


class TestHasPushedDescendant:
    """Tests for LocalMountConfig.has_pushed_descendant()."""

    def _make_config(
        self,
        tmp_path: Path,
        pushed_files: set[Path] | None = None,
    ) -> LocalMountConfig:
        return LocalMountConfig(
            mount_specs=[MountSpecPath(mount_root=tmp_path)],
            pushed_files=pushed_files or set(),
        )

    def test_pushed_file_directly_under_path(self, tmp_path: Path):
        """Pushed file is an immediate child of the queried path."""
        config = self._make_config(tmp_path, {tmp_path / "vendor" / "file.txt"})
        assert config.has_pushed_descendant(tmp_path / "vendor") is True

    def test_pushed_file_deeply_nested(self, tmp_path: Path):
        """Pushed file is several levels below the queried path."""
        config = self._make_config(tmp_path, {
            tmp_path / "vendor" / "internal" / "secret.py",
        })
        assert config.has_pushed_descendant(tmp_path / "vendor") is True
        assert config.has_pushed_descendant(tmp_path) is True

    def test_no_pushed_files(self, tmp_path: Path):
        """Empty pushed_files set."""
        config = self._make_config(tmp_path, set())
        assert config.has_pushed_descendant(tmp_path / "vendor") is False

    def test_pushed_file_is_the_path_itself(self, tmp_path: Path):
        """Pushed file equals the queried path — not a strict descendant."""
        config = self._make_config(tmp_path, {tmp_path / "vendor"})
        assert config.has_pushed_descendant(tmp_path / "vendor") is False

    def test_pushed_file_in_sibling_directory(self, tmp_path: Path):
        """Pushed file under a sibling path should not match."""
        config = self._make_config(tmp_path, {tmp_path / "dist" / "file.js"})
        assert config.has_pushed_descendant(tmp_path / "vendor") is False

    def test_multiple_pushed_files_one_matches(self, tmp_path: Path):
        """Multiple pushed files, only one is a descendant."""
        config = self._make_config(tmp_path, {
            tmp_path / "dist" / "bundle.js",
            tmp_path / "vendor" / "lib" / "helper.py",
            tmp_path / "readme.txt",
        })
        assert config.has_pushed_descendant(tmp_path / "vendor") is True
        assert config.has_pushed_descendant(tmp_path / "dist") is True
        assert config.has_pushed_descendant(tmp_path / "src") is False

    def test_root_path_with_any_pushed(self, tmp_path: Path):
        """Querying the mount root — any pushed file anywhere is a descendant."""
        config = self._make_config(tmp_path, {tmp_path / "deep" / "file.txt"})
        assert config.has_pushed_descendant(tmp_path) is True

    def test_path_above_mount_root(self, tmp_path: Path):
        """Path above mount root — pushed files are not descendants of it
        unless is_descendant handles cross-root correctly."""
        config = self._make_config(
            tmp_path / "project",
            {tmp_path / "project" / "vendor" / "file.txt"},
        )
        # tmp_path is above mount_root — pushed file IS under tmp_path
        assert config.has_pushed_descendant(tmp_path) is True

    def test_path_sharing_prefix_but_not_ancestor(self, tmp_path: Path):
        """vendor-extra is not a descendant of vendor (string prefix trap)."""
        config = self._make_config(tmp_path, {
            tmp_path / "vendor-extra" / "file.txt",
        })
        assert config.has_pushed_descendant(tmp_path / "vendor") is False


# ──────────────────────────────────────────────
# LMC-2: add_detached_mount / is_detached_mounted
# ──────────────────────────────────────────────


class TestAddDetachedMount:
    def test_adds_detached_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        assert config.add_detached_mount(src) is True
        assert len(config.mount_specs) == 1
        assert config.mount_specs[0].mount_root == src
        assert config.mount_specs[0].delivery == "detached"

    def test_overlap_with_existing_bind_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        config.add_mount(parent)
        assert config.add_detached_mount(child) is False
        # Overlap in reverse: try adding a bind under a detached parent
        other = tmp_path / "other"
        other.mkdir()
        child2 = other / "inner"
        config.add_detached_mount(other)
        assert config.add_mount(child2) is False

    def test_duplicate_mount_root_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_detached_mount(src)
        assert config.add_detached_mount(src) is False

    def test_is_detached_mounted_exact_match(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        other = tmp_path / "other"
        src.mkdir()
        other.mkdir()
        config.add_detached_mount(src)
        config.add_mount(other)

        assert config.is_detached_mounted(src) is True
        assert config.is_detached_mounted(other) is False  # bind spec
        assert config.is_detached_mounted(src / "child") is False  # descendant

    def test_is_detached_mounted_empty_config(self, tmp_path: Path):
        config = LocalMountConfig()
        assert config.is_detached_mounted(tmp_path / "anything") is False


# ──────────────────────────────────────────────
# LMC-3: convert_delivery
# ──────────────────────────────────────────────


class TestConvertDelivery:
    def test_bind_to_detached(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_mount(src)
        assert config.convert_delivery(src, "detached") is True
        assert config.mount_specs[0].delivery == "detached"

    def test_detached_to_bind(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_detached_mount(src)
        assert config.convert_delivery(src, "bind") is True
        assert config.mount_specs[0].delivery == "bind"

    def test_already_at_target_returns_false(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_mount(src)
        assert config.convert_delivery(src, "bind") is False

    def test_no_matching_spec_returns_false(self, tmp_path: Path):
        config = LocalMountConfig()
        assert config.convert_delivery(tmp_path / "missing", "detached") is False


# ──────────────────────────────────────────────
# LMC-4: remove_but_keep_children
# ──────────────────────────────────────────────


class TestRemoveButKeepChildren:
    def test_explodes_parent_into_children(self, tmp_path: Path):
        parent = tmp_path / "parent"
        (parent / "a").mkdir(parents=True)
        (parent / "b").mkdir()
        (parent / "c").mkdir()

        config = LocalMountConfig()
        config.add_mount(parent)
        assert config.remove_but_keep_children(parent) is True

        roots = {ms.mount_root for ms in config.mount_specs}
        assert roots == {parent / "a", parent / "b", parent / "c"}

    def test_children_inherit_delivery(self, tmp_path: Path):
        parent = tmp_path / "parent"
        (parent / "a").mkdir(parents=True)
        (parent / "b").mkdir()

        config = LocalMountConfig()
        config.add_detached_mount(parent)
        config.remove_but_keep_children(parent)

        assert all(ms.delivery == "detached" for ms in config.mount_specs)

    def test_no_match_returns_false(self, tmp_path: Path):
        config = LocalMountConfig()
        assert config.remove_but_keep_children(tmp_path / "missing") is False

    def test_no_children_returns_false(self, tmp_path: Path):
        parent = tmp_path / "parent"
        parent.mkdir()
        config = LocalMountConfig()
        config.add_mount(parent)
        # No child dirs → no-op
        assert config.remove_but_keep_children(parent) is False
        # Parent still present
        assert any(ms.mount_root == parent for ms in config.mount_specs)

    def test_patterns_reassigned_to_children(self, tmp_path: Path):
        parent = tmp_path / "parent"
        (parent / "a" / "vendor").mkdir(parents=True)
        (parent / "b").mkdir()

        config = LocalMountConfig()
        config.add_mount(parent)
        # Add a pattern that points under child 'a'
        config.mount_specs[0].patterns.append("a/vendor/")

        config.remove_but_keep_children(parent)

        a_spec = next(ms for ms in config.mount_specs if ms.mount_root.name == "a")
        b_spec = next(ms for ms in config.mount_specs if ms.mount_root.name == "b")
        assert "vendor/" in a_spec.patterns
        assert b_spec.patterns == []
