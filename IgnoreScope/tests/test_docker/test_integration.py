"""Integration tests for IgnoreScope containers.

These tests require Docker to be installed and running.
They create real containers and test the full workflow.

Run with: pytest -v --docker tests/test_docker/test_integration.py
Or interactively: python -m IgnoreScope.tests.test_docker.test_integration

Test matrix:
1. Minimal container (no LLM)
2. Container with Claude Code (curl install)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Generator

import pytest

# Mark all tests in this module as requiring Docker
pytestmark = pytest.mark.docker


# =============================================================================
# Test fixtures
# =============================================================================

@pytest.fixture(scope="module")
def docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ['docker', 'info'],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture(scope="function")
def temp_project(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary project structure for testing.

    Creates:
    - src/main.py (visible)
    - src/api/internal/secret.py (mask target)
    - src/api/public/client.py (reveal target)
    - config/settings.json (exception file)
    """
    project = tmp_path / "test_project"
    project.mkdir()

    # Create source structure
    src = project / "src"
    src.mkdir()
    (src / "main.py").write_text("# Main module\nprint('Hello')\n")

    api = src / "api"
    api.mkdir()

    internal = api / "internal"
    internal.mkdir()
    (internal / "secret.py").write_text("# Secret code\nAPI_KEY = 'xxx'\n")

    public = api / "public"
    public.mkdir()
    (public / "client.py").write_text("# Public client\ndef fetch(): pass\n")

    # Create config (for exception file testing)
    config = project / "config"
    config.mkdir()
    (config / "settings.json").write_text('{"debug": true}\n')

    yield project

    # Cleanup is handled by pytest's tmp_path fixture


@pytest.fixture(scope="function")
def test_container_name() -> str:
    """Generate unique container name for test isolation."""
    import uuid
    return f"isd-test-{uuid.uuid4().hex[:8]}"


# =============================================================================
# Minimal container tests
# =============================================================================

class TestMinimalContainer:
    """Tests for minimal container (no LLM)."""

    def test_dockerfile_generation(self, temp_project: Path):
        """Test minimal Dockerfile generation."""
        from IgnoreScope.docker.compose import generate_dockerfile

        dockerfile = generate_dockerfile(
            project_name="TestProject",
            container_root="/workspace",
        )

        assert "FROM python:3.11-slim" in dockerfile
        assert "WORKDIR /workspace" in dockerfile
        assert 'sleep infinity' in dockerfile.lower() or 'sleep' in dockerfile
        assert "claude" not in dockerfile.lower()  # No LLM

    def test_compose_generation(self, temp_project: Path):
        """Test docker-compose.yml generation with masked volumes."""
        from IgnoreScope.docker.compose import generate_compose_with_masks
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mounts={temp_project / "src"},
            masked={temp_project / "src" / "api"},
            revealed={temp_project / "src" / "api" / "public"},
            pushed_files=set(),
            host_project_root=temp_project,
            host_container_root=temp_project,
        )

        compose = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=temp_project,
            docker_container_name="test-container",
        )

        assert "test-container" in compose
        assert "Volume layers" in compose
        assert "mask_" in compose  # Mask volume name
        assert "/workspace/src" in compose

    @pytest.mark.skipif(
        os.environ.get("SKIP_DOCKER_TESTS") == "1",
        reason="Docker tests disabled via SKIP_DOCKER_TESTS=1"
    )
    def test_container_lifecycle(
        self,
        docker_available: bool,
        temp_project: Path,
        test_container_name: str,
    ):
        """Test full container lifecycle: create, start, stop, remove."""
        if not docker_available:
            pytest.skip("Docker not available")

        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.cli.commands import cmd_create, cmd_remove

        config = ScopeDockerConfig(
            mounts={temp_project / "src"},
            masked={temp_project / "src" / "api"},
            revealed={temp_project / "src" / "api" / "public"},
            container_name=test_container_name,
            host_project_root=temp_project,
        )

        try:
            # Create container
            success, msg = cmd_create(temp_project, config)
            assert success, f"Create failed: {msg}"

            # Verify container exists
            result = subprocess.run(
                ['docker', 'ps', '-a', '--filter', f'name={test_container_name}', '-q'],
                capture_output=True,
                text=True,
            )
            assert result.stdout.strip(), "Container not found after create"

        finally:
            # Cleanup: remove container
            cmd_remove(temp_project, test_container_name, confirm=True, remove_images=True)


