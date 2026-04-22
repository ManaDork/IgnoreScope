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
# LMC-2b: add_detached_folder_mount (Virtual Folder)
# ──────────────────────────────────────────────


class TestAddDetachedFolderMount:
    def test_adds_host_backed_folder_seed_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        assert config.add_detached_folder_mount(src) is True
        assert len(config.mount_specs) == 1
        ms = config.mount_specs[0]
        assert ms.mount_root == src
        assert ms.delivery == "detached"
        assert ms.content_seed == "folder"
        assert ms.host_path == src  # host-backed (LocalHost gesture)
        assert ms.preserve_on_update is False

    def test_overlap_with_existing_bind_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        config.add_mount(parent)
        assert config.add_detached_folder_mount(child) is False

    def test_overlap_with_existing_detached_folder_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        config.add_detached_folder_mount(parent)
        assert config.add_detached_folder_mount(child) is False
        assert config.add_mount(child) is False

    def test_duplicate_mount_root_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_detached_folder_mount(src)
        assert config.add_detached_folder_mount(src) is False

    def test_validator_passes_for_resulting_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_detached_folder_mount(src)
        assert config.mount_specs[0].validate() == []


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


# ──────────────────────────────────────────────
# LMC-5: Phase 3 container-only constructors
#        add_stencil_folder / add_stencil_volume / mark_permanent / unmark_permanent
# ──────────────────────────────────────────────


class TestAddStencilFolder:
    def test_creates_detached_folder_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        container_path = Path("/container/folder")
        assert config.add_stencil_folder(container_path) is True
        spec = config.mount_specs[0]
        assert spec.mount_root == container_path
        assert spec.delivery == "detached"
        assert spec.content_seed == "folder"
        assert spec.host_path is None
        assert spec.preserve_on_update is False

    def test_preserve_on_update_flag_propagates(self, tmp_path: Path):
        config = LocalMountConfig()
        assert config.add_stencil_folder(
            Path("/container/folder"), preserve_on_update=True,
        ) is True
        assert config.mount_specs[0].preserve_on_update is True

    def test_duplicate_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        p = Path("/container/folder")
        config.add_stencil_folder(p)
        assert config.add_stencil_folder(p) is False

    def test_overlap_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        config.add_stencil_folder(Path("/container/parent"))
        assert config.add_stencil_folder(Path("/container/parent/child")) is False
        assert len(config.mount_specs) == 1


class TestAddStencilVolume:
    def test_creates_volume_folder_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        container_path = Path("/container/data")
        assert config.add_stencil_volume(container_path) is True
        spec = config.mount_specs[0]
        assert spec.mount_root == container_path
        assert spec.delivery == "volume"
        assert spec.content_seed == "folder"
        assert spec.host_path is None
        assert spec.preserve_on_update is False

    def test_volume_duplicate_rejected(self, tmp_path: Path):
        config = LocalMountConfig()
        p = Path("/container/data")
        config.add_stencil_volume(p)
        assert config.add_stencil_volume(p) is False


class TestMarkPermanent:
    def test_flips_false_to_true_on_detached_folder(self, tmp_path: Path):
        config = LocalMountConfig()
        p = Path("/container/folder")
        config.add_stencil_folder(p)
        assert config.mount_specs[0].preserve_on_update is False
        assert config.mark_permanent(p) is True
        assert config.mount_specs[0].preserve_on_update is True

    def test_noop_when_already_permanent(self, tmp_path: Path):
        config = LocalMountConfig()
        p = Path("/container/folder")
        config.add_stencil_folder(p, preserve_on_update=True)
        assert config.mark_permanent(p) is False

    def test_rejected_on_bind_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_mount(src)
        assert config.mark_permanent(src) is False
        assert config.mount_specs[0].preserve_on_update is False

    def test_rejected_on_volume_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        p = Path("/container/data")
        config.add_stencil_volume(p)
        assert config.mark_permanent(p) is False

    def test_rejected_on_detached_tree_spec(self, tmp_path: Path):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_detached_mount(src)  # tree seed
        assert config.mark_permanent(src) is False

    def test_no_match_returns_false(self, tmp_path: Path):
        config = LocalMountConfig()
        assert config.mark_permanent(Path("/container/missing")) is False


class TestUnmarkPermanent:
    def test_flips_true_to_false(self, tmp_path: Path):
        config = LocalMountConfig()
        p = Path("/container/folder")
        config.add_stencil_folder(p, preserve_on_update=True)
        assert config.unmark_permanent(p) is True
        assert config.mount_specs[0].preserve_on_update is False

    def test_noop_when_already_false(self, tmp_path: Path):
        config = LocalMountConfig()
        p = Path("/container/folder")
        config.add_stencil_folder(p)
        assert config.unmark_permanent(p) is False

    def test_no_match_returns_false(self, tmp_path: Path):
        config = LocalMountConfig()
        assert config.unmark_permanent(Path("/container/missing")) is False


class TestConfigRoundTripWithPhase3:
    def test_container_only_folder_round_trip(self, tmp_path: Path):
        config = LocalMountConfig()
        config.add_stencil_folder(
            Path("/container/data"), preserve_on_update=True,
        )
        restored = LocalMountConfig.from_dict(config.to_dict(tmp_path), tmp_path)
        assert len(restored.mount_specs) == 1
        spec = restored.mount_specs[0]
        assert spec.delivery == "detached"
        assert spec.content_seed == "folder"
        assert spec.host_path is None
        assert spec.preserve_on_update is True

    def test_volume_round_trip(self, tmp_path: Path):
        config = LocalMountConfig()
        config.add_stencil_volume(Path("/container/cache"))
        restored = LocalMountConfig.from_dict(config.to_dict(tmp_path), tmp_path)
        spec = restored.mount_specs[0]
        assert spec.delivery == "volume"
        assert spec.content_seed == "folder"
        assert spec.host_path is None

    def test_legacy_bind_mount_still_sets_host_path_to_mirror_mount_root(
        self, tmp_path: Path,
    ):
        config = LocalMountConfig()
        src = tmp_path / "src"
        src.mkdir()
        config.add_mount(src)
        assert config.mount_specs[0].host_path == src
