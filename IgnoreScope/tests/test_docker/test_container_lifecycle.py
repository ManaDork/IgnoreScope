"""Tests for docker container lifecycle orchestrators (container_lifecycle.py).

Verifies:
  - preflight_update: container must exist
  - execute_update: orphan detection, compose down without volumes, non-fatal prune
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from IgnoreScope.core.op_result import OpError, OpResult


# =============================================================================
# Helpers
# =============================================================================

def _make_config(scope_name: str = "test-container", tmp_path: Path | None = None):
    """Create a minimal ScopeDockerConfig for testing."""
    from IgnoreScope.core.config import ScopeDockerConfig

    root = tmp_path or Path("/fake/project")
    return ScopeDockerConfig(
        scope_name=scope_name,
        host_project_root=root,
        host_container_root=root.parent,
        container_root="/workspace",
    )


def _make_hierarchy(
    mask_volume_names: list[str],
    isolation_volume_names: list[str] | None = None,
    isolation_volume_entries: list[str] | None = None,
):
    """Create a minimal ContainerHierarchy mock with specified volume names."""
    from IgnoreScope.core.hierarchy import ContainerHierarchy

    h = ContainerHierarchy()
    h.mask_volume_names = list(mask_volume_names)
    h.isolation_volume_names = list(isolation_volume_names or [])
    h.isolation_volume_entries = list(isolation_volume_entries or [])
    h.ordered_volumes = []
    h.revealed_parents = set()
    h.validation_errors = []
    return h


# =============================================================================
# preflight_update
# =============================================================================

class TestPreflightUpdate:
    """Tests for container_lifecycle.preflight_update."""

    def test_no_container_returns_not_found(self, tmp_path):
        """Returns CONTAINER_NOT_FOUND when container doesn't exist."""
        from IgnoreScope.docker.container_lifecycle import preflight_update

        config = _make_config(tmp_path=tmp_path)

        with patch(
            "IgnoreScope.docker.container_lifecycle.container_exists",
            return_value=False,
        ):
            result = preflight_update(tmp_path, config)

        assert result.success is False
        assert result.error == OpError.CONTAINER_NOT_FOUND
        assert "Use Create instead" in result.message


# =============================================================================
# execute_update
# =============================================================================

