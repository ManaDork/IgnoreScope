"""Tests for cmd_install_git CLI command.

Verifies the CLI command handler for Git installation into containers.
All Docker calls are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestCmdInstallGit:
    """Tests for cli.commands.cmd_install_git."""

    def test_success(self, tmp_path: Path):
        """Returns (True, message) with version on successful deploy."""
        from IgnoreScope.cli.commands import cmd_install_git
        from IgnoreScope.container_ext.install_extension import DeployResult

        mock_result = DeployResult(
            success=True,
            message="Git deployed successfully",
            version="2.39.2",
        )

        with patch(
            "IgnoreScope.cli.commands.GitInstaller"
        ) as MockInstaller:
            instance = MockInstaller.return_value
            instance.deploy.return_value = mock_result

            success, msg = cmd_install_git(tmp_path, "default")

            assert success is True
            assert "2.39.2" in msg
            instance.deploy.assert_called_once()

    def test_with_configure(self, tmp_path: Path):
        """Configures identity when --configure, --name, --email provided."""
        from IgnoreScope.cli.commands import cmd_install_git
        from IgnoreScope.container_ext.install_extension import DeployResult

        mock_result = DeployResult(
            success=True,
            message="Git deployed successfully",
            version="2.39.2",
        )

        with patch(
            "IgnoreScope.cli.commands.GitInstaller"
        ) as MockInstaller:
            instance = MockInstaller.return_value
            instance.deploy.return_value = mock_result
            instance.configure_identity.return_value = (True, "OK")

            success, msg = cmd_install_git(
                tmp_path, "default",
                configure=True, name="Test", email="t@t.com"
            )

            assert success is True
            assert "Test" in msg
            assert "t@t.com" in msg
            instance.configure_identity.assert_called_once()

    def test_failure(self, tmp_path: Path):
        """Returns (False, message) when deploy fails."""
        from IgnoreScope.cli.commands import cmd_install_git
        from IgnoreScope.container_ext.install_extension import DeployResult

        mock_result = DeployResult(
            success=False,
            message="Container not available: not found",
        )

        with patch(
            "IgnoreScope.cli.commands.GitInstaller"
        ) as MockInstaller:
            instance = MockInstaller.return_value
            instance.deploy.return_value = mock_result

            success, msg = cmd_install_git(tmp_path, "default")

            assert success is False
            assert "not available" in msg
