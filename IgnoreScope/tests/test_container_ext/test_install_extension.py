"""Tests for ExtensionInstaller base class (install_extension.py).

Verifies the deploy_runtime() template method flow using a minimal
concrete subclass. All docker calls are mocked.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from IgnoreScope.container_ext.install_extension import (
    ExtensionInstaller,
    DeployMethod,
    DeployResult,
)


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------

class _StubInstaller(ExtensionInstaller):
    """Minimal concrete ExtensionInstaller for testing base class flow."""

    def __init__(self, install_commands=None, version_output="1.0.0"):
        self._install_commands = (
            install_commands if install_commands is not None
            else [['bash', '-c', 'echo install']]
        )
        self._version_output = version_output

    @property
    def name(self) -> str:
        return "Stub"

    @property
    def binary_name(self) -> str:
        return "stub"

    @property
    def supported_methods(self) -> list[DeployMethod]:
        return [DeployMethod.FULL]

    def get_install_commands(self, method: DeployMethod) -> list[list[str]]:
        return list(self._install_commands)

    def get_version_command(self) -> list[str]:
        return ['stub', '--version']

    def parse_version_output(self, output: str) -> str | None:
        return output.strip() if output and output.strip() else None


# =============================================================================
# deploy_runtime() flow
# =============================================================================

class TestDeployRuntime:
    """Tests for ExtensionInstaller.deploy_runtime() template method."""

    def test_deploy_success_full_flow(self):
        """Happy path: container running -> install -> verify -> success."""
        installer = _StubInstaller()

        with (
            patch(
                "IgnoreScope.docker.ensure_container_running",
                return_value=(True, "running"),
            ),
            patch(
                "IgnoreScope.docker.exec_in_container",
            ) as mock_exec,
        ):
            # Install succeeds, verify succeeds with version
            mock_exec.side_effect = [
                (True, "install ok", ""),   # install command
                (True, "1.0.0", ""),        # verify command
            ]

            result = installer.deploy_runtime("test-container", DeployMethod.FULL)

            assert result.success is True
            assert result.version == "1.0.0"
            assert result.method == DeployMethod.FULL
            assert mock_exec.call_count == 2

    def test_deploy_container_not_running(self):
        """Container not running -> immediate failure."""
        installer = _StubInstaller()

        with patch(
            "IgnoreScope.docker.ensure_container_running",
            return_value=(False, "not found"),
        ):
            result = installer.deploy_runtime("test-container")

            assert result.success is False
            assert "not available" in result.message.lower()

    def test_deploy_install_fails(self):
        """Install command returns non-zero -> failure."""
        installer = _StubInstaller()

        with (
            patch(
                "IgnoreScope.docker.ensure_container_running",
                return_value=(True, "running"),
            ),
            patch(
                "IgnoreScope.docker.exec_in_container",
                return_value=(False, "", "apt-get failed"),
            ),
        ):
            result = installer.deploy_runtime("test-container")

            assert result.success is False
            assert "failed" in result.message.lower()

    def test_deploy_verify_fails(self):
        """Install succeeds but verification fails -> failure."""
        installer = _StubInstaller()

        with (
            patch(
                "IgnoreScope.docker.ensure_container_running",
                return_value=(True, "running"),
            ),
            patch(
                "IgnoreScope.docker.exec_in_container",
            ) as mock_exec,
        ):
            mock_exec.side_effect = [
                (True, "install ok", ""),    # install succeeds
                (False, "", "not found"),    # verify fails
            ]

            result = installer.deploy_runtime("test-container")

            assert result.success is False
            assert "verification failed" in result.message.lower()

    def test_deploy_multiple_commands_executed_in_order(self):
        """Multiple install commands are executed sequentially."""
        installer = _StubInstaller(install_commands=[
            ['bash', '-c', 'step 1'],
            ['bash', '-c', 'step 2'],
            ['bash', '-c', 'step 3'],
        ])

        with (
            patch(
                "IgnoreScope.docker.ensure_container_running",
                return_value=(True, "running"),
            ),
            patch(
                "IgnoreScope.docker.exec_in_container",
            ) as mock_exec,
        ):
            mock_exec.side_effect = [
                (True, "", ""),     # step 1
                (True, "", ""),     # step 2
                (True, "", ""),     # step 3
                (True, "1.0.0", ""),  # verify
            ]

            result = installer.deploy_runtime("test-container")

            assert result.success is True
            assert mock_exec.call_count == 4

    def test_deploy_stops_on_first_command_failure(self):
        """If second of three install commands fails, third is not run."""
        installer = _StubInstaller(install_commands=[
            ['bash', '-c', 'step 1'],
            ['bash', '-c', 'step 2'],
            ['bash', '-c', 'step 3'],
        ])

        with (
            patch(
                "IgnoreScope.docker.ensure_container_running",
                return_value=(True, "running"),
            ),
            patch(
                "IgnoreScope.docker.exec_in_container",
            ) as mock_exec,
        ):
            mock_exec.side_effect = [
                (True, "", ""),           # step 1 ok
                (False, "", "error"),     # step 2 fails
            ]

            result = installer.deploy_runtime("test-container")

            assert result.success is False
            assert mock_exec.call_count == 2  # step 3 never called

    def test_deploy_no_commands_returns_failure(self):
        """Empty install commands list returns failure."""
        installer = _StubInstaller(install_commands=[])

        with patch(
            "IgnoreScope.docker.ensure_container_running",
            return_value=(True, "running"),
        ):
            result = installer.deploy_runtime("test-container")

            assert result.success is False
            assert "no installation commands" in result.message.lower()


# =============================================================================
# verify()
# =============================================================================

class TestVerify:
    """Tests for ExtensionInstaller.verify()."""

    def test_verify_success(self):
        """Verify returns version when binary responds."""
        installer = _StubInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1.0.0"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = installer.verify("test-container")

            assert result.success is True
            assert result.version == "1.0.0"

    def test_verify_not_installed(self):
        """Verify returns failure when binary not found."""
        installer = _StubInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "not found"

        with patch("subprocess.run", return_value=mock_result):
            result = installer.verify("test-container")

            assert result.success is False
            assert "not found" in result.message.lower() or "not functional" in result.message.lower()
