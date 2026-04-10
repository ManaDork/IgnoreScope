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

import json
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

from IgnoreScope.core.mount_spec_path import MountSpecPath


def _make_mount_specs(mounts=None, masked=None, revealed=None):
    """Convert old-style flat sets to mount_specs list (test compat helper)."""
    specs = []
    for mount_root in sorted(mounts or set()):
        patterns = []
        for m in sorted(masked or set()):
            try:
                rel = str(m.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"{rel}/")
            except ValueError:
                pass
        for r in sorted(revealed or set()):
            try:
                rel = str(r.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"!{rel}/")
            except ValueError:
                pass
        specs.append(MountSpecPath(mount_root=mount_root, patterns=patterns))
    return specs


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
            mount_specs=_make_mount_specs(
                {temp_project / "src"},
                {temp_project / "src" / "api"},
                {temp_project / "src" / "api" / "public"},
            ),
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
            mount_specs=_make_mount_specs(
                {temp_project / "src"},
                {temp_project / "src" / "api"},
                {temp_project / "src" / "api" / "public"},
            ),
            scope_name=test_container_name,
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

    def test_claude_deployer_basic_dockerfile(self, temp_project: Path):
        """Test basic Dockerfile generation (non-LLM path)."""
        from IgnoreScope.docker.compose import generate_dockerfile

        dockerfile = generate_dockerfile()

        assert "FROM" in dockerfile
        assert "CMD" in dockerfile

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
        from IgnoreScope.container_ext import ClaudeInstaller, DeployMethod

        config = ScopeDockerConfig(
            mount_specs=_make_mount_specs({temp_project / "src"}),
            scope_name=test_container_name,
            host_project_root=temp_project,
        )

        try:
            # Create minimal container
            success, msg = cmd_create(temp_project, config)
            assert success, f"Create failed: {msg}"

            # Deploy Claude
            installer = ClaudeInstaller()
            result = installer.deploy_runtime(
                test_container_name, method=DeployMethod.FULL, timeout=300
            )

            if result.success:
                # Verify installation
                verify_result = installer.verify(test_container_name)
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
            mount_specs=_make_mount_specs(
                {temp_project / "config"},
                {temp_project / "config"},
            ),
            pushed_files={temp_project / "config" / "settings.json"},
            scope_name=test_container_name,
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
            mount_specs=_make_mount_specs(
                {temp_project / "src"},
                {temp_project / "src"},
                {temp_project / "src" / "api" / "public"},
            ),
            scope_name=test_container_name,
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
# Container security probe (mandatory pre-release)
# =============================================================================

