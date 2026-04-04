"""Tests for P4McpInstaller (p4_mcp_extension.py).

Verifies install command generation, version parsing, devenv mount check,
convenience functions, deploy flow, and config deployment.
All subprocess calls are mocked.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# Properties
# =============================================================================

class TestP4McpInstallerProperties:
    """Tests for P4McpInstaller properties and constants."""

    def test_name(self):
        """name returns 'P4 MCP Server'."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.name == "P4 MCP Server"

    def test_binary_name(self):
        """binary_name returns 'p4-mcp-server'."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.binary_name == "p4-mcp-server"

    def test_supported_methods(self):
        """Only FULL deploy method is supported."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = P4McpInstaller()
        assert installer.supported_methods == [DeployMethod.FULL]

    def test_devenv_mount_default(self):
        """Default devenv mount is /devenv."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer._devenv_mount == "/devenv"

    def test_devenv_mount_custom(self):
        """Custom devenv mount is stored."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller(devenv_mount="/custom")
        assert installer._devenv_mount == "/custom"

    def test_src_dir(self):
        """src_dir computed from default devenv mount."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.src_dir == "/devenv/mcp/p4-mcp-server/linux"

    def test_src_dir_custom_mount(self):
        """src_dir computed from custom devenv mount."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller(devenv_mount="/custom")
        assert installer.src_dir == "/custom/mcp/p4-mcp-server/linux"

    def test_symlink_path_constant(self):
        """SYMLINK_PATH is the expected binary path."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        assert P4McpInstaller.SYMLINK_PATH == "/usr/local/bin/p4-mcp-server-linux"

    def test_lib_dir_constant(self):
        """LIB_DIR is the expected library directory."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        assert P4McpInstaller.LIB_DIR == "/usr/local/lib/p4-mcp-server"


# =============================================================================
# Install commands
# =============================================================================

class TestP4McpInstallerInstallCommands:
    """Tests for P4McpInstaller.get_install_commands."""

    def test_returns_single_command(self):
        """Install commands list has exactly one entry."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = P4McpInstaller()
        commands = installer.get_install_commands(DeployMethod.FULL)
        assert len(commands) == 1

    def test_command_contains_cp(self):
        """Install command includes cp -r."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = P4McpInstaller()
        commands = installer.get_install_commands(DeployMethod.FULL)
        cmd_str = commands[0][2]  # ['bash', '-c', '<command>']
        assert 'cp -r' in cmd_str

    def test_command_contains_chmod(self):
        """Install command includes chmod +x."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = P4McpInstaller()
        commands = installer.get_install_commands(DeployMethod.FULL)
        cmd_str = commands[0][2]
        assert 'chmod +x' in cmd_str

    def test_command_contains_symlink(self):
        """Install command includes ln -sf."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = P4McpInstaller()
        commands = installer.get_install_commands(DeployMethod.FULL)
        cmd_str = commands[0][2]
        assert 'ln -sf' in cmd_str

    def test_command_uses_correct_paths(self):
        """Install command references src_dir, LIB_DIR, and SYMLINK_PATH."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = P4McpInstaller()
        commands = installer.get_install_commands(DeployMethod.FULL)
        cmd_str = commands[0][2]
        assert '/devenv/mcp/p4-mcp-server/linux' in cmd_str
        assert '/usr/local/lib/p4-mcp-server' in cmd_str
        assert '/usr/local/bin/p4-mcp-server-linux' in cmd_str

    def test_command_uses_custom_mount(self):
        """Install command adapts to custom devenv mount."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = P4McpInstaller(devenv_mount="/myenv")
        commands = installer.get_install_commands(DeployMethod.FULL)
        cmd_str = commands[0][2]
        assert '/myenv/mcp/p4-mcp-server/linux' in cmd_str


# =============================================================================
# Version parsing
# =============================================================================

class TestP4McpInstallerVersionParsing:
    """Tests for P4McpInstaller version command and parsing."""

    def test_version_command(self):
        """get_version_command returns [SYMLINK_PATH, '--version']."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.get_version_command() == [
            "/usr/local/bin/p4-mcp-server-linux", "--version"
        ]

    def test_parse_semver(self):
        """Parses '1.2.3' from plain semver."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.parse_version_output("1.2.3") == "1.2.3"

    def test_parse_v_prefix(self):
        """Strips v prefix from 'v1.0.0'."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.parse_version_output("v1.0.0") == "1.0.0"

    def test_parse_empty(self):
        """Returns None for empty output."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.parse_version_output("") is None

    def test_parse_non_version_fallback(self):
        """Non-version but non-empty output returns 'installed'."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.parse_version_output("some binary output") == "installed"

    def test_parse_whitespace_only(self):
        """Whitespace-only output returns None."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()
        assert installer.parse_version_output("   ") is None


