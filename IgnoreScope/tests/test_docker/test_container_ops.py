"""Tests for docker container operations (container_ops.py).

Verifies function contracts for all container-side operations:
  - Docker availability checks
  - Container lifecycle (create, start, stop, remove)
  - Image and volume management
  - File push/pull via docker cp

All subprocess calls are mocked — no Docker required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# lifecycle.py functions
# =============================================================================

class TestLifecycleIsDockerInstalled:
    """Tests for lifecycle.is_docker_installed."""

    def test_docker_found(self):
        """Returns True when docker binary exists on PATH."""
        from IgnoreScope.docker.container_ops import is_docker_installed

        with patch("shutil.which", return_value="/usr/bin/docker"):
            assert is_docker_installed() is True

    def test_docker_not_found(self):
        """Returns False when docker binary not on PATH."""
        from IgnoreScope.docker.container_ops import is_docker_installed

        with patch("shutil.which", return_value=None):
            assert is_docker_installed() is False


class TestLifecycleIsDockerRunning:
    """Tests for lifecycle.is_docker_running."""

    def test_running(self):
        """Returns (True, message) when docker info succeeds."""
        from IgnoreScope.docker.container_ops import is_docker_running

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            running, msg = is_docker_running()
            assert running is True
            assert "running" in msg.lower()

    def test_not_installed(self):
        """Returns (False, message) when docker not installed."""
        from IgnoreScope.docker.container_ops import is_docker_running

        with patch("shutil.which", return_value=None):
            running, msg = is_docker_running()
            assert running is False
            assert "not installed" in msg.lower()


class TestLifecycleGetContainerInfo:
    """Tests for lifecycle.get_container_info."""

    def test_returns_info_dict(self):
        """Returns dict with id, status, running, image, created on success."""
        from IgnoreScope.docker.container_ops import get_container_info

        inspect_data = [{
            "Id": "abc123def456789",
            "State": {"Status": "running", "Running": True},
            "Config": {"Image": "my-image:latest"},
            "Created": "2026-01-01T00:00:00Z",
        }]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(inspect_data)

        with patch("subprocess.run", return_value=mock_result):
            info = get_container_info("my-container")

        assert info is not None
        assert info["id"] == "abc123def456"  # Truncated to 12 chars
        assert info["status"] == "running"
        assert info["running"] is True
        assert info["image"] == "my-image:latest"

    def test_returns_none_on_not_found(self):
        """Returns None when container doesn't exist."""
        from IgnoreScope.docker.container_ops import get_container_info

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            assert get_container_info("nonexistent") is None

    def test_returns_none_on_exception(self):
        """Returns None on subprocess error."""
        from IgnoreScope.docker.container_ops import get_container_info

        with patch("subprocess.run", side_effect=Exception("error")):
            assert get_container_info("my-container") is None


class TestLifecycleStartStop:
    """Tests for lifecycle.start_container and stop_container."""

    def test_start_success(self):
        """Returns (True, message) on successful start."""
        from IgnoreScope.docker.container_ops import start_container

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            success, msg = start_container("my-container")
            assert success is True
            assert "started" in msg.lower()

    def test_start_failure(self):
        """Returns (False, message) on failed start."""
        from IgnoreScope.docker.container_ops import start_container

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Container not found"

        with patch("subprocess.run", return_value=mock_result):
            success, msg = start_container("my-container")
            assert success is False

    def test_stop_success(self):
        """Returns (True, message) on successful stop."""
        from IgnoreScope.docker.container_ops import stop_container

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            success, msg = stop_container("my-container")
            assert success is True
            assert "stopped" in msg.lower()

    def test_stop_failure(self):
        """Returns (False, message) on failed stop."""
        from IgnoreScope.docker.container_ops import stop_container

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Container not found"

        with patch("subprocess.run", return_value=mock_result):
            success, msg = stop_container("my-container")
            assert success is False


class TestLifecycleImageExists:
    """Tests for lifecycle.image_exists."""

    def test_exists(self):
        """Returns True when image ID returned."""
        from IgnoreScope.docker.container_ops import image_exists

        mock_result = MagicMock()
        mock_result.stdout = "sha256:abc123\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            assert image_exists("my-image:latest") is True

    def test_not_exists(self):
        """Returns False when no image ID returned."""
        from IgnoreScope.docker.container_ops import image_exists

        mock_result = MagicMock()
        mock_result.stdout = "\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            assert image_exists("my-image:latest") is False