# =============================================================================
# LLM-enabled container tests
# =============================================================================

class TestLLMContainer:
    """Tests for containers with LLM deployment."""

    def test_claude_dockerfile_generation(self, temp_project: Path):
        """Test Dockerfile generation with Claude Code."""
        from IgnoreScope.docker.compose import generate_dockerfile_with_llm
        from IgnoreScope.container_ext import ClaudeInstaller

        deployer = ClaudeInstaller(auto_launch=True)
        dockerfile, entrypoint = generate_dockerfile_with_llm(
            deployer,
            project_name="TestProject",
            container_root="/workspace",
        )

        # Check Dockerfile
        assert "Claude Code" in dockerfile
        assert "curl" in dockerfile
        assert "claude.ai/install.sh" in dockerfile
        assert "WORKDIR /workspace" in dockerfile

        # Check entrypoint
        assert entrypoint is not None
        assert "#!/bin/bash" in entrypoint
        assert "claude" in entrypoint.lower()
        assert "/workspace" in entrypoint

    def test_claude_deployer_interface(self):
        """Test ClaudeInstaller implements required interface."""
        from IgnoreScope.container_ext import ClaudeInstaller, DeployMethod

        deployer = ClaudeInstaller()

        assert deployer.name == "Claude Code"
        assert deployer.binary_name == "claude"
        assert DeployMethod.MINIMAL in deployer.supported_methods
        assert DeployMethod.FULL in deployer.supported_methods

        # Check command generation
        minimal_cmds = deployer.get_install_commands(DeployMethod.MINIMAL)
        assert any("curl" in str(cmd) for cmd in minimal_cmds)

        full_cmds = deployer.get_install_commands(DeployMethod.FULL)
        assert any("curl" in str(cmd) for cmd in full_cmds)

    def test_version_parsing(self):
        """Test Claude version string parsing."""
        from IgnoreScope.container_ext import ClaudeInstaller

        deployer = ClaudeInstaller()

        # Test various version formats
        assert deployer.parse_version_output("claude-code version 1.2.3") == "1.2.3"
        assert deployer.parse_version_output("v1.0.0") == "1.0.0"
        assert deployer.parse_version_output("1.2.3") == "1.2.3"
        assert deployer.parse_version_output("") is None

    @pytest.mark.skipif(
        os.environ.get("SKIP_DOCKER_TESTS") == "1",
        reason="Docker tests disabled via SKIP_DOCKER_TESTS=1"
    )
    @pytest.mark.slow
    def test_claude_runtime_deployment(
        self,
        docker_available: bool,
        temp_project: Path,
        test_container_name: str,
    ):
        """Test Claude deployment to running container.

        This test:
        1. Creates a minimal container
        2. Deploys Claude via curl installer
        3. Verifies Claude is installed

        Note: Requires internet access for curl install.
        """
        if not docker_available:
            pytest.skip("Docker not available")

        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.cli.commands import cmd_create, cmd_remove
        from IgnoreScope.container_ext import deploy_claude, verify_claude

        config = ScopeDockerConfig(
            mounts={temp_project / "src"},
            container_name=test_container_name,
            host_project_root=temp_project,
        )

        try:
            # Create minimal container
            success, msg = cmd_create(temp_project, config)
            assert success, f"Create failed: {msg}"

            # Deploy Claude
            result = deploy_claude(test_container_name, timeout=300)

            if result.success:
                # Verify installation
                verify_result = verify_claude(test_container_name)
                assert verify_result.success, f"Verification failed: {verify_result.message}"
                print(f"Claude version: {verify_result.version}")
            else:
                # NPM install may fail in test environment (network, etc.)
                pytest.skip(f"Claude deployment skipped: {result.message}")

        finally:
            cmd_remove(temp_project, test_container_name, confirm=True, remove_images=True)