# =============================================================================
# is_installed
# =============================================================================

class TestP4McpInstallerIsInstalled:
    """Tests for P4McpInstaller.is_installed."""

    def test_is_installed_uses_test_x(self):
        """is_installed runs 'docker exec <container> test -x' on SYMLINK_PATH."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer.is_installed("my-container")

            assert result is True
            call_args = mock_run.call_args[0][0]
            assert call_args == [
                'docker', 'exec', 'my-container',
                'test', '-x', '/usr/local/bin/p4-mcp-server-linux',
            ]

    def test_is_installed_returns_false_when_missing(self):
        """is_installed returns False when binary is not found."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = installer.is_installed("my-container")
            assert result is False


# =============================================================================
# check_devenv_mount
# =============================================================================

class TestP4McpInstallerCheckDevenvMount:
    """Tests for P4McpInstaller.check_devenv_mount."""

    def test_mount_present(self):
        """When devenv mount exists, returns (True, '')."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            ok, msg = installer.check_devenv_mount("my-container")
            assert ok is True
            assert msg == ""

    def test_mount_missing(self):
        """When devenv mount is absent, returns (False, error_message)."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            ok, msg = installer.check_devenv_mount("my-container")
            assert ok is False
            assert "/devenv" in msg
            assert "IgnoreScope GUI" in msg


# =============================================================================
# Convenience functions
# =============================================================================

class TestConvenienceFunctions:
    """Tests for deploy_p4_mcp and verify_p4_mcp."""

    def test_deploy_p4_mcp_delegates(self):
        """deploy_p4_mcp creates installer and calls deploy."""
        from IgnoreScope.container_ext.p4_mcp_extension import deploy_p4_mcp, P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployResult

        with patch.object(P4McpInstaller, "deploy", return_value=DeployResult(
            success=True, message="ok"
        )) as mock_deploy:
            result = deploy_p4_mcp("test-container")
            assert result.success is True
            mock_deploy.assert_called_once_with("test-container", timeout=60)

    def test_verify_p4_mcp_delegates(self):
        """verify_p4_mcp creates installer and calls verify."""
        from IgnoreScope.container_ext.p4_mcp_extension import verify_p4_mcp, P4McpInstaller
        from IgnoreScope.container_ext.install_extension import DeployResult

        with patch.object(P4McpInstaller, "verify", return_value=DeployResult(
            success=True, message="installed", version="1.0.0"
        )) as mock_verify:
            result = verify_p4_mcp("test-container")
            assert result.success is True
            assert result.version == "1.0.0"
            mock_verify.assert_called_once_with("test-container")


# =============================================================================
# Deploy flow
# =============================================================================

