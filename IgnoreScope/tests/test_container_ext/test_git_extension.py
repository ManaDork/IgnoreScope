"""Tests for GitInstaller (git_extension.py).

Verifies install command generation, version parsing, distro detection,
identity configuration, deploy flow, and config deployment.
All subprocess calls are mocked.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# Install commands
# =============================================================================

class TestGitInstallerInstallCommands:
    """Tests for GitInstaller.get_install_commands."""

    def test_debian_install_command(self):
        """Debian distro returns apt-get command with git."""
        from IgnoreScope.container_ext.git_extension import GitInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = GitInstaller()
        installer._resolved_distro = "debian"
        commands = installer.get_install_commands(DeployMethod.FULL)

        assert len(commands) == 1
        cmd_str = commands[0][2]  # ['bash', '-c', '<command>']
        assert 'apt-get' in cmd_str
        assert 'git' in cmd_str
        assert 'apk' not in cmd_str

    def test_alpine_install_command(self):
        """Alpine distro returns apk command with git."""
        from IgnoreScope.container_ext.git_extension import GitInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        installer = GitInstaller()
        installer._resolved_distro = "alpine"
        commands = installer.get_install_commands(DeployMethod.FULL)

        assert len(commands) == 1
        cmd_str = commands[0][2]  # ['sh', '-c', '<command>']
        assert 'apk' in cmd_str
        assert 'git' in cmd_str
        assert 'apt-get' not in cmd_str

    def test_version_command(self):
        """get_version_command returns ['git', '--version']."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()
        assert installer.get_version_command() == ['git', '--version']

    def test_version_parsing_valid(self):
        """Parses '2.39.2' from 'git version 2.39.2'."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()
        assert installer.parse_version_output("git version 2.39.2") == "2.39.2"

    def test_version_parsing_empty(self):
        """Returns None for empty output."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()
        assert installer.parse_version_output("") is None

    def test_is_installed_uses_test_x(self):
        """is_installed runs 'docker exec <container> test -x /usr/bin/git'."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

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
                'test', '-x', '/usr/bin/git',
            ]

    def test_detect_distro_debian(self):
        """When 'command -v apk' fails, detect_distro returns 'debian'."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            assert installer.detect_distro("my-container") == "debian"

    def test_detect_distro_alpine(self):
        """When 'command -v apk' succeeds, detect_distro returns 'alpine'."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/sbin/apk\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            assert installer.detect_distro("my-container") == "alpine"


# =============================================================================
# Identity configuration
# =============================================================================

class TestGitInstallerConfigureIdentity:
    """Tests for GitInstaller.configure_identity."""

    def test_configure_sets_name_and_email(self):
        """configure_identity runs git config commands with correct args."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            ok, msg = installer.configure_identity(
                "my-container", "Test User", "test@example.com"
            )

            assert ok is True
            assert "Test User" in msg
            assert "test@example.com" in msg

            # Verify docker exec was called with git config commands
            call_args = mock_run.call_args[0][0]
            assert call_args[:3] == ['docker', 'exec', 'my-container']
            cmd_str = ' '.join(call_args[3:])
            assert 'git config --global user.name' in cmd_str
            assert 'git config --global user.email' in cmd_str


# =============================================================================
# Deploy flow
# =============================================================================

class TestGitInstallerDeploy:
    """Tests for GitInstaller.deploy() end-to-end flow.

    Mocks at docker module function level (ensure_container_running,
    exec_in_container) rather than subprocess.run, because
    ensure_container_running parses JSON output internally.
    """

    def test_deploy_auto_detects_distro(self):
        """deploy(distro='auto') detects distro, runs install, verifies."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            mock_exec.side_effect = [
                (False, "", ""),                 # detect_distro: apk not found → debian
                (True, "install ok", ""),         # install command
                (True, "git version 2.39.2", ""), # verify
            ]

            result = installer.deploy("test-container", distro="auto")

            assert result.success is True
            assert installer._resolved_distro == "debian"

    def test_deploy_explicit_distro(self):
        """deploy(distro='alpine') skips detection, uses alpine commands."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            mock_exec.side_effect = [
                (True, "install ok", ""),         # install command (apk)
                (True, "git version 2.39.2", ""), # verify
            ]

            result = installer.deploy("test-container", distro="alpine")

            assert result.success is True
            assert installer._resolved_distro == "alpine"

    def test_deploy_container_not_running(self):
        """deploy() returns failure when container is not running."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with patch(
            "IgnoreScope.docker.ensure_container_running",
            return_value=(False, "not found"),
        ):
            result = installer.deploy("nonexistent-container")

            assert result.success is False
            assert "not available" in result.message.lower()

    def test_deploy_install_fails(self):
        """deploy() returns failure when install command fails."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            mock_exec.side_effect = [
                (False, "", ""),                  # detect_distro: apk fails → debian
                (False, "", "apt-get failed"),    # install fails
            ]

            result = installer.deploy("test-container")

            assert result.success is False

    def test_deploy_verify_fails(self):
        """deploy() returns failure when verification fails after install."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with (
            patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")),
            patch("IgnoreScope.docker.exec_in_container") as mock_exec,
        ):
            mock_exec.side_effect = [
                (False, "", ""),              # detect_distro → debian
                (True, "install ok", ""),     # install succeeds
                (False, "", "git not found"), # verify fails
            ]

            result = installer.deploy("test-container")

            assert result.success is False
            assert "verification failed" in result.message.lower()


# =============================================================================
# Config deployment
# =============================================================================

class TestGitInstallerDeployConfig:
    """Tests for GitInstaller.deploy_config() — .gitignore template."""

    def test_deploy_config_renders_scope_name(self):
        """deploy_config() substitutes {scope_name} in template."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with patch(
            "IgnoreScope.docker.push_file_to_container",
            return_value=(True, "ok"),
        ) as mock_push:
            results = installer.deploy_config(
                "test-container",
                {"scope_name": "mydev"},
                "/MyProject",
                "/MyProject/.ignore_scope/mydev",
            )

            assert len(results) == 1
            assert results[0].success is True
            assert "/MyProject/.gitignore" in results[0].message

            # Verify correct container destination
            push_call = mock_push.call_args
            assert push_call[0][2] == "/MyProject/.gitignore"

    def test_deploy_config_push_fails(self):
        """deploy_config() returns failure when push fails."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with patch(
            "IgnoreScope.docker.push_file_to_container",
            return_value=(False, "connection refused"),
        ):
            results = installer.deploy_config(
                "test-container",
                {"scope_name": "dev"},
                "/MyProject",
                "/MyProject/.ignore_scope/dev",
            )

            assert len(results) == 1
            assert results[0].success is False
            assert "failed" in results[0].message.lower()

    def test_deploy_config_default_scope_name(self):
        """deploy_config() uses 'default' when scope_name missing from context."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        installer = GitInstaller()

        with patch(
            "IgnoreScope.docker.push_file_to_container",
            return_value=(True, "ok"),
        ):
            results = installer.deploy_config(
                "test-container",
                {},  # empty context
                "/MyProject",
                "/MyProject/.ignore_scope/default",
            )

            assert len(results) == 1
            assert results[0].success is True

    def test_gitignore_template_has_required_patterns(self):
        """GITIGNORE_TEMPLATE contains blanket-ignore and scope whitelist."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        tpl = GitInstaller.GITIGNORE_TEMPLATE
        assert "*" in tpl
        assert "{scope_name}" in tpl
        assert "!.ignore_scope/{scope_name}/" in tpl
        assert "*.db" in tpl