class TestExecuteUpdate:
    """Tests for container_lifecycle.execute_update."""

    def _patch_all(
        self, old_masks, new_masks,
        old_iso=None, new_iso=None,
        compose_down_ok=True, prune_ok=True,
    ):
        """Return a dict of patches for execute_update testing."""
        old_config = _make_config()
        old_hierarchy = _make_hierarchy(old_masks, old_iso)
        # preflight_create also calls compute_hierarchy for validation
        preflight_hierarchy = _make_hierarchy(new_masks, new_iso)
        new_hierarchy = _make_hierarchy(new_masks, new_iso)

        patches = {
            "load_config": patch(
                "IgnoreScope.docker.container_lifecycle.load_config",
                return_value=old_config,
            ),
            "compute_hierarchy": patch(
                "IgnoreScope.core.hierarchy.compute_container_hierarchy",
                side_effect=[old_hierarchy, preflight_hierarchy, new_hierarchy],
            ),
            "container_exists": patch(
                "IgnoreScope.docker.container_lifecycle.container_exists",
                return_value=True,
            ),
            "is_docker_running": patch(
                "IgnoreScope.docker.container_lifecycle.is_docker_running",
                return_value=(True, "ok"),
            ),
            "remove_container_compose": patch(
                "IgnoreScope.docker.container_lifecycle.remove_container_compose",
                return_value=(compose_down_ok, "ok" if compose_down_ok else "compose down failed", []),
            ),
            "generate_compose": patch(
                "IgnoreScope.docker.container_lifecycle.generate_compose_with_masks",
                return_value="version: '3'\nservices:\n  claude:\n    image: test\n",
            ),
            "generate_dockerfile": patch(
                "IgnoreScope.docker.container_lifecycle.generate_dockerfile",
                return_value="FROM ubuntu:22.04\n",
            ),
            "build_image": patch(
                "IgnoreScope.docker.container_lifecycle.build_image",
                return_value=(True, "built"),
            ),
            "create_container_compose": patch(
                "IgnoreScope.docker.container_lifecycle.create_container_compose",
                return_value=(True, "created", "test-container"),
            ),
            "volume_exists": patch(
                "IgnoreScope.docker.container_lifecycle.volume_exists",
                return_value=True,
            ),
            "remove_volume": patch(
                "IgnoreScope.docker.container_lifecycle.remove_volume",
                return_value=(prune_ok, "removed" if prune_ok else "in use"),
            ),
            "ensure_container_running": patch(
                "IgnoreScope.docker.container_lifecycle.ensure_container_running",
                return_value=(True, "running"),
            ),
            "ensure_container_directories": patch(
                "IgnoreScope.docker.container_lifecycle.ensure_container_directories",
                return_value=(True, "dirs ok"),
            ),
            "save_config": patch(
                "IgnoreScope.docker.container_lifecycle.save_config",
            ),
            "get_container_dir": patch(
                "IgnoreScope.docker.container_lifecycle.get_container_dir",
            ),
        }
        return patches

    def _run_update(self, patches, tmp_path):
        """Enter all patches and run execute_update."""
        from IgnoreScope.docker.container_lifecycle import execute_update

        config = _make_config(tmp_path=tmp_path)

        # get_container_dir needs to return a real writable directory
        patches["get_container_dir"].start().return_value = tmp_path / ".isd" / "test"
        (tmp_path / ".isd" / "test").mkdir(parents=True, exist_ok=True)

        mocks = {}
        for name, p in patches.items():
            if name != "get_container_dir":  # already started
                mocks[name] = p.start()

        try:
            result = execute_update(tmp_path, config)
        finally:
            for p in patches.values():
                p.stop()

        return result, mocks

    def test_orphan_detection(self, tmp_path):
        """Old masks {A,B,C}, new masks {A,C,D} → orphans = {B}."""
        patches = self._patch_all(
            old_masks=["A", "B", "C"],
            new_masks=["A", "C", "D"],
        )
        result, mocks = self._run_update(patches, tmp_path)

        assert result.success is True
        # remove_volume should have been called for orphan "B"
        mocks["remove_volume"].assert_called_once_with("B")

    def test_compose_down_no_volumes(self, tmp_path):
        """Verify remove_container_compose called with remove_volumes=False."""
        patches = self._patch_all(old_masks=["A"], new_masks=["A"])
        result, mocks = self._run_update(patches, tmp_path)

        assert result.success is True
        call_kwargs = mocks["remove_container_compose"].call_args
        assert call_kwargs[1]["remove_volumes"] is False
        assert call_kwargs[1]["remove_images"] is False

    def test_compose_down_failure(self, tmp_path):
        """Compose down fails → returns failure immediately."""
        patches = self._patch_all(
            old_masks=["A"], new_masks=["A"], compose_down_ok=False,
        )
        result, mocks = self._run_update(patches, tmp_path)

        assert result.success is False
        assert "stop container" in result.message.lower() or "compose down" in result.message.lower()

    def test_prune_non_fatal(self, tmp_path):
        """remove_volume fails → overall success=True, details populated."""
        patches = self._patch_all(
            old_masks=["A", "B"],
            new_masks=["A"],
            prune_ok=False,
        )
        result, mocks = self._run_update(patches, tmp_path)

        assert result.success is True
        assert any("Failed to prune" in d for d in result.details)

    def test_orphan_detection_isolation_volumes(self, tmp_path):
        """Old iso {X,Y}, new iso {Y,Z} → orphan X pruned."""
        patches = self._patch_all(
            old_masks=["A"], new_masks=["A"],
            old_iso=["X", "Y"], new_iso=["Y", "Z"],
        )
        result, mocks = self._run_update(patches, tmp_path)

        assert result.success is True
        mocks["remove_volume"].assert_called_once_with("X")

    def test_orphan_detection_mixed_masks_and_isolation(self, tmp_path):
        """Orphans from both mask and isolation are pruned."""
        patches = self._patch_all(
            old_masks=["A", "B"], new_masks=["A"],
            old_iso=["X", "Y"], new_iso=["X"],
        )
        result, mocks = self._run_update(patches, tmp_path)

        assert result.success is True
        # Both orphan mask "B" and orphan iso "Y" should be pruned
        pruned = {call.args[0] for call in mocks["remove_volume"].call_args_list}
        assert pruned == {"B", "Y"}