class TestP4McpInstallerDeploy:
    """Tests for P4McpInstaller.deploy() end-to-end flow.

    Mocks at docker module function level (ensure_container_running,
    exec_in_container) rather than subprocess.run, because
    ensure_container_running parses JSON output internally.
    """

    def test_deploy_full_flow(self):
        """Happy path: container running -> devenv check -> install -> verify -> success."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            mock_exec.side_effect = [
                (True, "", ""),            # check_devenv_mount
                (True, "staged OK", ""),   # install command
                (True, "1.0.0", ""),       # verify
            ]

            result = installer.deploy("test-container")

            assert result.success is True

    def test_deploy_container_not_running(self):
        """deploy() returns failure when container is not running."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with patch(
            "IgnoreScope.docker.ensure_container_running",
            return_value=(False, "not found"),
        ):
            result = installer.deploy("nonexistent")

            assert result.success is False
            assert "not available" in result.message.lower()

    def test_deploy_devenv_missing(self):
        """deploy() returns failure with guidance when devenv mount missing."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            # check_devenv_mount fails
            mock_exec.return_value = (False, "", "")

            result = installer.deploy("test-container")

            assert result.success is False
            assert "/devenv" in result.message

    def test_deploy_install_fails(self):
        """deploy() returns failure when cp/symlink command fails."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            mock_exec.side_effect = [
                (True, "", ""),             # check_devenv_mount ok
                (False, "", "cp failed"),   # install fails
            ]

            result = installer.deploy("test-container")

            assert result.success is False

    def test_deploy_verify_fails(self):
        """deploy() returns failure when install succeeds but verify fails."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            mock_exec.side_effect = [
                (True, "", ""),            # check_devenv_mount ok
                (True, "staged OK", ""),   # install succeeds
                (False, "", "not found"),  # verify fails
            ]

            result = installer.deploy("test-container")

            assert result.success is False
            assert "verification failed" in result.message.lower()


# =============================================================================
# Config deployment
# =============================================================================

class TestP4McpInstallerDeployConfig:
    """Tests for P4McpInstaller.deploy_config() — .p4config and .p4ignore."""

    def test_deploy_config_renders_tokens(self):
        """deploy_config() substitutes P4 tokens in p4config template."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with patch(
            "IgnoreScope.docker.push_file_to_container",
            return_value=(True, "ok"),
        ) as mock_push:
            results = installer.deploy_config(
                "test-container",
                {"p4port": "ssl:perforce:1666", "p4user": "dev", "p4client": "ws_dev"},
                "/MyProject",
                "/MyProject/.ignore_scope/mydev",
            )

            assert len(results) == 2
            assert results[0].success is True
            assert results[1].success is True

            # First push = .p4config -> scope_dir
            first_dest = mock_push.call_args_list[0][0][2]
            assert first_dest == "/MyProject/.ignore_scope/mydev/.p4config"

            # Second push = .p4ignore -> project_dir
            second_dest = mock_push.call_args_list[1][0][2]
            assert second_dest == "/MyProject/.p4ignore"

    def test_deploy_config_p4config_push_fails(self):
        """deploy_config() stops and returns failure when p4config push fails."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with patch(
            "IgnoreScope.docker.push_file_to_container",
            return_value=(False, "connection error"),
        ):
            results = installer.deploy_config(
                "test-container",
                {"p4port": "ssl:perforce:1666", "p4user": "dev", "p4client": "ws"},
                "/MyProject",
                "/MyProject/.ignore_scope/dev",
            )

            # Should stop after first failure (only 1 result)
            assert len(results) == 1
            assert results[0].success is False
            assert "p4config" in results[0].message.lower()

    def test_deploy_config_p4ignore_push_fails(self):
        """deploy_config() returns partial success when p4ignore push fails."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        call_count = 0

        def mock_push(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (True, "ok")  # p4config succeeds
            return (False, "disk full")  # p4ignore fails

        with patch(
            "IgnoreScope.docker.push_file_to_container",
            side_effect=mock_push,
        ):
            results = installer.deploy_config(
                "test-container",
                {"p4port": "ssl:perforce:1666", "p4user": "dev", "p4client": "ws"},
                "/MyProject",
                "/MyProject/.ignore_scope/dev",
            )

            assert len(results) == 2
            assert results[0].success is True
            assert results[1].success is False
            assert "p4ignore" in results[1].message.lower()

    def test_deploy_config_missing_tokens(self):
        """deploy_config() with empty context replaces tokens with empty strings."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        installer = P4McpInstaller()

        with patch(
            "IgnoreScope.docker.push_file_to_container",
            return_value=(True, "ok"),
        ):
            results = installer.deploy_config(
                "test-container",
                {},  # no tokens
                "/MyProject",
                "/MyProject/.ignore_scope/dev",
            )

            # Should still succeed (empty values are valid)
            assert len(results) == 2
            assert all(r.success for r in results)

    def test_p4config_template_has_tokens(self):
        """P4CONFIG_TEMPLATE contains expected placeholder tokens."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        tpl = P4McpInstaller.P4CONFIG_TEMPLATE
        assert "{p4port}" in tpl
        assert "{p4user}" in tpl
        assert "{p4client}" in tpl

    def test_p4ignore_template_is_static(self):
        """P4IGNORE_TEMPLATE has no placeholder tokens."""
        from IgnoreScope.container_ext.p4_mcp_extension import P4McpInstaller

        tpl = P4McpInstaller.P4IGNORE_TEMPLATE
        assert "{" not in tpl
        assert ".git" in tpl
        assert ".ignore_scope/" in tpl
