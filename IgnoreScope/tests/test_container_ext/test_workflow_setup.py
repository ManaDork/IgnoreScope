"""Tests for WorkflowSetup (workflow_setup.py).

Verifies computed paths, template rendering, step ordering,
devenv precondition check, and config update. All docker calls are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from IgnoreScope.container_ext.workflow_setup import WorkflowSetup
from IgnoreScope.container_ext.install_extension import DeployResult


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def setup() -> WorkflowSetup:
    """Standard WorkflowSetup instance for testing."""
    return WorkflowSetup(
        host_project_root=Path("S:/Games/MyGame"),
        scope_name="dev",
        p4port="ssl:perforce.example.com:1666",
        p4user="testuser",
        p4client="testuser-MyGame",
        git_user="Test User",
        git_email="test@example.com",
        github_remote_url="https://github.com/test/mygame.git",
    )


# =============================================================================
# Computed paths
# =============================================================================

class TestComputedPaths:
    """Tests for WorkflowSetup computed path properties."""

    def test_project_dir(self, setup: WorkflowSetup):
        """project_dir = /{project_name}."""
        assert setup.project_dir == "/MyGame"

    def test_scope_dir(self, setup: WorkflowSetup):
        """scope_dir = /{project}/.ignore_scope/{scope}."""
        assert setup.scope_dir == "/MyGame/.ignore_scope/dev"

    def test_git_dir(self, setup: WorkflowSetup):
        """git_dir = scope_dir/.git."""
        assert setup.git_dir == "/MyGame/.ignore_scope/dev/.git"

    def test_project_dir_preserves_name(self):
        """Project name with spaces is preserved."""
        ws = WorkflowSetup(
            host_project_root=Path("S:/My Project"),
            scope_name="default",
            p4port="", p4user="", p4client="",
        )
        assert ws.project_dir == "/My Project"


# =============================================================================
# Template rendering
# =============================================================================

class TestTemplateRendering:
    """Tests for _render_template placeholder substitution.

    Note: gitignore, p4config, p4ignore templates have been migrated to
    their respective extension classes (GitInstaller, P4McpInstaller).
    Only composite workflow templates (mcp.json, seed_claude_md.md) remain
    in the templates/ directory and are rendered by WorkflowSetup.
    """

    def test_all_tokens_replaced_in_mcp_json(self, setup: WorkflowSetup):
        """All known tokens in mcp.json are substituted."""
        content = setup._render_template("mcp.json")
        for token in ["{scope_dir}", "{p4_mcp_dest}"]:
            assert token not in content, f"Token {token} was not replaced"

    def test_mcp_json_absolute_p4config(self, setup: WorkflowSetup):
        """mcp.json renders P4CONFIG as absolute path to scope dir."""
        content = setup._render_template("mcp.json")
        assert "/MyGame/.ignore_scope/dev/.p4config" in content
        # Must NOT contain relative .p4config
        assert '"P4CONFIG": ".p4config"' not in content

    def test_mcp_json_p4_mcp_dest(self, setup: WorkflowSetup):
        """mcp.json renders P4 MCP command from class constant."""
        content = setup._render_template("mcp.json")
        assert WorkflowSetup.P4_MCP_DEST in content

    def test_seed_claude_md_project_and_scope(self, setup: WorkflowSetup):
        """seed_claude_md renders project name and scope."""
        content = setup._render_template("seed_claude_md.md")
        assert "/MyGame" in content
        assert "dev" in content


# =============================================================================
# P4_MCP_DEST constant
# =============================================================================

class TestP4McpDest:
    """Tests for P4_MCP_DEST class constant consistency."""

    def test_constant_value(self):
        """P4_MCP_DEST is the expected binary path."""
        assert WorkflowSetup.P4_MCP_DEST == "/usr/local/bin/p4-mcp-server-linux"


# =============================================================================
# stage_p4_mcp_binary — devenv precondition
# =============================================================================

class TestStageP4McpPrecondition:
    """Tests for devenv mount precondition check in stage_p4_mcp_binary.

    After extraction, stage_p4_mcp_binary delegates to P4McpInstaller.deploy()
    which calls ensure_container_running → check_devenv_mount → deploy_runtime
    (ensure_container_running + install + verify).
    """

    def test_missing_devenv_returns_targeted_error(self, setup: WorkflowSetup):
        """When /devenv mount is absent, returns clear error message."""
        with patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")), \
             patch("IgnoreScope.docker.exec_in_container") as mock_exec:
            # First call: test -d "/devenv" → fails
            mock_exec.return_value = (False, "", "")

            result = setup.stage_p4_mcp_binary()

            assert result.success is False
            assert "/devenv" in result.message
            assert "IgnoreScope GUI" in result.message
            # Should NOT proceed to the install command
            assert mock_exec.call_count == 1

    def test_devenv_present_proceeds_to_copy(self, setup: WorkflowSetup):
        """When /devenv mount exists, proceeds to copy step and verifies."""
        with patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")), \
             patch("IgnoreScope.docker.exec_in_container") as mock_exec:
            # deploy() → check_devenv_mount → deploy_runtime (install + verify)
            mock_exec.side_effect = [
                (True, "", ""),           # devenv check
                (True, "staged OK", ""),  # install command (cp + symlink)
                (True, "1.0.0", ""),      # verify (version check)
            ]

            result = setup.stage_p4_mcp_binary()

            assert result.success is True
            assert mock_exec.call_count == 3


# =============================================================================
# write_workspace_files — file ordering
# =============================================================================

class TestWriteWorkspaceFilesOrder:
    """Tests for file write ordering in write_workspace_files."""

    def test_p4ignore_before_gitignore(self, setup: WorkflowSetup):
        """In file_map, .p4ignore is written before .gitignore."""
        pushed_files: list[str] = []

        with patch("IgnoreScope.docker.ensure_container_directories", return_value=(True, "")), \
             patch("IgnoreScope.docker.file_exists_in_container", return_value=False), \
             patch("IgnoreScope.docker.push_file_to_container") as mock_push:
            mock_push.return_value = (True, "")

            result = setup.write_workspace_files()

            # Collect container_dest args from push calls
            for call in mock_push.call_args_list:
                pushed_files.append(call[0][2])  # 3rd positional arg = container_dest

        p4ignore_idx = next(i for i, f in enumerate(pushed_files) if ".p4ignore" in f)
        gitignore_idx = next(i for i, f in enumerate(pushed_files) if ".gitignore" in f)
        assert p4ignore_idx < gitignore_idx, ".p4ignore must be written before .gitignore"

    def test_existing_p4ignore_noted(self, setup: WorkflowSetup):
        """When .p4ignore already exists, result notes overwrite."""
        with patch("IgnoreScope.docker.ensure_container_directories", return_value=(True, "")), \
             patch("IgnoreScope.docker.file_exists_in_container", return_value=True), \
             patch("IgnoreScope.docker.push_file_to_container", return_value=(True, "")):

            result = setup.write_workspace_files()

            assert result.success is True
            written = result.details["written"]
            p4ignore_entry = [w for w in written if ".p4ignore" in w][0]
            assert "(overwritten)" in p4ignore_entry


# =============================================================================
# setup_git — env var location
# =============================================================================

class TestSetupGitEnvVars:
    """Tests for git env var placement in setup_git."""

    def test_writes_to_profile_d_not_bashrc(self, setup: WorkflowSetup):
        """GIT_DIR/GIT_WORK_TREE written to /etc/profile.d/, not .bashrc."""
        from IgnoreScope.container_ext.git_extension import GitInstaller

        exec_calls: list[str] = []

        def capture_exec(container, cmd, timeout=None):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            exec_calls.append(cmd_str)
            return (True, "Initialized empty Git repository", "")

        with patch("IgnoreScope.docker.exec_in_container", side_effect=capture_exec), \
             patch.object(
                 GitInstaller, "configure_identity", return_value=(True, "OK")
             ):
            result = setup.setup_git()

        assert result.success is True

        # Find the env var command
        env_cmd = [c for c in exec_calls if "profile.d" in c]
        assert len(env_cmd) == 1, "Should write to /etc/profile.d/"
        assert "/etc/profile.d/git-env.sh" in env_cmd[0]
        assert "/etc/environment" in env_cmd[0]

        # Must NOT write to .bashrc
        bashrc_cmds = [c for c in exec_calls if ".bashrc" in c]
        assert len(bashrc_cmds) == 0, "Should NOT write to .bashrc"


# =============================================================================
# run_full_setup — step ordering + config update
# =============================================================================

class TestRunFullSetup:
    """Tests for orchestrator step execution."""

    def test_stops_on_first_failure(self, setup: WorkflowSetup):
        """run_full_setup stops executing after first failure."""
        call_count = 0

        def fail_on_third(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                return DeployResult(success=False, message="step 3 failed")
            return DeployResult(success=True, message="ok")

        with patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")), \
             patch.object(setup, "install_system_deps", side_effect=lambda: fail_on_third()), \
             patch.object(setup, "install_git", side_effect=lambda: fail_on_third()), \
             patch.object(setup, "install_p4_cli", side_effect=lambda: fail_on_third()):

            results = setup.run_full_setup()

        assert len(results) == 3
        assert results[-1][1].success is False

    def test_all_nine_steps_present(self, setup: WorkflowSetup):
        """run_full_setup has exactly 9 steps in the correct order."""
        expected = [
            "install_system_deps", "install_git", "install_p4_cli",
            "stage_p4_mcp_binary", "install_claude", "install_bootstrap",
            "install_context_mode", "write_workspace_files", "setup_git",
        ]

        # Mock everything to succeed and collect step names
        def mock_success():
            return DeployResult(success=True, message="ok")

        with patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")):
            for step_name in expected:
                setattr(setup, step_name, mock_success)

            # Also mock _update_config_pushed_files since all steps succeed
            with patch.object(setup, "_update_config_pushed_files"):
                results = setup.run_full_setup()

        step_names = [name for name, _ in results]
        assert step_names == expected

    def test_config_update_on_full_success(self, setup: WorkflowSetup):
        """_update_config_pushed_files called when all steps succeed."""
        def mock_success():
            return DeployResult(success=True, message="ok")

        with patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")), \
             patch.object(setup, "_update_config_pushed_files") as mock_update:
            for name in ["install_system_deps", "install_git", "install_p4_cli",
                         "stage_p4_mcp_binary", "install_claude", "install_bootstrap",
                         "install_context_mode", "write_workspace_files", "setup_git"]:
                setattr(setup, name, mock_success)

            setup.run_full_setup()

        mock_update.assert_called_once()

    def test_config_update_skipped_on_failure(self, setup: WorkflowSetup):
        """_update_config_pushed_files NOT called when a step fails."""
        call_idx = 0

        def mock_step():
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return DeployResult(success=False, message="fail")
            return DeployResult(success=True, message="ok")

        with patch("IgnoreScope.docker.ensure_container_running", return_value=(True, "")), \
             patch.object(setup, "_update_config_pushed_files") as mock_update, \
             patch.object(setup, "install_system_deps", side_effect=mock_step):

            setup.run_full_setup()

        mock_update.assert_not_called()