# =============================================================================
# Compose: isolation volume declaration
# =============================================================================

class TestComposeIsolationVolumes:
    """Verify generate_compose_with_masks declares isolation volumes."""

    def test_isolation_volumes_in_volumes_section(self, tmp_path: Path):
        """isolation_volume_names → declared in top-level volumes section."""
        from IgnoreScope.docker.compose import generate_compose_with_masks

        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-container",
            isolation_volume_entries=["iso_claude_root_local:/root/.local"],
            isolation_volume_names=["iso_claude_root_local"],
        )

        # Volume appears in services.volumes (from isolation_volume_entries)
        assert "iso_claude_root_local:/root/.local" in compose
        # Volume declared in top-level volumes section
        lines = compose.split("\n")
        volumes_section_idx = next(i for i, l in enumerate(lines) if l.startswith("volumes:"))
        volumes_section = "\n".join(lines[volumes_section_idx:])
        assert "  iso_claude_root_local:" in volumes_section

    def test_no_isolation_volumes_no_change(self, tmp_path: Path):
        """No isolation_volume_names → output unchanged from before."""
        from IgnoreScope.docker.compose import generate_compose_with_masks

        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-container",
            isolation_volume_names=[],
        )

        assert "iso_" not in compose

    def test_both_mask_and_isolation_declared(self, tmp_path: Path):
        """Both mask and isolation volumes appear in volumes section."""
        from IgnoreScope.docker.compose import generate_compose_with_masks

        compose = generate_compose_with_masks(
            ordered_volumes=["mask_src_api:/workspace/src/api"],
            mask_volume_names=["mask_src_api"],
            host_project_root=tmp_path,
            docker_container_name="test-container",
            isolation_volume_entries=["iso_claude_root_local:/root/.local"],
            isolation_volume_names=["iso_claude_root_local"],
        )

        lines = compose.split("\n")
        volumes_section_idx = next(i for i, l in enumerate(lines) if l.startswith("volumes:"))
        volumes_section = "\n".join(lines[volumes_section_idx:])
        assert "  mask_src_api:" in volumes_section
        assert "  iso_claude_root_local:" in volumes_section


# =============================================================================
# _collect_isolation_paths
# =============================================================================

