"""Tests for the Phase 3 Task 4.8 CLI surface.

Covers cmd_add_mount (Phase 2 Task 3.1, extended in 4.8a with --seed),
cmd_convert (Phase 2 Task 3.2), cmd_add_folder (4.8b), and
cmd_mark_permanent / cmd_unmark_permanent (4.8c). Docker calls are
mocked where they would otherwise be invoked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _scope_dir(project: Path, scope: str) -> Path:
    return project / ".ignore_scope" / scope


class TestCmdAddMount:
    def test_bind_default(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount
        from IgnoreScope.core.config import load_config

        src = tmp_path / "src"
        src.mkdir()

        success, msg = cmd_add_mount(tmp_path, "dev", src)
        assert success is True
        assert "Mount added" in msg
        assert "delivery=bind" in msg

        config = load_config(tmp_path, "dev")
        assert len(config.mount_specs) == 1
        assert config.mount_specs[0].mount_root == src
        assert config.mount_specs[0].delivery == "bind"

    def test_detached_explicit(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount
        from IgnoreScope.core.config import load_config

        src = tmp_path / "src"
        src.mkdir()

        success, msg = cmd_add_mount(tmp_path, "dev", src, delivery="detached")
        assert success is True
        assert "Virtual Mount added" in msg
        assert "delivery=detached" in msg

        config = load_config(tmp_path, "dev")
        assert config.mount_specs[0].delivery == "detached"

    def test_overlap_rejected(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount

        src = tmp_path / "src"
        nested = src / "nested"
        nested.mkdir(parents=True)

        ok, _ = cmd_add_mount(tmp_path, "dev", src)
        assert ok is True

        success, msg = cmd_add_mount(tmp_path, "dev", nested)
        assert success is False
        assert "overlap" in msg.lower()

    def test_nonexistent_path_rejected(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount

        missing = tmp_path / "does_not_exist"
        success, msg = cmd_add_mount(tmp_path, "dev", missing)
        assert success is False
        assert "does not exist" in msg.lower()

    def test_invalid_delivery(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount

        src = tmp_path / "src"
        src.mkdir()

        success, msg = cmd_add_mount(tmp_path, "dev", src, delivery="retained")
        assert success is False
        assert "invalid" in msg.lower()


class TestCmdConvert:
    def test_bind_to_detached(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount, cmd_convert
        from IgnoreScope.core.config import load_config

        src = tmp_path / "src"
        src.mkdir()
        cmd_add_mount(tmp_path, "dev", src, delivery="bind")

        with patch(
            "IgnoreScope.cli.commands.container_exists", return_value=False
        ):
            success, msg = cmd_convert(tmp_path, "dev", src, target="detached")

        assert success is True
        assert "detached" in msg
        config = load_config(tmp_path, "dev")
        assert config.mount_specs[0].delivery == "detached"

    def test_detached_to_bind(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount, cmd_convert
        from IgnoreScope.core.config import load_config

        src = tmp_path / "src"
        src.mkdir()
        cmd_add_mount(tmp_path, "dev", src, delivery="detached")

        with patch(
            "IgnoreScope.cli.commands.container_exists", return_value=False
        ):
            success, msg = cmd_convert(tmp_path, "dev", src, target="bind")

        assert success is True
        config = load_config(tmp_path, "dev")
        assert config.mount_specs[0].delivery == "bind"

    def test_recreate_note_when_container_exists(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount, cmd_convert

        src = tmp_path / "src"
        src.mkdir()
        cmd_add_mount(tmp_path, "dev", src, delivery="bind")

        with patch(
            "IgnoreScope.cli.commands.container_exists", return_value=True
        ):
            success, msg = cmd_convert(tmp_path, "dev", src, target="detached")

        assert success is True
        assert "recreate" in msg.lower() or "create" in msg.lower()

    def test_no_matching_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_convert

        missing = tmp_path / "missing"
        success, msg = cmd_convert(tmp_path, "dev", missing, target="detached")
        assert success is False
        assert "no mount spec" in msg.lower()

    def test_already_at_target_noop(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount, cmd_convert

        src = tmp_path / "src"
        src.mkdir()
        cmd_add_mount(tmp_path, "dev", src, delivery="bind")

        with patch(
            "IgnoreScope.cli.commands.container_exists", return_value=False
        ):
            success, msg = cmd_convert(tmp_path, "dev", src, target="bind")

        assert success is True
        assert "no-op" in msg.lower() or "already" in msg.lower()

    def test_invalid_target(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_convert

        src = tmp_path / "src"
        src.mkdir()

        success, msg = cmd_convert(tmp_path, "dev", src, target="retained")
        assert success is False
        assert "invalid" in msg.lower()


class TestCmdAddMountSeedFolder:
    """Phase 3 Task 4.8a — `--seed folder` Virtual Folder gesture."""

    def test_seed_folder_creates_host_backed_folder_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount
        from IgnoreScope.core.config import load_config

        src = tmp_path / "src"
        src.mkdir()

        success, msg = cmd_add_mount(
            tmp_path, "dev", src, delivery="detached", seed="folder",
        )
        assert success is True
        assert "Virtual Folder added" in msg

        config = load_config(tmp_path, "dev")
        spec = config.mount_specs[0]
        assert spec.delivery == "detached"
        assert spec.content_seed == "folder"
        assert spec.host_path == src

    def test_seed_folder_requires_detached_delivery(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount

        src = tmp_path / "src"
        src.mkdir()

        success, msg = cmd_add_mount(
            tmp_path, "dev", src, delivery="bind", seed="folder",
        )
        assert success is False
        assert "folder" in msg.lower()
        assert "detached" in msg.lower()

    def test_invalid_seed_value(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount

        src = tmp_path / "src"
        src.mkdir()

        success, msg = cmd_add_mount(
            tmp_path, "dev", src, delivery="detached", seed="bogus",
        )
        assert success is False
        assert "seed" in msg.lower()


class TestCmdAddFolder:
    """Phase 3 Task 4.8b — container-only `add-folder` family."""

    def test_default_creates_detached_folder_container_only(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder
        from IgnoreScope.core.config import load_config

        success, msg = cmd_add_folder(
            tmp_path, "dev", Path("/api/cache"),
        )
        assert success is True
        assert "Folder added" in msg

        config = load_config(tmp_path, "dev")
        spec = config.mount_specs[0]
        assert spec.delivery == "detached"
        assert spec.content_seed == "folder"
        assert spec.host_path is None
        assert spec.preserve_on_update is False

    def test_permanent_flag_sets_preserve_on_update(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder
        from IgnoreScope.core.config import load_config

        success, msg = cmd_add_folder(
            tmp_path, "dev", Path("/api/cache"), permanent=True,
        )
        assert success is True
        assert "Permanent Folder (No Recreate)" in msg

        config = load_config(tmp_path, "dev")
        spec = config.mount_specs[0]
        assert spec.delivery == "detached"
        assert spec.preserve_on_update is True

    def test_volume_flag_creates_volume_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder
        from IgnoreScope.core.config import load_config

        with patch(
            "IgnoreScope.cli.commands.container_exists", return_value=False
        ):
            success, msg = cmd_add_folder(
                tmp_path, "dev", Path("/api/cache"), volume=True,
            )
        assert success is True
        assert "Volume Mount" in msg

        config = load_config(tmp_path, "dev")
        spec = config.mount_specs[0]
        assert spec.delivery == "volume"
        assert spec.content_seed == "folder"
        assert spec.host_path is None

    def test_volume_recreate_note_when_container_exists(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder

        with patch(
            "IgnoreScope.cli.commands.container_exists", return_value=True
        ):
            success, msg = cmd_add_folder(
                tmp_path, "dev", Path("/api/cache"), volume=True,
            )
        assert success is True
        assert "recreate" in msg.lower() or "create" in msg.lower()

    def test_permanent_and_volume_mutually_exclusive(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder

        success, msg = cmd_add_folder(
            tmp_path, "dev", Path("/api/cache"),
            permanent=True, volume=True,
        )
        assert success is False
        assert "mutually exclusive" in msg.lower()

    def test_relative_container_path_rejected(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder

        success, msg = cmd_add_folder(tmp_path, "dev", Path("api/cache"))
        assert success is False
        assert "absolute" in msg.lower()

    def test_overlap_rejected(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder

        ok, _ = cmd_add_folder(tmp_path, "dev", Path("/api"))
        assert ok is True

        success, msg = cmd_add_folder(tmp_path, "dev", Path("/api/cache"))
        assert success is False
        assert "overlap" in msg.lower()


class TestCmdMarkPermanent:
    """Phase 3 Task 4.8c — preserve_on_update flip on detached folder spec."""

    def test_marks_detached_folder_permanent(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder, cmd_mark_permanent
        from IgnoreScope.core.config import load_config

        cmd_add_folder(tmp_path, "dev", Path("/api/cache"))
        success, msg = cmd_mark_permanent(tmp_path, "dev", Path("/api/cache"))
        assert success is True
        assert "Marked permanent" in msg

        config = load_config(tmp_path, "dev")
        assert config.mount_specs[0].preserve_on_update is True

    def test_already_permanent_is_noop(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder, cmd_mark_permanent

        cmd_add_folder(tmp_path, "dev", Path("/api/cache"), permanent=True)
        success, msg = cmd_mark_permanent(tmp_path, "dev", Path("/api/cache"))
        assert success is True
        assert "no-op" in msg.lower() or "already" in msg.lower()

    def test_rejects_tree_seed_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_mount, cmd_mark_permanent

        src = tmp_path / "src"
        src.mkdir()
        cmd_add_mount(tmp_path, "dev", src, delivery="detached", seed="tree")

        success, msg = cmd_mark_permanent(tmp_path, "dev", src)
        assert success is False
        assert "content_seed" in msg.lower() or "folder" in msg.lower()

    def test_rejects_volume_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder, cmd_mark_permanent

        with patch(
            "IgnoreScope.cli.commands.container_exists", return_value=False
        ):
            cmd_add_folder(tmp_path, "dev", Path("/api/cache"), volume=True)

        success, msg = cmd_mark_permanent(tmp_path, "dev", Path("/api/cache"))
        assert success is False
        assert "delivery" in msg.lower() or "detached" in msg.lower()

    def test_no_matching_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_mark_permanent

        success, msg = cmd_mark_permanent(tmp_path, "dev", Path("/missing"))
        assert success is False
        assert "no mount spec" in msg.lower()


class TestCmdUnmarkPermanent:
    """Phase 3 Task 4.8c — inverse of mark-permanent."""

    def test_unmarks_permanent_folder_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder, cmd_unmark_permanent
        from IgnoreScope.core.config import load_config

        cmd_add_folder(tmp_path, "dev", Path("/api/cache"), permanent=True)
        success, msg = cmd_unmark_permanent(tmp_path, "dev", Path("/api/cache"))
        assert success is True
        assert "Unmarked permanent" in msg

        config = load_config(tmp_path, "dev")
        assert config.mount_specs[0].preserve_on_update is False

    def test_already_unmarked_is_noop(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_add_folder, cmd_unmark_permanent

        cmd_add_folder(tmp_path, "dev", Path("/api/cache"))
        success, msg = cmd_unmark_permanent(tmp_path, "dev", Path("/api/cache"))
        assert success is True
        assert "no-op" in msg.lower() or "already" in msg.lower()

    def test_no_matching_spec(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_unmark_permanent

        success, msg = cmd_unmark_permanent(tmp_path, "dev", Path("/missing"))
        assert success is False
        assert "no mount spec" in msg.lower()
