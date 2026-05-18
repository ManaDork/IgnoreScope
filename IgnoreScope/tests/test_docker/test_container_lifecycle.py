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


def _make_hierarchy(mask_volume_names: list[str]):
    """Create a minimal ContainerHierarchy mock with specified volume names."""
    from IgnoreScope.core.hierarchy import ContainerHierarchy

    h = ContainerHierarchy()
    h.mask_volume_names = list(mask_volume_names)
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
# Extension validation smoke (regression for `_validate_hierarchy` HCR fix)
# =============================================================================

class TestExtensionValidation:
    """Lifecycle smoke test mirroring the GUI 'Update Container' repro shape:
    a project with an installed extension whose synth specs carry container
    paths (host_path=None) must NOT trip the HCR residency check.
    """

    def test_preflight_create_with_extension_synth_specs(self, tmp_path):
        """Bug repro: ExtensionConfig.isolation_paths produce host_path=None
        specs whose mount_root is a container path (e.g. /root/.local).
        preflight_create must pass these through validation without firing
        VALIDATION_FAILED with 'not under host container root'.
        """
        from IgnoreScope.core.config import ScopeDockerConfig
        from IgnoreScope.core.local_mount_config import ExtensionConfig
        from IgnoreScope.docker.container_lifecycle import preflight_create

        host_container_root = tmp_path
        host_project_root = tmp_path / "myproject"
        host_project_root.mkdir()

        config = ScopeDockerConfig(
            scope_name="test-scope",
            host_project_root=host_project_root,
            host_container_root=host_container_root,
            container_root="/workspace",
            extensions=[
                ExtensionConfig(
                    name="Claude Code",
                    installer_class="ClaudeInstaller",
                    isolation_paths=["/root/.local"],
                    state="installed",
                ),
            ],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.is_docker_running",
            return_value=(True, "ok"),
        ):
            result = preflight_create(host_project_root, config)

        # Either success, or a non-validation error. The fix's specific
        # contract is that we do NOT fire VALIDATION_FAILED for the synth
        # spec's container path.
        if not result.success:
            details_str = " ".join(result.details or [])
            assert result.error != OpError.VALIDATION_FAILED or (
                "not under host container root" not in details_str
            ), (
                f"Extension synth spec tripped HCR validation: "
                f"error={result.error}, details={result.details}"
            )


# =============================================================================
# execute_update
# =============================================================================

class TestExecuteUpdate:
    """Tests for container_lifecycle.execute_update."""

    def _patch_all(
        self, old_masks, new_masks,
        compose_down_ok=True, prune_ok=True,
    ):
        """Return a dict of patches for execute_update testing."""
        old_config = _make_config()
        old_hierarchy = _make_hierarchy(old_masks)
        # preflight_create also calls compute_hierarchy for validation
        preflight_hierarchy = _make_hierarchy(new_masks)
        new_hierarchy = _make_hierarchy(new_masks)

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

    def test_leftover_staged_flips_success_to_false(self, tmp_path):
        """A staged entry that the Phase-10a drain doesn't clear → success=False.

        Models an interrupted Update: the preserve flow enqueued a snapshot but
        the drain (mocked here) failed to restore it. The Update completes
        structurally, but the user must run `push-marked` to finish.
        """
        from IgnoreScope.core.marked_staged import (
            StagedEntry,
            add_marked_staged,
            snapshot_path_for,
        )
        from IgnoreScope.core.op_result import OpResult

        patches = self._patch_all(old_masks=["A"], new_masks=["A"])
        # Drain reports success but doesn't dequeue the staged entry — the
        # leftover is what flips Update's verdict.
        patches["drain_marked_push"] = patch(
            "IgnoreScope.docker.container_lifecycle.drain_marked_push",
            return_value=OpResult(success=True, message="drain noop", details=[]),
        )

        # Pre-seed a staged entry (and its on-disk snapshot) so the post-drain
        # `load_marked_staged` call returns it. Scope name must match the
        # config built by `_make_config` (default: "test-container").
        scope = "test-container"
        snap = snapshot_path_for(tmp_path, scope, "/workspace/keep")
        snap.mkdir(parents=True, exist_ok=True)
        (snap / "data.txt").write_text("preserved", encoding="utf-8")
        add_marked_staged(
            tmp_path, scope,
            [StagedEntry(source=snap, target="/workspace/keep", is_dir=True)],
        )

        result, _ = self._run_update(patches, tmp_path)

        assert result.success is False
        assert "preserved folder(s) failed to restore" in result.message
        assert "push-marked" in result.message


# =============================================================================
# Compose: L_volume tier declaration
# =============================================================================