class TestLifecycleVolumeExists:
    """Tests for lifecycle.volume_exists."""

    def test_exists(self):
        """Returns True when docker volume inspect succeeds."""
        from IgnoreScope.docker.container_ops import volume_exists

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            assert volume_exists("my-volume") is True

    def test_not_exists(self):
        """Returns False when docker volume inspect fails."""
        from IgnoreScope.docker.container_ops import volume_exists

        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            assert volume_exists("my-volume") is False


class TestVolumeRemove:
    """Tests for container_ops.remove_volume."""

    def test_remove_success(self):
        """Returns (True, message) when docker volume rm succeeds."""
        from IgnoreScope.docker.container_ops import remove_volume

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            success, msg = remove_volume("my-volume")
            assert success is True
            assert "removed" in msg.lower()

    def test_remove_failure(self):
        """Returns (False, message) when docker volume rm fails."""
        from IgnoreScope.docker.container_ops import remove_volume

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "volume is in use"

        with patch("subprocess.run", return_value=mock_result):
            success, msg = remove_volume("my-volume")
            assert success is False
            assert "in use" in msg.lower()

    def test_remove_timeout(self):
        """Returns (False, message) on timeout."""
        from IgnoreScope.docker.container_ops import remove_volume
        import subprocess as _subprocess

        with patch("subprocess.run", side_effect=_subprocess.TimeoutExpired("cmd", 30)):
            success, msg = remove_volume("my-volume")
            assert success is False
            assert "timed out" in msg.lower()


# =============================================================================
# file_ops.py functions
# =============================================================================

class TestFileOpsContainerExists:
    """Tests for file_ops.container_exists (docker inspect version).

    CC-4 will keep THIS implementation as the canonical one.
    """

    def test_exists_via_inspect(self):
        """Returns True when get_container_info returns data."""
        from IgnoreScope.docker.container_ops import container_exists

        inspect_data = [{
            "Id": "abc123def456789",
            "State": {"Status": "running", "Running": True},
            "Config": {"Image": "img"},
            "Created": "2026-01-01",
        }]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(inspect_data)

        with patch("subprocess.run", return_value=mock_result):
            assert container_exists("my-container") is True

    def test_not_exists_via_inspect(self):
        """Returns False when get_container_info returns None."""
        from IgnoreScope.docker.container_ops import container_exists

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            assert container_exists("nonexistent") is False


class TestFileOpsPushFile:
    """Tests for file_ops.push_file_to_container."""

    def test_push_success(self, tmp_path: Path):
        """Returns (True, message) when docker cp succeeds."""
        from IgnoreScope.docker.container_ops import push_file_to_container

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            success, msg = push_file_to_container(
                "my-container", test_file, "/workspace/test.txt"
            )
            assert success is True

    def test_push_file_not_found(self, tmp_path: Path):
        """Returns (False, message) when host file doesn't exist."""
        from IgnoreScope.docker.container_ops import push_file_to_container

        missing = tmp_path / "missing.txt"

        success, msg = push_file_to_container(
            "my-container", missing, "/workspace/missing.txt"
        )
        assert success is False
        assert "not found" in msg.lower()

    def test_push_directory_passes_to_docker(self, tmp_path: Path):
        """Directories are passed through to docker cp (may fail if container missing)."""
        from IgnoreScope.docker.container_ops import push_file_to_container

        success, msg = push_file_to_container(
            "my-container", tmp_path, "/workspace/"
        )
        # No local guard — docker cp handles directory push natively.
        # Fails here because container doesn't exist, not because it's a directory.
        assert success is False


class TestFileOpsPullFile:
    """Tests for file_ops.pull_file_from_container."""

    def test_pull_success(self, tmp_path: Path):
        """Returns (True, message) when docker cp succeeds.

        Note: Host-side mkdir moved to file_ops.execute_pull (F-3 ownership fix).
        pull_file_from_container is now a pure docker cp wrapper — caller
        must ensure destination directory exists.
        """
        from IgnoreScope.docker.container_ops import pull_file_from_container

        output = tmp_path / "output" / "test.txt"
        # Caller (file_ops.execute_pull) is responsible for mkdir
        output.parent.mkdir(parents=True, exist_ok=True)

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            success, msg = pull_file_from_container(
                "my-container", "/workspace/test.txt", output
            )
            assert success is True

    def test_pull_failure(self, tmp_path: Path):
        """Returns (False, message) when docker cp fails."""
        from IgnoreScope.docker.container_ops import pull_file_from_container

        output = tmp_path / "output" / "test.txt"

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No such container path"

        with patch("subprocess.run", return_value=mock_result):
            success, msg = pull_file_from_container(
                "my-container", "/workspace/test.txt", output
            )
            assert success is False


