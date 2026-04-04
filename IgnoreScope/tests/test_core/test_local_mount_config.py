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