class TestComposeVolumeTier:
    """Verify generate_compose_with_masks declares L_volume tier volumes."""

    def test_volume_names_in_volumes_section(self, tmp_path: Path):
        """volume_names → declared in top-level volumes section."""
        from IgnoreScope.docker.compose import generate_compose_with_masks

        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-container",
            volume_entries=["vol_claude_root_.local:/root/.local"],
            volume_names=["vol_claude_root_.local"],
        )

        # Volume appears in services.volumes (from volume_entries)
        assert "vol_claude_root_.local:/root/.local" in compose
        # Volume declared in top-level volumes section
        lines = compose.split("\n")
        volumes_section_idx = next(i for i, l in enumerate(lines) if l.startswith("volumes:"))
        volumes_section = "\n".join(lines[volumes_section_idx:])
        assert "  vol_claude_root_.local:" in volumes_section

    def test_no_volumes_no_change(self, tmp_path: Path):
        """No volume_names → output has no vol_* entries."""
        from IgnoreScope.docker.compose import generate_compose_with_masks

        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-container",
            volume_names=[],
        )

        assert "vol_" not in compose

    def test_both_mask_and_volume_tier_declared(self, tmp_path: Path):
        """Both mask and L_volume tier volumes appear in volumes section."""
        from IgnoreScope.docker.compose import generate_compose_with_masks

        compose = generate_compose_with_masks(
            ordered_volumes=["mask_src_api:/workspace/src/api"],
            mask_volume_names=["mask_src_api"],
            host_project_root=tmp_path,
            docker_container_name="test-container",
            volume_entries=["vol_claude_root_.local:/root/.local"],
            volume_names=["vol_claude_root_.local"],
        )

        lines = compose.split("\n")
        volumes_section_idx = next(i for i, l in enumerate(lines) if l.startswith("volumes:"))
        volumes_section = "\n".join(lines[volumes_section_idx:])
        assert "  mask_src_api:" in volumes_section
        assert "  vol_claude_root_.local:" in volumes_section


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
# Marked-push drain on create — drains the queue; does NOT dump pushed_files
# =============================================================================


class TestMarkedPushDrainOnCreate:
    """execute_create runs drain_marked_push (the single replay path) to deliver
    any pre-container Pushes. It does NOT dump config.pushed_files into the queue
    — a clean first create has none; a recreate uses the manual export escape
    hatch. Per-file cp failures land in details, not fatal. Delivery-agnostic.
    """

    def _patches_for_create(self, tmp_path: Path):
        """Patches sufficient for execute_create to reach the dump+drain block."""
        from IgnoreScope.core.hierarchy import ContainerHierarchy

        h = ContainerHierarchy()
        h.mask_volume_names = []
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

    def test_empty_pushed_files_drain_runs(self, tmp_path: Path):
        """No pushed_files → the drain is still invoked (it'll find an empty queue)."""
        config = _make_config(tmp_path=tmp_path)
        config.pushed_files = set()

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle.add_marked_push",
        ) as mock_add, patch(
            "IgnoreScope.docker.container_lifecycle.drain_marked_push",
            return_value=OpResult(success=True, message="No files queued for push"),
        ) as mock_drain:
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        mock_add.assert_not_called()  # create never dumps
        mock_drain.assert_called_once()
        assert mock_drain.call_args.kwargs["config"] is config
        assert mock_drain.call_args.kwargs["on_stale"] == "replace"

    def test_bind_delivery_clears_pushed_files_and_drains(self, tmp_path: Path):
        """Create CLEARS config.pushed_files (fresh container, nothing confirmed)
        and does NOT dump them into the queue — the drain re-adds only what it
        actually cp's in (here: nothing, since the queue is empty)."""
        from IgnoreScope.core.mount_spec_path import MountSpecPath

        src = tmp_path / "src"
        src.mkdir()
        pushed = tmp_path / "src" / "config.json"
        pushed.write_text("{}")

        config = _make_config(tmp_path=tmp_path)
        config.mount_specs = [MountSpecPath(mount_root=src, patterns=[], delivery="bind")]
        config.pushed_files = {pushed}

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle.add_marked_push",
        ) as mock_add, patch(
            "IgnoreScope.docker.container_lifecycle.drain_marked_push",
            return_value=OpResult(success=True, message="No files queued for push"),
        ) as mock_drain:
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        mock_add.assert_not_called()           # create never dumps
        assert config.pushed_files == set()    # cleared; mocked drain re-adds nothing
        mock_drain.assert_called_once()
        assert mock_drain.call_args.kwargs["config"] is config
        assert mock_drain.call_args.kwargs["on_stale"] == "replace"

    def test_detached_delivery_drains_after_detached_init(self, tmp_path: Path):
        """Detached scope → the drain runs after _detached_init; still no dump."""
        from IgnoreScope.core.mount_spec_path import MountSpecPath

        src = tmp_path / "src"
        src.mkdir()
        pushed = tmp_path / "src" / "secret.env"
        pushed.write_text("X=1")

        config = _make_config(tmp_path=tmp_path)
        config.mount_specs = [
            MountSpecPath(
                mount_root=src, patterns=[], delivery="detached", host_path=src,
            ),
        ]
        config.pushed_files = {pushed}

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle._detached_init",
            return_value=OpResult(success=True, message="ok", details=[]),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.add_marked_push",
        ) as mock_add, patch(
            "IgnoreScope.docker.container_lifecycle.drain_marked_push",
            return_value=OpResult(success=True, message="No files queued for push"),
        ) as mock_drain:
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        mock_add.assert_not_called()
        mock_drain.assert_called_once()

    def test_drain_incomplete_in_details(self, tmp_path: Path):
        """A non-fatal drain failure → its message + notes land in result.details."""
        config = _make_config(tmp_path=tmp_path)
        config.pushed_files = set()

        patches = self._patches_for_create(tmp_path)
        with patch(
            "IgnoreScope.docker.container_lifecycle.drain_marked_push",
            return_value=OpResult(
                success=False,
                message="Container could not be started: boom",
                details=["cp failed, left queued: missing.txt — denied"],
            ),
        ):
            result, _ = self._run_create(patches, tmp_path, config)

        assert result.success is True
        assert any("marked-push drain incomplete" in d for d in result.details)
        assert any("cp failed" in d for d in result.details)