class TestFileOpsEnsureContainerRunning:
    """Tests for file_ops.ensure_container_running."""

    def test_already_running(self):
        """Returns (True, message) when container already running."""
        from IgnoreScope.docker.container_ops import ensure_container_running

        inspect_data = [{
            "Id": "abc123",
            "State": {"Status": "running", "Running": True},
            "Config": {"Image": "img"},
            "Created": "2026-01-01",
        }]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(inspect_data)

        with patch("subprocess.run", return_value=mock_result):
            success, msg = ensure_container_running("my-container")
            assert success is True
            assert "already running" in msg.lower()

    def test_not_found(self):
        """Returns (False, message) when container doesn't exist."""
        from IgnoreScope.docker.container_ops import ensure_container_running

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            success, msg = ensure_container_running("nonexistent")
            assert success is False
            assert "not found" in msg.lower()


class TestFileOpsEnsureContainerDirectories:
    """Tests for file_ops.ensure_container_directories."""

    def test_creates_directories(self):
        """Calls docker exec mkdir -p with parent dirs."""
        from IgnoreScope.docker.container_ops import ensure_container_directories

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            success, msg = ensure_container_directories(
                "my-container",
                ["/workspace/src/api/config.json", "/workspace/src/vendor/lib.py"],
            )
            assert success is True
            # Should have called docker exec mkdir -p with parent directories
            call_args = mock_run.call_args[0][0]
            assert "mkdir" in call_args
            assert "-p" in call_args

    def test_no_paths_noop(self):
        """Empty paths list → immediate success, no subprocess call."""
        from IgnoreScope.docker.container_ops import ensure_container_directories

        with patch("subprocess.run") as mock_run:
            success, msg = ensure_container_directories("my-container", [])
            assert success is True
            mock_run.assert_not_called()


class TestFileOpsScanContainer:
    """Tests for file_ops.scan_container_directory."""

    def test_scan_returns_files(self):
        """Returns list of relative file paths."""
        from IgnoreScope.docker.container_ops import scan_container_directory

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "file1.py\nsubdir/file2.py\n"

        with patch("subprocess.run", return_value=mock_result):
            success, files = scan_container_directory(
                "my-container", "/workspace/src"
            )
            assert success is True
            assert "file1.py" in files
            assert "subdir/file2.py" in files

    def test_scan_empty_directory(self):
        """Returns empty list for empty directory."""
        from IgnoreScope.docker.container_ops import scan_container_directory

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            success, files = scan_container_directory(
                "my-container", "/workspace/empty"
            )
            assert success is True
            assert files == []

    def test_scan_nonexistent_directory(self):
        """Returns empty list for missing directory (not an error)."""
        from IgnoreScope.docker.container_ops import scan_container_directory

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No such file or directory"

        with patch("subprocess.run", return_value=mock_result):
            success, files = scan_container_directory(
                "my-container", "/workspace/missing"
            )
            assert success is True
            assert files == []


class TestFileOpsFileExistsInContainer:
    """Tests for file_ops.file_exists_in_container."""

    def test_file_exists(self):
        """Returns True when docker exec test -f succeeds."""
        from IgnoreScope.docker.container_ops import file_exists_in_container

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            assert file_exists_in_container("my-container", "/workspace/file.txt") is True

    def test_file_not_exists(self):
        """Returns False when docker exec test -f fails."""
        from IgnoreScope.docker.container_ops import file_exists_in_container

        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            assert file_exists_in_container("my-container", "/workspace/missing.txt") is False


class TestFileOpsRemoveFile:
    """Tests for file_ops.remove_file_from_container."""

    def test_remove_success(self):
        """Returns (True, message) when docker exec rm succeeds."""
        from IgnoreScope.docker.container_ops import remove_file_from_container

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            success, msg = remove_file_from_container(
                "my-container", "/workspace/file.txt"
            )
            assert success is True

    def test_remove_failure(self):
        """Returns (False, message) when docker exec rm fails."""
        from IgnoreScope.docker.container_ops import remove_file_from_container

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied"

        with patch("subprocess.run", return_value=mock_result):
            success, msg = remove_file_from_container(
                "my-container", "/workspace/file.txt"
            )
            assert success is False


# =============================================================================
# exec_in_container tests
# =============================================================================