class TestCollectIsolationPaths:
    """Verify _collect_isolation_paths extracts extension data correctly."""

    def test_extensions_with_isolation_paths(self):
        """Extensions with isolation_paths → list of (name, path) tuples."""
        from IgnoreScope.docker.container_lifecycle import _collect_isolation_paths
        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.core.local_mount_config import ExtensionConfig

        config = ScopeDockerConfig(
            scope_name="test",
            extensions=[
                ExtensionConfig(
                    name="Claude Code",
                    installer_class="ClaudeInstaller",
                    isolation_paths=["/root/.local"],
                ),
                ExtensionConfig(
                    name="P4 MCP Server",
                    installer_class="P4McpInstaller",
                    isolation_paths=["/usr/local/lib/p4-mcp-server"],
                ),
            ],
        )

        result = _collect_isolation_paths(config)

        assert result == [
            ("Claude Code", "/root/.local"),
            ("P4 MCP Server", "/usr/local/lib/p4-mcp-server"),
        ]

    def test_no_extensions_returns_none(self):
        """Empty extensions list → None."""
        from IgnoreScope.docker.container_lifecycle import _collect_isolation_paths
        from IgnoreScope.core.config import ScopeDockerConfig

        config = ScopeDockerConfig(scope_name="test")

        assert _collect_isolation_paths(config) is None

    def test_extensions_with_empty_isolation_paths(self):
        """Extensions exist but all have empty isolation_paths → None."""
        from IgnoreScope.docker.container_lifecycle import _collect_isolation_paths
        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.core.local_mount_config import ExtensionConfig

        config = ScopeDockerConfig(
            scope_name="test",
            extensions=[
                ExtensionConfig(
                    name="Git",
                    installer_class="GitInstaller",
                    isolation_paths=[],
                ),
            ],
        )

        assert _collect_isolation_paths(config) is None

    def test_mixed_extensions(self):
        """Mix of extensions with and without isolation_paths."""
        from IgnoreScope.docker.container_lifecycle import _collect_isolation_paths
        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.core.local_mount_config import ExtensionConfig

        config = ScopeDockerConfig(
            scope_name="test",
            extensions=[
                ExtensionConfig(
                    name="Git",
                    installer_class="GitInstaller",
                    isolation_paths=[],
                ),
                ExtensionConfig(
                    name="Claude Code",
                    installer_class="ClaudeInstaller",
                    isolation_paths=["/root/.local"],
                ),
            ],
        )

        result = _collect_isolation_paths(config)
        assert result == [("Claude Code", "/root/.local")]


# =============================================================================
# reconcile_extensions — state matrix
# =============================================================================

