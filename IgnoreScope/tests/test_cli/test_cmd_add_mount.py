"""Tests for cmd_add_mount and cmd_convert CLI commands (Phase 2 Tasks 3.1, 3.2).

Verifies the thin CLI wrappers over LocalMountConfig.add_mount /
add_detached_mount / convert_delivery. Docker calls are mocked where
they would otherwise be invoked.
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