class TestExecInContainer:
    """Tests for container_ops.exec_in_container."""

    def test_success_returns_stdout(self):
        """Returns (True, stdout, '') on zero exit code."""
        from IgnoreScope.docker.container_ops import exec_in_container

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hello world\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            success, stdout, stderr = exec_in_container("my-container", ["echo", "hello"])
            assert success is True
            assert stdout == "hello world"
            assert stderr == ""
            # Verify docker exec prefix
            call_args = mock_run.call_args[0][0]
            assert call_args[:3] == ["docker", "exec", "my-container"]
            assert call_args[3:] == ["echo", "hello"]

    def test_failure_returns_stderr(self):
        """Returns (False, '', stderr) on non-zero exit code."""
        from IgnoreScope.docker.container_ops import exec_in_container

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "command not found\n"

        with patch("subprocess.run", return_value=mock_result):
            success, stdout, stderr = exec_in_container("my-container", ["badcmd"])
            assert success is False
            assert stdout == ""
            assert stderr == "command not found"

    def test_timeout_returns_message(self):
        """Returns (False, '', timeout message) on TimeoutExpired."""
        from IgnoreScope.docker.container_ops import exec_in_container
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
            success, stdout, stderr = exec_in_container(
                "my-container", ["sleep", "999"], timeout=10
            )
            assert success is False
            assert stdout == ""
            assert "timed out" in stderr.lower()

    def test_exception_returns_error_string(self):
        """Returns (False, '', error) on generic exception."""
        from IgnoreScope.docker.container_ops import exec_in_container

        with patch("subprocess.run", side_effect=OSError("Docker not found")):
            success, stdout, stderr = exec_in_container("my-container", ["ls"])
            assert success is False
            assert "Docker not found" in stderr


# =============================================================================
# get_llm_command parameterization tests
# =============================================================================

class TestGetLlmCommand:
    """Tests for container_ops.get_llm_command with binary_name param."""

    def test_default_binary(self):
        """Default binary_name is 'claude'."""
        from IgnoreScope.docker.container_ops import get_llm_command

        cmd = get_llm_command("my-container", "/workspace")
        assert cmd == "docker exec -it -w /workspace my-container claude"

    def test_custom_binary(self):
        """Custom binary_name appears in generated command."""
        from IgnoreScope.docker.container_ops import get_llm_command

        cmd = get_llm_command("my-container", "/workspace", binary_name="copilot")
        assert cmd == "docker exec -it -w /workspace my-container copilot"

    def test_absolute_path_binary(self):
        """Absolute path binary appears in command — required for runtime containers."""
        from IgnoreScope.docker.container_ops import get_llm_command

        cmd = get_llm_command("my-container", "/workspace", binary_name="/root/.local/bin/claude")
        assert cmd == "docker exec -it -w /workspace my-container /root/.local/bin/claude"


# =============================================================================
# LLM deployer install commands tests
# =============================================================================

class TestClaudeDeployerInstallCommands:
    """Tests for ClaudeInstaller.get_install_commands."""

    def test_minimal_single_curl_command(self):
        """MINIMAL returns single curl installer command."""
        from IgnoreScope.container_ext.claude_extension import ClaudeInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        deployer = ClaudeInstaller()
        commands = deployer.get_install_commands(DeployMethod.MINIMAL)

        assert len(commands) == 1
        assert 'curl' in commands[0][2]
        assert deployer.NATIVE_INSTALL_URL in commands[0][2]

    def test_full_includes_prereqs_and_curl(self):
        """FULL returns apt-get prereqs step + curl installer (2 commands)."""
        from IgnoreScope.container_ext.claude_extension import ClaudeInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        deployer = ClaudeInstaller()
        commands = deployer.get_install_commands(DeployMethod.FULL)

        assert len(commands) == 2

        # First command: apt-get install of curl and ca-certificates
        prereq_cmd = commands[0][2]
        assert 'apt-get' in prereq_cmd
        assert 'curl' in prereq_cmd
        assert 'ca-certificates' in prereq_cmd

        # Second command: curl installer (same as MINIMAL)
        install_cmd = commands[1][2]
        assert 'curl' in install_cmd
        assert deployer.NATIVE_INSTALL_URL in install_cmd

    def test_full_does_not_use_npm(self):
        """FULL commands must not depend on npm/nodejs."""
        from IgnoreScope.container_ext.claude_extension import ClaudeInstaller
        from IgnoreScope.container_ext.install_extension import DeployMethod

        deployer = ClaudeInstaller()
        commands = deployer.get_install_commands(DeployMethod.FULL)

        all_text = ' '.join(str(arg) for cmd in commands for arg in cmd)
        assert 'npm' not in all_text

    def test_version_command_uses_absolute_path(self):
        """get_version_command() must use BINARY_PATH, not bare binary name."""
        from IgnoreScope.container_ext.claude_extension import ClaudeInstaller

        deployer = ClaudeInstaller()
        cmd = deployer.get_version_command()

        assert cmd[0] == deployer.BINARY_PATH
        assert cmd[0].startswith('/')
        assert cmd == ['/root/.local/bin/claude', '--version']

    def test_is_installed_uses_absolute_path(self):
        """is_installed() must use 'test -x BINARY_PATH', not 'which'."""
        from IgnoreScope.container_ext.claude_extension import ClaudeInstaller

        deployer = ClaudeInstaller()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = deployer.is_installed("my-container")

            assert result is True
            call_args = mock_run.call_args[0][0]
            # Must be: docker exec my-container test -x /root/.local/bin/claude
            assert call_args == [
                'docker', 'exec', 'my-container',
                'test', '-x', '/root/.local/bin/claude',
            ]