class TestReconcileExtensions:
    """Verify reconcile_extensions state × presence matrix."""

    def _make_ext_config(self, name="Claude Code", installer_class="ClaudeInstaller",
                         state="installed", isolation_paths=None):
        """Create a ScopeDockerConfig with one extension."""
        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.core.local_mount_config import ExtensionConfig

        return ScopeDockerConfig(
            scope_name="test",
            extensions=[
                ExtensionConfig(
                    name=name,
                    installer_class=installer_class,
                    isolation_paths=isolation_paths or ["/root/.local"],
                    state=state,
                ),
            ],
        )

    def _mock_installer(self, verify_success=True, deploy_success=True):
        """Create a mock installer with configurable verify/deploy results."""
        from IgnoreScope.container_ext import DeployResult

        installer = MagicMock()
        installer.verify.return_value = DeployResult(
            success=verify_success, message="ok" if verify_success else "not found",
            version="1.0.0" if verify_success else "",
        )
        installer.deploy_runtime.return_value = DeployResult(
            success=deploy_success, message="deployed" if deploy_success else "failed",
            version="1.0.0" if deploy_success else "",
        )
        return installer

    def test_installed_present_noop(self):
        """state='installed' + binary present → no-op."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="installed")
        installer = self._mock_installer(verify_success=True)

        with patch("IgnoreScope.container_ext.get_installer", return_value=installer), \
             patch("IgnoreScope.docker.container_lifecycle.save_config"):
            result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert any("no action" in d for d in result.details)
        installer.deploy_runtime.assert_not_called()
        assert config.extensions[0].state == "installed"

    def test_installed_missing_redeploy(self):
        """state='installed' + binary missing → re-deploy (recreate recovery)."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="installed")
        installer = self._mock_installer(verify_success=False, deploy_success=True)

        with patch("IgnoreScope.container_ext.get_installer", return_value=installer):
            result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert any("re-deploy" in d for d in result.details)
        installer.deploy_runtime.assert_called_once()
        assert config.extensions[0].state == "installed"

    def test_deploy_missing_install(self):
        """state='deploy' + binary missing → deploy_runtime() → installed."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="deploy")
        installer = self._mock_installer(verify_success=False, deploy_success=True)

        with patch("IgnoreScope.container_ext.get_installer", return_value=installer):
            result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert any("deploy succeeded" in d for d in result.details)
        installer.deploy_runtime.assert_called_once()
        assert config.extensions[0].state == "installed"

    def test_deploy_present_mark_installed(self):
        """state='deploy' + binary present → state becomes 'installed'."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="deploy")
        installer = self._mock_installer(verify_success=True)

        with patch("IgnoreScope.container_ext.get_installer", return_value=installer):
            result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert any("installed" in d for d in result.details)
        installer.deploy_runtime.assert_not_called()
        assert config.extensions[0].state == "installed"

    def test_remove_present_noop(self):
        """state='remove' + any → skipped (deferred to Phase 5)."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="remove")
        result = reconcile_extensions("test-container", config)

        assert result.success is True
        # No details for skipped entries
        assert len(result.details) == 0

    def test_empty_state_noop(self):
        """state='' → skipped (not extension-managed)."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="")
        result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert len(result.details) == 0

    def test_no_extensions(self):
        """No extensions → success with no work."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions
        from IgnoreScope.core.config import ScopeDockerConfig

        config = ScopeDockerConfig(scope_name="test")
        result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert "No extensions" in result.message

    def test_deploy_failure_nonfatal(self):
        """Deploy fails for one extension → overall success, error in details."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="installed")
        installer = self._mock_installer(verify_success=False, deploy_success=False)

        with patch("IgnoreScope.container_ext.get_installer", return_value=installer):
            result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert any("failed" in d for d in result.details)

    def test_unknown_installer_skipped(self):
        """Unknown installer_class → skipped with message."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(installer_class="FakeInstaller")

        with patch("IgnoreScope.container_ext.get_installer", return_value=None):
            result = reconcile_extensions("test-container", config)

        assert result.success is True
        assert any("unknown installer" in d for d in result.details)

    def test_state_mutated_in_place(self):
        """State transitions mutate config in-place (caller saves)."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="deploy")
        installer = self._mock_installer(verify_success=True)

        with patch("IgnoreScope.container_ext.get_installer", return_value=installer):
            reconcile_extensions("test-container", config)

        # Config mutated in-place — caller is responsible for save
        assert config.extensions[0].state == "installed"

    def test_no_save_called_internally(self):
        """reconcile_extensions does NOT call save_config (caller saves)."""
        from IgnoreScope.docker.container_lifecycle import reconcile_extensions

        config = self._make_ext_config(state="deploy")
        installer = self._mock_installer(verify_success=True)

        with patch("IgnoreScope.container_ext.get_installer", return_value=installer), \
             patch("IgnoreScope.docker.container_lifecycle.save_config") as mock_save:
            reconcile_extensions("test-container", config)

        mock_save.assert_not_called()


# =============================================================================
# pushed_files replay — mode-agnostic
# =============================================================================