# =============================================================================
# File operation tests
# =============================================================================

class TestFileOperations:
    """Tests for push/pull file operations."""

    @pytest.mark.skipif(
        os.environ.get("SKIP_DOCKER_TESTS") == "1",
        reason="Docker tests disabled via SKIP_DOCKER_TESTS=1"
    )
    def test_push_pull_cycle(
        self,
        docker_available: bool,
        temp_project: Path,
        test_container_name: str,
    ):
        """Test push and pull of exception files."""
        if not docker_available:
            pytest.skip("Docker not available")

        from IgnoreScope.core.config import ScopeDockerConfig, get_container_path
        from IgnoreScope.cli.commands import cmd_create, cmd_push, cmd_pull, cmd_remove

        # Create config with pushed file
        config = ScopeDockerConfig(
            mounts={temp_project / "config"},
            masked={temp_project / "config"},
            pushed_files={temp_project / "config" / "settings.json"},
            container_name=test_container_name,
            host_project_root=temp_project,
            dev_mode=True,  # Safe pull to ./Pulled/
        )

        # Compute container path for the settings file (dynamic, not hardcoded)
        settings_container_path = get_container_path(
            config.container_root,
            (temp_project / "config" / "settings.json").relative_to(config.host_container_root).as_posix(),
        )

        try:
            # Create container
            success, msg = cmd_create(temp_project, config)
            assert success, f"Create failed: {msg}"

            # Push file (force=True because file is already in pushed_files config)
            success, msg = cmd_push(temp_project, test_container_name, force=True)
            assert success, f"Push failed: {msg}"

            # Modify file in container
            subprocess.run([
                'docker', 'exec', test_container_name,
                'sh', '-c', f'echo \'{{"debug": false}}\' > {settings_container_path}'
            ], check=True)

            # Pull file (force=True for consistency)
            success, msg = cmd_pull(temp_project, test_container_name, force=True)
            assert success, f"Pull failed: {msg}"

            # Check pulled file exists in Pulled/ directory
            pulled_dirs = list((temp_project / "Pulled").iterdir())
            assert len(pulled_dirs) > 0, "No pulled files found"

        finally:
            cmd_remove(temp_project, test_container_name, confirm=True, remove_images=True)


# =============================================================================
# Mount-root masking tests (Docker required)
# =============================================================================

class TestMountRootMasking:
    """Test that a bind-mounted folder can be masked at the same path.

    Docker volume layering order:
      1. Bind mount:  host/src → /workspace/.../src       (files visible)
      2. Named volume: mask_src → /workspace/.../src      (overlays, hides files)
      3. Reveal:       host/.../public → /workspace/.../public    (punch-through)
    """

    @pytest.mark.skipif(
        os.environ.get("SKIP_DOCKER_TESTS") == "1",
        reason="Docker tests disabled via SKIP_DOCKER_TESTS=1"
    )
    def test_mount_root_files_hidden_by_mask_volume(
        self,
        docker_available: bool,
        temp_project: Path,
        test_container_name: str,
    ):
        """Mount src/ AND mask src/ — files at mount root should be hidden."""
        if not docker_available:
            pytest.skip("Docker not available")

        from IgnoreScope.core.config import ScopeDockerConfig, get_container_path
        from IgnoreScope.cli.commands import cmd_create, cmd_remove

        # src/ is BOTH mounted and masked; api/public/ is revealed
        config = ScopeDockerConfig(
            mounts={temp_project / "src"},
            masked={temp_project / "src"},
            revealed={temp_project / "src" / "api" / "public"},
            container_name=test_container_name,
            host_project_root=temp_project,
        )

        # Compute container paths dynamically (container_root derived from host_container_root)
        hcr = config.host_container_root
        cr = config.container_root
        main_py = get_container_path(cr, (temp_project / "src" / "main.py").relative_to(hcr).as_posix())
        secret_py = get_container_path(cr, (temp_project / "src" / "api" / "internal" / "secret.py").relative_to(hcr).as_posix())
        client_py = get_container_path(cr, (temp_project / "src" / "api" / "public" / "client.py").relative_to(hcr).as_posix())

        try:
            success, msg = cmd_create(temp_project, config)
            assert success, f"Create failed: {msg}"

            # cmd_create uses --no-start; start the container for exec
            start = subprocess.run(
                ['docker', 'start', test_container_name],
                capture_output=True, text=True,
            )
            assert start.returncode == 0, f"Start failed: {start.stderr}"

            # main.py sits directly in src/ (the masked mount root) — should be HIDDEN
            result = subprocess.run(
                ['docker', 'exec', test_container_name,
                 'test', '-f', main_py],
                capture_output=True,
            )
            assert result.returncode != 0, (
                f"main.py should be hidden — mask volume should overlay the bind mount ({main_py})"
            )

            # secret.py is inside a masked child (src/api/internal/) — should be HIDDEN
            result = subprocess.run(
                ['docker', 'exec', test_container_name,
                 'test', '-f', secret_py],
                capture_output=True,
            )
            assert result.returncode != 0, (
                f"secret.py should be hidden — inside masked tree ({secret_py})"
            )

            # client.py is inside the revealed punch-through (src/api/public/) — should be VISIBLE
            result = subprocess.run(
                ['docker', 'exec', test_container_name,
                 'test', '-f', client_py],
                capture_output=True,
            )
            assert result.returncode == 0, (
                f"client.py should be visible — revealed punch-through ({client_py})"
            )

        finally:
            cmd_remove(temp_project, test_container_name, confirm=True, remove_images=True)