# =============================================================================
# Import contract tests
# =============================================================================

class TestImportContracts:
    """Verify public API imports work correctly.

    After CC-2, these imports will change source modules but the
    docker/__init__.py public API should remain the same.
    """

    def test_package_api_exports(self):
        """docker/__init__.py exports all expected functions."""
        import IgnoreScope.docker as docker_pkg

        # Container ops (consolidated from lifecycle.py + file_ops.py)
        assert hasattr(docker_pkg, "is_docker_installed")
        assert hasattr(docker_pkg, "is_docker_running")
        assert hasattr(docker_pkg, "container_exists")
        assert hasattr(docker_pkg, "image_exists")
        assert hasattr(docker_pkg, "build_image")
        assert hasattr(docker_pkg, "create_container_compose")
        assert hasattr(docker_pkg, "remove_container_compose")
        assert hasattr(docker_pkg, "start_container")
        assert hasattr(docker_pkg, "stop_container")
        assert hasattr(docker_pkg, "get_container_info")
        assert hasattr(docker_pkg, "ensure_container_running")
        assert hasattr(docker_pkg, "exec_in_container")
        assert hasattr(docker_pkg, "push_file_to_container")
        assert hasattr(docker_pkg, "pull_file_from_container")
        assert hasattr(docker_pkg, "ensure_container_directories")
        assert hasattr(docker_pkg, "scan_container_directory")
        assert hasattr(docker_pkg, "remove_file_from_container")
        assert hasattr(docker_pkg, "file_exists_in_container")
        assert hasattr(docker_pkg, "volume_exists")

        # File ops (host-side helpers)
        assert hasattr(docker_pkg, "resolve_file_subset")
        assert hasattr(docker_pkg, "resolve_pull_output")

        # Compose function
        assert hasattr(docker_pkg, "generate_compose_with_masks")

        # Names
        assert hasattr(docker_pkg, "DockerNames")

    def test_shadow_alias_removed(self):
        """Verify generate_compose_with_shadows is no longer exported (CC-6)."""
        import IgnoreScope.docker as docker_pkg

        assert not hasattr(docker_pkg, "generate_compose_with_shadows")

    def test_sanitize_scope_name_exports(self):
        """Verify sanitize_scope_name is exported from docker package."""
        import IgnoreScope.docker as docker_pkg

        assert hasattr(docker_pkg, "sanitize_scope_name")


# =============================================================================
# sanitize_volume_name tests
# =============================================================================

class TestSanitizeVolumeName:
    """Tests for docker.names.sanitize_volume_name."""

    def test_space_to_underscore(self):
        """Spaces become underscores (not silently dropped)."""
        from IgnoreScope.docker.names import sanitize_volume_name

        assert sanitize_volume_name("Dev Container") == "dev_container"


# =============================================================================
# sanitize_scope_name tests
# =============================================================================

class TestSanitizeScopeName:
    """Tests for docker.names.sanitize_scope_name."""

    def test_preserves_case(self):
        """Mixed case is preserved (Docker container names allow it)."""
        from IgnoreScope.docker.names import sanitize_scope_name

        assert sanitize_scope_name("DevContainer") == "DevContainer"

    def test_space_to_underscore(self):
        """Spaces become underscores."""
        from IgnoreScope.docker.names import sanitize_scope_name

        assert sanitize_scope_name("Dev Container") == "Dev_Container"

    def test_strips_special_chars(self):
        """Characters not in [a-zA-Z0-9_.-/\\ ] are stripped."""
        from IgnoreScope.docker.names import sanitize_scope_name

        assert sanitize_scope_name("test@v2!") == "testv2"

    def test_fallback_on_empty(self):
        """All-invalid input falls back to 'default'."""
        from IgnoreScope.docker.names import sanitize_scope_name

        assert sanitize_scope_name("!!!") == "default"