class TestPushedFilesReplay:
    """pushed_files replay runs on every create/update when non-empty.

    Delivery-agnostic: bind-only, detached-only, and mixed scopes all replay.
    """

    def _patches_for_create(self, tmp_path: Path):
        """Patches sufficient for execute_create to reach the replay block."""
        from IgnoreScope.core.hierarchy import ContainerHierarchy

        h = ContainerHierarchy()
        h.mask_volume_names = []
        h.isolation_volume_names = []
        h.isolation_volume_entries = []
        h.ordered_volumes = []
        h.revealed_parents = set()
        h.validation_errors = []

        return {
            "compute_hierarchy": patch(
                "IgnoreScope.core.hierarchy.compute_container_hierarchy",
                return_value=h,
            ),
            "is_docker_running": patch(
                "IgnoreScope.docker.container_lifecycle.is_docker_running",
                return_value=(True, "ok"),
            ),
            "generate_compose": patch(
                "IgnoreScope.docker.container_lifecycle.generate_compose_with_masks",
                return_value="version: '3'\nservices: {}\n",
            ),
            "generate_dockerfile": patch(
                "IgnoreScope.docker.container_lifecycle.generate_dockerfile",
                return_value="FROM ubuntu:22.04\n",
            ),
            "build_image": patch(
                "IgnoreScope.docker.container_lifecycle.build_image",
                return_value=(True, "built"),
            ),
            "create_container_compose": patch(
                "IgnoreScope.docker.container_lifecycle.create_container_compose",
                return_value=(True, "created", "test-container"),
            ),
            "ensure_container_running": patch(
                "IgnoreScope.docker.container_lifecycle.ensure_container_running",
                return_value=(True, "running"),
            ),
            "ensure_container_directories": patch(
                "IgnoreScope.docker.container_lifecycle.ensure_container_directories",
                return_value=(True, "dirs ok"),
            ),
            "save_config": patch(
                "IgnoreScope.docker.container_lifecycle.save_config",
            ),
        }

    def _run_create(self, patches, tmp_path, config):
        from IgnoreScope.docker.container_lifecycle import execute_create

        mocks = {}
        for name, p in patches.items():
            mocks[name] = p.start()
        try:
            result = execute_create(tmp_path, config)
        finally:
            for p in patches.values():
                p.stop()
        return result, mocks

    def test_empty_pushed_files_no_batch_call(self, tmp_path: Path):
        """No pushed_files → execute_push_batch not called."""
        config = _make_config(tmp_path=tmp_path)
        config.pushed_files = set()

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle.execute_push_batch",
        ) as mock_batch:
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        mock_batch.assert_not_called()

    def test_bind_delivery_replay_runs(self, tmp_path: Path):
        """All-bind scope with pushed_files → replay runs (mode-agnostic)."""
        from IgnoreScope.core.mount_spec_path import MountSpecPath

        src = tmp_path / "src"
        src.mkdir()
        pushed = tmp_path / "src" / "config.json"
        pushed.parent.mkdir(parents=True, exist_ok=True)
        pushed.write_text("{}")

        config = _make_config(tmp_path=tmp_path)
        config.mount_specs = [MountSpecPath(mount_root=src, patterns=[], delivery="bind")]
        config.pushed_files = {pushed}

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle.execute_push_batch",
            return_value={pushed: OpResult(success=True, message="pushed")},
        ) as mock_batch:
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        mock_batch.assert_called_once()

    def test_detached_delivery_replay_runs(self, tmp_path: Path):
        """Detached scope with pushed_files → replay runs after detached_init."""
        from IgnoreScope.core.mount_spec_path import MountSpecPath

        src = tmp_path / "src"
        src.mkdir()
        pushed = tmp_path / "src" / "secret.env"
        pushed.parent.mkdir(parents=True, exist_ok=True)
        pushed.write_text("X=1")

        config = _make_config(tmp_path=tmp_path)
        config.mount_specs = [
            MountSpecPath(mount_root=src, patterns=[], delivery="detached"),
        ]
        config.pushed_files = {pushed}

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle._detached_init",
            return_value=OpResult(success=True, message="ok", details=[]),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.execute_push_batch",
            return_value={pushed: OpResult(success=True, message="pushed")},
        ) as mock_batch:
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        mock_batch.assert_called_once()

    def test_replay_failure_in_details(self, tmp_path: Path):
        """Per-file replay failure → aggregated into details, not fatal."""
        src = tmp_path / "src"
        src.mkdir()
        pushed = tmp_path / "src" / "missing.txt"

        config = _make_config(tmp_path=tmp_path)
        config.pushed_files = {pushed}

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle.execute_push_batch",
            return_value={pushed: OpResult(success=False, message="not found")},
        ):
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        assert any("pushed_files replay failed" in d for d in result.details)