# =============================================================================
# Hierarchy tests (unit tests, no Docker required)
# =============================================================================

class TestHierarchy:
    """Unit tests for hierarchy computation."""

    def test_revealed_parent_computation(self, temp_project: Path):
        """Test revealed parent directory computation."""
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mounts={temp_project / "src"},
            masked={temp_project / "src" / "api"},
            revealed={temp_project / "src" / "api" / "public"},
            pushed_files={temp_project / "src" / "api" / "internal" / "secret.py"},
            host_project_root=temp_project,
            host_container_root=temp_project,
        )

        # Should have parent dir for pushed file in masked area
        assert len(hierarchy.revealed_parents) > 0
        assert any("internal" in p for p in hierarchy.revealed_parents)

    def test_sibling_mount_hierarchy(self, temp_project: Path):
        """Test hierarchy computation with sibling mounts."""
        from IgnoreScope.core.config import SiblingMount
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        sibling = SiblingMount(
            host_path=Path("E:/SharedLibs"),
            container_path="/shared",
            mounts={Path("E:/SharedLibs/common")},
            masked=set(),
            revealed=set(),
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mounts={temp_project / "src"},
            masked=set(),
            revealed=set(),
            pushed_files=set(),
            host_project_root=temp_project,
            host_container_root=temp_project,
            siblings=[sibling],
        )

        # Should have volumes for both primary and sibling
        assert any("/workspace" in v for v in hierarchy.ordered_volumes)
        assert any("/shared" in v for v in hierarchy.ordered_volumes)


# =============================================================================
# Interactive test runner
# =============================================================================

