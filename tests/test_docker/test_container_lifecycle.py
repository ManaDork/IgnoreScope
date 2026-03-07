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
    """Create a minimal ContainerHierarchy mock with specified mask names."""
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
# execute_update
# =============================================================================

class TestExecuteUpdate:
    """Tests for container_lifecycle.execute_update."""

    def _patch_all(self, old_masks, new_masks, compose_down_ok=True, prune_ok=True):
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
