"""Integration tests for per-spec delivery pipeline (Task 2.10).

End-to-end verification that ``delivery="bind"`` vs ``delivery="detached"``
on individual MountSpecPath instances drives the correct behavior through:

  - core.hierarchy.compute_container_hierarchy (volume emission)
  - docker.compose.generate_compose_with_masks (YAML shape)
  - docker.container_lifecycle._detached_init (docker cp walk + post-cp rm)

These tests use mocked subprocess calls (``push_file_to_container``,
``exec_in_container``, ``ensure_container_running``) so they do not need
Docker to be running.

Coverage (AC from planning/tasks/virtual-mount-phase-1.md § 2.10):
  - Create + recreate bind-only scope → stable compose shape.
  - Create detached-only scope → cp walk runs, no volumes emitted.
  - Detached + mask → post-cp rm -rf inside container.
  - Detached + reveal → reveal path added to cp pairs.
  - Mixed scope → bind spec emits volumes; detached spec is cp'd.
  - Convert gesture → flipping delivery flips the emission shape.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from IgnoreScope.core.config import ScopeDockerConfig
from IgnoreScope.core.hierarchy import compute_container_hierarchy
from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.docker.compose import generate_compose_with_masks
from IgnoreScope.docker.container_lifecycle import _detached_init


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _spec(
    mount_root: Path,
    patterns: list[str] | None = None,
    delivery: str = "bind",
) -> MountSpecPath:
    return MountSpecPath(
        mount_root=mount_root,
        patterns=list(patterns or []),
        delivery=delivery,
    )


def _make_config(
    tmp_path: Path,
    specs: list[MountSpecPath],
) -> ScopeDockerConfig:
    return ScopeDockerConfig(
        scope_name="vmount-test",
        host_project_root=tmp_path,
        host_container_root=tmp_path,
        container_root="/workspace",
        mount_specs=specs,
    )


def _compose_from_config(config: ScopeDockerConfig, name: str = "test-ctr") -> str:
    """Run the full hierarchy → compose pipeline."""
    hierarchy = compute_container_hierarchy(
        container_root=config.container_root,
        mount_specs=config.mount_specs,
        pushed_files=config.pushed_files,
        host_project_root=config.host_project_root,
        host_container_root=config.host_container_root,
    )
    return generate_compose_with_masks(
        ordered_volumes=hierarchy.ordered_volumes,
        mask_volume_names=hierarchy.mask_volume_names,
        host_project_root=config.host_project_root,
        docker_container_name=name,
        container_root=config.container_root,
        project_name=config.host_project_root.name,
        isolation_volume_entries=hierarchy.isolation_volume_entries,
        isolation_volume_names=hierarchy.isolation_volume_names,
    )


def _run_detached_init(config: ScopeDockerConfig):
    """Invoke _detached_init with mocked docker subprocess calls.

    Returns a 3-tuple (result, push_mock, exec_mock).
    """
    with patch(
        "IgnoreScope.docker.container_lifecycle.ensure_container_running",
        return_value=(True, "ok"),
    ), patch(
        "IgnoreScope.docker.container_lifecycle.ensure_container_directories",
        return_value=(True, "dirs ok"),
    ), patch(
        "IgnoreScope.docker.container_lifecycle.push_file_to_container",
        return_value=(True, "ok"),
    ) as push, patch(
        "IgnoreScope.docker.container_lifecycle.exec_in_container",
        return_value=(True, "", ""),
    ) as exec_mock:
        result = _detached_init("vmount-test", config)
    return result, push, exec_mock


# ──────────────────────────────────────────────
# Bind-only scopes (baseline — pre-pivot behavior)
# ──────────────────────────────────────────────


class TestBindOnlyScope:
    """All specs delivery="bind" → classic volume-layer behavior."""

    def test_bind_only_emits_volumes_and_no_cp_walk(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, [_spec(src, delivery="bind")])

        compose = _compose_from_config(config)
        assert "/workspace/src" in compose, "bind spec must bind-mount mount_root"

        result, push, exec_mock = _run_detached_init(config)
        assert result.success is True
        push.assert_not_called()
        exec_mock.assert_not_called()

    def test_bind_only_recreate_is_stable(self, tmp_path: Path):
        """Recreating the same config emits byte-identical compose."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, [_spec(src, delivery="bind")])

        first = _compose_from_config(config, name="stable-ctr")
        second = _compose_from_config(config, name="stable-ctr")
        assert first == second


# ──────────────────────────────────────────────
# Detached-only scopes
# ──────────────────────────────────────────────


class TestDetachedOnlyScope:
    """All specs delivery="detached" → cp walk, no volumes."""

    def test_detached_only_omits_project_volumes(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, [_spec(src, delivery="detached")])

        compose = _compose_from_config(config)
        assert "/workspace/src" not in compose, (
            "detached spec must NOT bind-mount — content arrives via docker cp"
        )
        assert "mask_" not in compose

    def test_detached_only_runs_cp_walk(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, [_spec(src, delivery="detached")])

        result, push, _ = _run_detached_init(config)
        assert result.success is True
        host_paths = [call.args[1] for call in push.call_args_list]
        assert src in host_paths, f"detached mount_root must be cp'd: {host_paths}"