class TestContainerProbe:
    """Full container security probe — mandatory before release.

    Builds a container via IgnoreScope framework, deploys container_probe.py,
    executes all 8 probe sections inside the container, and asserts on
    security-critical results.

    Run with: pytest -v -m docker IgnoreScope/tests/test_docker/test_integration.py -k TestContainerProbe
    """

    # -----------------------------------------------------------------
    # Expected volume mask check results (matrix coverage)
    #
    #   Pattern            | Host Content          | Expected Inside Container
    #   -------------------|-----------------------|---------------------------
    #   api/       (mask)  | files at depth        | empty/submount (masked)
    #   build/     (mask)  | files deeply nested   | empty/submount (masked)
    #   vendor/    (mask)  | files, no reveal      | empty/submount (masked)
    #   !api/public/       | client.py             | visible (revealed)
    #   !build/out/release | release.bin           | visible (revealed)
    # -----------------------------------------------------------------
    EXPECTED_MASKED = {"src/api", "src/build", "src/vendor"}
    EXPECTED_REVEALED = {"src/api/public", "src/build/out/release"}

    @pytest.fixture(scope="class")
    def probe_project(self, tmp_path_factory) -> Path:
        """Class-scoped temp project covering the full mask/reveal matrix.

        Structure:
            src/
                main.py                              (visible — not masked)
                api/                                 (MASK 1: shallow, has children)
                    internal/
                        secret.py
                    public/                          (REVEAL 1: inside shallow mask)
                        client.py
                build/                               (MASK 2: deep nesting)
                    artifacts/
                        cache/
                            build.log
                            out/
                                release/             (REVEAL 2: deep inside deep mask)
                                    release.bin
                vendor/                              (MASK 3: pure mask, no reveal)
                    third_party/
                        license.txt
        """
        project = tmp_path_factory.mktemp("probe_project")

        src = project / "src"
        src.mkdir()
        (src / "main.py").write_text("print('hello')\n")

        # --- Mask 1: api/ (shallow) with reveal at api/public/ ---
        api = src / "api"
        api.mkdir()
        internal = api / "internal"
        internal.mkdir()
        (internal / "secret.py").write_text("API_KEY = 'xxx'\n")
        public = api / "public"
        public.mkdir()
        (public / "client.py").write_text("def fetch(): pass\n")

        # --- Mask 2: build/ (deep nesting) with reveal at build/out/release/ ---
        build = src / "build"
        build.mkdir()
        cache = build / "artifacts" / "cache"
        cache.mkdir(parents=True)
        (cache / "build.log").write_text("compile output\n")
        release = build / "out" / "release"
        release.mkdir(parents=True)
        (release / "release.bin").write_bytes(b"\x00" * 64)

        # --- Mask 3: vendor/ (pure mask, no reveal) ---
        vendor = src / "vendor"
        vendor.mkdir()
        tp = vendor / "third_party"
        tp.mkdir()
        (tp / "license.txt").write_text("MIT\n")

        return project

    @pytest.fixture(scope="class")
    def probe_container_name(self) -> str:
        """Class-scoped unique container name."""
        import uuid
        return f"isd-probe-{uuid.uuid4().hex[:8]}"

    @pytest.fixture(scope="class")
    def probe_report(self, docker_available, probe_project, probe_container_name):
        """Build container, deploy and run probe, return parsed JSON report.

        Creates an IgnoreScope container with the full mask/reveal matrix:
          - src/ mounted
          - src/api/ masked, src/api/public/ revealed
          - src/build/ masked, src/build/out/release/ revealed (deep nesting)
          - src/vendor/ masked (pure mask, no reveal)

        Then copies container_probe.py in and executes it.
        """
        if not docker_available:
            pytest.skip("Docker not available")

        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.cli.commands import cmd_create, cmd_remove
        from IgnoreScope.docker.names import build_docker_name

        # Full matrix: 3 masks, 2 reveals covering shallow, deep, and pure-mask
        probe_specs = [MountSpecPath(
            mount_root=probe_project / "src",
            patterns=[
                "api/",                   # Mask 1: shallow
                "!api/public/",           # Reveal 1: inside shallow mask
                "build/",                 # Mask 2: deep nesting
                "!build/out/release/",    # Reveal 2: deep inside deep mask
                "vendor/",                # Mask 3: pure mask, no reveal
            ],
        )]

        config = ScopeDockerConfig(
            mount_specs=probe_specs,
            scope_name=probe_container_name,
            host_project_root=probe_project,
        )

        # Docker container name is {project}__{scope}, not scope_name alone
        docker_name = build_docker_name(probe_project, probe_container_name)
        # Container workdir = container_root/project_name (mirrors generate_dockerfile)
        container_workdir = f"{config.container_root}/{probe_project.name}"

        try:
            # Phase 1: Create container
            success, msg = cmd_create(probe_project, config)
            assert success, f"Container create failed: {msg}"

            # Phase 2: Start container
            start = subprocess.run(
                ['docker', 'start', docker_name],
                capture_output=True, text=True,
            )
            assert start.returncode == 0, f"Container start failed: {start.stderr}"

            # Phase 3: Deploy scope config into container for volume mask probe
            scope_dir = probe_project / ".ignore_scope"
            if scope_dir.exists():
                subprocess.run(
                    ['docker', 'cp',
                     str(scope_dir),
                     f'{docker_name}:{container_workdir}/.ignore_scope'],
                    capture_output=True, text=True, check=True,
                )

            # Phase 4: Deploy probe script
            probe_script = str(
                Path(__file__).resolve().parents[3] / "scripts" / "container_probe.py"
            )
            cp = subprocess.run(
                ['docker', 'cp', probe_script,
                 f'{docker_name}:/tmp/container_probe.py'],
                capture_output=True, text=True,
            )
            assert cp.returncode == 0, f"docker cp probe failed: {cp.stderr}"

            # Phase 5: Execute probe inside container (cwd = workdir for volume mask discovery)
            exec_result = subprocess.run(
                ['docker', 'exec', '-w', container_workdir,
                 docker_name,
                 'python3', '/tmp/container_probe.py'],
                capture_output=True, text=True, timeout=60,
            )

            # Phase 6: Parse JSON report from stdout
            stdout = exec_result.stdout
            marker = "=== Report ==="
            idx = stdout.find(marker)
            assert idx != -1, (
                f"Probe output missing report marker.\n"
                f"stdout: {stdout[:500]}\nstderr: {exec_result.stderr[:500]}"
            )

            json_str = stdout[idx + len(marker):]
            decoder = json.JSONDecoder()
            report, _ = decoder.raw_decode(json_str.strip())

            yield report

        finally:
            cmd_remove(
                probe_project, probe_container_name,
                confirm=True, remove_images=True,
            )

    # -----------------------------------------------------------------
    # Security assertions — each probe section gets its own test
    # -----------------------------------------------------------------

    def test_confirms_container_identity(self, probe_report):
        """Probe must confirm it is running inside a container."""
        identity = probe_report["identity"]
        assert identity["is_container"] is True, "Probe did not detect container environment"

    def test_mount_escape_vectors_blocked(self, probe_report):
        """All mount escape vectors must be blocked or errored."""
        escape = probe_report["mount_escape"]

        # mount(2) syscall — must be denied
        if "mount_syscall" in escape:
            assert escape["mount_syscall"].get("blocked", True), \
                "mount(2) syscall should be blocked"

        # unshare mount namespace — must be denied
        if "unshare_mount_ns" in escape:
            assert escape["unshare_mount_ns"].get("blocked", True), \
                "unshare -m should be blocked"

        # hardlink across device boundary — must fail
        if "hardlink_escape" in escape:
            assert escape["hardlink_escape"].get("blocked", True), \
                "Cross-device hardlink should be blocked"

    def test_docker_socket_not_accessible(self, probe_report):
        """Docker socket must not be connectable from inside the container."""
        escape = probe_report["mount_escape"]
        docker_sock = escape.get("docker_socket", {})
        # Socket either doesn't exist or isn't connectable
        if docker_sock.get("exists"):
            assert docker_sock.get("connectable") is not True, \
                "Docker socket is accessible — container breakout risk"

    def test_critical_capabilities_denied(self, probe_report):
        """Security-critical Linux capabilities must NOT be granted."""
        caps = probe_report["capabilities"]
        granted_names = {e["capability"] for e in caps.get("granted", [])}

        must_deny = [
            "CAP_SYS_ADMIN",    # mount/namespace escape
            "CAP_SYS_PTRACE",   # process attach
            "CAP_SYS_MODULE",   # kernel module loading
            "CAP_SYS_RAWIO",    # raw I/O port access
        ]
        for cap in must_deny:
            assert cap not in granted_names, f"{cap} must be denied"

    def test_proc_masks_enforced(self, probe_report):
        """Docker default /proc masks must be in place."""
        proc = probe_report["proc_masks"]
        masked = proc.get("masked", {})

        valid_mechanisms = {"char_device_null", "empty_tmpfs", "permission_denied"}
        for path, info in masked.items():
            if info.get("exists"):
                mechanism = info.get("mechanism", "")
                assert mechanism in valid_mechanisms, \
                    f"{path} not properly masked (mechanism={mechanism})"

    # -----------------------------------------------------------------
    # Volume mask matrix — individual condition tests
    # -----------------------------------------------------------------

    def _get_volume_checks(self, probe_report) -> dict[str, dict]:
        """Helper: extract volume mask checks keyed by path."""
        masks = probe_report["volume_masks"]
        if "error" in masks:
            pytest.fail(f"Volume mask probe error: {masks['error']}")
        return {c["path"]: c for c in masks["checks"]}

    def test_volume_mask_matrix_coverage(self, probe_report):
        """Probe must check every expected masked and revealed path."""
        checks = self._get_volume_checks(probe_report)
        checked_paths = set(checks.keys())

        for path in self.EXPECTED_MASKED:
            assert path in checked_paths, f"Missing masked check for '{path}'"
        for path in self.EXPECTED_REVEALED:
            assert path in checked_paths, f"Missing revealed check for '{path}'"

        expected_total = len(self.EXPECTED_MASKED) + len(self.EXPECTED_REVEALED)
        assert len(checks) == expected_total, (
            f"Expected {expected_total} checks, got {len(checks)}: {list(checks.keys())}"
        )

    def test_masked_shallow_hidden(self, probe_report):
        """Mask 1: api/ (shallow) — content must be hidden by volume overlay."""
        checks = self._get_volume_checks(probe_report)
        check = checks["src/api"]
        assert check["expected"] == "masked"
        assert check["pass"] is True, (
            f"api/ mask leak: actual={check['actual']}, "
            f"file_count={check.get('file_count', 'N/A')}"
        )

    def test_masked_deep_hidden(self, probe_report):
        """Mask 2: build/ (deep nesting) — deeply nested content must be hidden."""
        checks = self._get_volume_checks(probe_report)
        check = checks["src/build"]
        assert check["expected"] == "masked"
        assert check["pass"] is True, (
            f"build/ mask leak: actual={check['actual']}, "
            f"file_count={check.get('file_count', 'N/A')}"
        )

    def test_masked_pure_no_reveal(self, probe_report):
        """Mask 3: vendor/ (pure mask, no reveal) — must be fully hidden."""
        checks = self._get_volume_checks(probe_report)
        check = checks["src/vendor"]
        assert check["expected"] == "masked"
        assert check["pass"] is True, (
            f"vendor/ mask leak: actual={check['actual']}, "
            f"file_count={check.get('file_count', 'N/A')}"
        )

    def test_revealed_shallow_visible(self, probe_report):
        """Reveal 1: api/public/ — punch-through must expose content."""
        checks = self._get_volume_checks(probe_report)
        check = checks["src/api/public"]
        assert check["expected"] == "revealed"
        assert check["pass"] is True, f"api/public/ not visible: actual={check['actual']}"
        assert check.get("entry_count", 0) > 0, "Revealed path has no entries"

    def test_revealed_deep_visible(self, probe_report):
        """Reveal 2: build/out/release/ — deep punch-through must expose content."""
        checks = self._get_volume_checks(probe_report)
        check = checks["src/build/out/release"]
        assert check["expected"] == "revealed"
        assert check["pass"] is True, (
            f"build/out/release/ not visible: actual={check['actual']}"
        )
        assert check.get("entry_count", 0) > 0, "Revealed path has no entries"

    def test_volume_masks_summary(self, probe_report):
        """Overall summary: all checks must pass (no leaks)."""
        masks = probe_report["volume_masks"]
        if "error" in masks:
            pytest.fail(f"Volume mask probe error: {masks['error']}")

        summary = masks["summary"]
        expected_total = len(self.EXPECTED_MASKED) + len(self.EXPECTED_REVEALED)
        assert summary["total"] == expected_total, (
            f"Expected {expected_total} checks, got {summary['total']}"
        )
        assert summary["all_enforced"], (
            f"Volume mask leaks: {summary['failed']}/{summary['total']} failed — "
            f"checks: {masks['checks']}"
        )


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
            mount_specs=_make_mount_specs(
                {temp_project / "src"},
                {temp_project / "src" / "api"},
                {temp_project / "src" / "api" / "public"},
            ),
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
            mount_specs=_make_mount_specs({Path("E:/SharedLibs/common")}),
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({temp_project / "src"}),
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
                    mount_specs=_make_mount_specs({project / "src"}),
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

            from IgnoreScope.container_ext import ClaudeInstaller, DeployMethod

            installer = ClaudeInstaller()
            result = installer.deploy_runtime(
                container_name, method=DeployMethod.FULL, timeout=300
            )
            if result.success:
                print(f"\n[OK] {result.message}")
                verify = installer.verify(container_name)
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