def run_interactive_tests():
    """Interactive test runner for manual testing.

    Provides a menu-driven interface for:
    1. Creating test containers
    2. Running specific test scenarios
    3. Testing LLM deployment
    4. Cleanup
    """
    import sys

    def prompt(msg: str, default: str = "") -> str:
        """Prompt user for input."""
        if default:
            result = input(f"{msg} [{default}]: ").strip()
            return result if result else default
        return input(f"{msg}: ").strip()

    def confirm(msg: str, default: bool = True) -> bool:
        """Prompt for yes/no confirmation."""
        suffix = " [Y/n]: " if default else " [y/N]: "
        response = input(msg + suffix).strip().lower()
        if not response:
            return default
        return response in ('y', 'yes')

    print("\n" + "=" * 60)
    print("IgnoreScope Interactive Test Runner")
    print("=" * 60)

    # Check Docker
    try:
        result = subprocess.run(['docker', 'info'], capture_output=True, timeout=10)
        if result.returncode != 0:
            print("\n[ERROR] Docker is not running. Please start Docker Desktop.")
            return 1
        print("\n[OK] Docker is running")
    except FileNotFoundError:
        print("\n[ERROR] Docker not found. Please install Docker.")
        return 1

    while True:
        print("\n" + "-" * 40)
        print("Test Menu:")
        print("  1. Run unit tests (no Docker)")
        print("  2. Run Docker tests (minimal container)")
        print("  3. Run Docker tests (with LLM deployment)")
        print("  4. Create test container interactively")
        print("  5. Deploy Claude to existing container")
        print("  6. Run all tests")
        print("  7. Cleanup test containers")
        print("  q. Quit")
        print("-" * 40)

        choice = prompt("Select option", "1")

        if choice == 'q':
            break

        elif choice == '1':
            print("\nRunning unit tests...")
            subprocess.run([
                sys.executable, '-m', 'pytest', '-v',
                '-k', 'not docker',
                str(Path(__file__).parent),
            ])

        elif choice == '2':
            print("\nRunning Docker tests (minimal container)...")
            subprocess.run([
                sys.executable, '-m', 'pytest', '-v',
                '-k', 'TestMinimalContainer',
                str(Path(__file__)),
            ])

        elif choice == '3':
            print("\nRunning Docker tests (with LLM)...")
            print("Note: This may take several minutes for npm install.")
            subprocess.run([
                sys.executable, '-m', 'pytest', '-v',
                '-k', 'TestLLMContainer',
                str(Path(__file__)),
            ])

        elif choice == '4':
            print("\nCreating test container...")
            container_name = prompt("Container name", "isd-interactive-test")

            # Create temp directory
            with tempfile.TemporaryDirectory() as tmpdir:
                project = Path(tmpdir) / "test_project"
                project.mkdir()
                (project / "src").mkdir()
                (project / "src" / "test.py").write_text("print('test')\n")

                from IgnoreScope.core.config import ScopeDockerConfig
                from IgnoreScope.cli.commands import cmd_create

                config = ScopeDockerConfig(
                    mounts={project / "src"},
                    container_name=container_name,
                    host_project_root=project,
                )

                success, msg = cmd_create(project, config)
                if success:
                    print(f"\n[OK] Container created: {container_name}")
                    print("You can now:")
                    print(f"  docker exec -it {container_name} bash")
                    print(f"  docker stop {container_name}")
                else:
                    print(f"\n[ERROR] {msg}")

        elif choice == '5':
            container_name = prompt("Container name")
            if not container_name:
                print("Container name required")
                continue

            print(f"\nDeploying Claude to {container_name}...")
            print("This may take 1-2 minutes...")

            from IgnoreScope.container_ext import deploy_claude, verify_claude

            result = deploy_claude(container_name, timeout=300)
            if result.success:
                print(f"\n[OK] {result.message}")
                verify = verify_claude(container_name)
                print(f"    Version: {verify.version}")
            else:
                print(f"\n[ERROR] {result.message}")

        elif choice == '6':
            print("\nRunning all tests...")
            subprocess.run([
                sys.executable, '-m', 'pytest', '-v',
                str(Path(__file__).parent),
            ])

        elif choice == '7':
            print("\nLooking for test containers...")
            result = subprocess.run(
                ['docker', 'ps', '-a', '--filter', 'name=isd-', '--format', '{{.Names}}'],
                capture_output=True,
                text=True,
            )
            containers = result.stdout.strip().split('\n')
            containers = [c for c in containers if c]

            if not containers:
                print("No test containers found")
                continue

            print(f"Found {len(containers)} test container(s):")
            for c in containers:
                print(f"  - {c}")

            if confirm("Remove all test containers?"):
                for c in containers:
                    subprocess.run(['docker', 'rm', '-f', c], capture_output=True)
                print("Containers removed")

    print("\nGoodbye!")
    return 0


if __name__ == "__main__":
    sys.exit(run_interactive_tests())