# ──────────────────────────────────────────────
# Detached + mask / reveal
# ──────────────────────────────────────────────


class TestDetachedWithPatterns:
    """Detached specs translate masks → post-cp rm, reveals → additional cp."""

    def test_detached_mask_triggers_rm(self, tmp_path: Path):
        src = tmp_path / "src"
        (src / "vendor").mkdir(parents=True)
        config = _make_config(
            tmp_path,
            [_spec(src, patterns=["vendor/"], delivery="detached")],
        )

        # Compose must NOT declare a mask volume for this spec.
        # Check for the ``mask_<name>:`` volume-entry token specifically —
        # the generated comment header and pytest tmp_path names may
        # legitimately contain the substring "mask" elsewhere.
        compose = _compose_from_config(config)
        for line in compose.splitlines():
            stripped = line.strip().lstrip("- ")
            assert not stripped.startswith("mask_"), (
                f"unexpected mask volume entry: {line}"
            )

        # Lifecycle must rm the masked subtree inside the container post-cp
        result, _, exec_mock = _run_detached_init(config)
        rm_calls = [call.args for call in exec_mock.call_args_list]
        assert any(
            cmd[1][:2] == ["rm", "-rf"] and cmd[1][2].endswith("/vendor")
            for cmd in rm_calls
        ), f"expected rm -rf on masked subtree, got: {rm_calls}"
        assert result.success is True

    def test_detached_reveal_adds_cp_pair(self, tmp_path: Path):
        src = tmp_path / "src"
        vendor = src / "vendor"
        public = vendor / "public"
        public.mkdir(parents=True)
        config = _make_config(
            tmp_path,
            [_spec(
                src,
                patterns=["vendor/", "!vendor/public/"],
                delivery="detached",
            )],
        )

        # Compose: no bind punch-through for reveal (detached emits nothing)
        compose = _compose_from_config(config)
        assert "/workspace/src/vendor/public" not in compose

        # Lifecycle: both mount_root and reveal path are cp'd
        _, push, _ = _run_detached_init(config)
        host_paths = [call.args[1] for call in push.call_args_list]
        assert src in host_paths
        assert public in host_paths


# ──────────────────────────────────────────────
# Mixed scope — bind + detached coexist
# ──────────────────────────────────────────────


class TestMixedScope:
    """Single scope with one bind spec and one detached spec."""

    def test_mixed_bind_live_detached_cpd(self, tmp_path: Path):
        src_bind = tmp_path / "src_bind"
        src_detached = tmp_path / "src_detached"
        src_bind.mkdir()
        src_detached.mkdir()
        config = _make_config(
            tmp_path,
            [
                _spec(src_bind, delivery="bind"),
                _spec(src_detached, delivery="detached"),
            ],
        )

        compose = _compose_from_config(config)
        # bind spec is live in compose
        assert "/workspace/src_bind" in compose
        # detached spec does NOT appear as a volume
        assert "/workspace/src_detached" not in compose

        _, push, _ = _run_detached_init(config)
        host_paths = [call.args[1] for call in push.call_args_list]
        # Detached is cp'd; bind is skipped
        assert src_detached in host_paths
        assert src_bind not in host_paths


# ──────────────────────────────────────────────
# Convert gesture — flipping delivery flips the pipeline
# ──────────────────────────────────────────────


class TestConvertGesture:
    """Toggling ``delivery`` on an existing spec flips emission + cp walk.

    The "convert gesture" in the GUI is a direct ``ms.delivery`` flip on the
    MountSpecPath. After flipping, recomputing the hierarchy + compose and
    re-running _detached_init must reflect the new mode.
    """

    def test_bind_to_detached_flip(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        spec = _spec(src, delivery="bind")
        config = _make_config(tmp_path, [spec])

        # Before flip: bind-mounted, no cp walk
        compose_before = _compose_from_config(config)
        assert "/workspace/src" in compose_before
        _, push_before, _ = _run_detached_init(config)
        push_before.assert_not_called()

        # Flip delivery in place (emulating GUI convert gesture)
        spec.delivery = "detached"

        # After flip: no bind mount, cp walk runs for mount_root
        compose_after = _compose_from_config(config)
        assert "/workspace/src" not in compose_after
        _, push_after, _ = _run_detached_init(config)
        host_paths = [call.args[1] for call in push_after.call_args_list]
        assert src in host_paths

    def test_detached_to_bind_flip(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        spec = _spec(src, delivery="detached")
        config = _make_config(tmp_path, [spec])

        # Before flip: no bind mount, cp walk runs
        compose_before = _compose_from_config(config)
        assert "/workspace/src" not in compose_before
        _, push_before, _ = _run_detached_init(config)
        host_paths_before = [call.args[1] for call in push_before.call_args_list]
        assert src in host_paths_before

        # Flip delivery back to bind
        spec.delivery = "bind"

        # After flip: bind-mounted, cp walk is no-op
        compose_after = _compose_from_config(config)
        assert "/workspace/src" in compose_after
        _, push_after, _ = _run_detached_init(config)
        push_after.assert_not_called()
