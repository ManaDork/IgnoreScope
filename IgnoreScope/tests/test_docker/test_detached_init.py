"""Tests for container_lifecycle._detached_init per-spec init.

Covers:
  - Iterates only detached specs (bind specs ignored)
  - ensure_container_running called before cp walk
  - L1 mount_root → docker cp pair
  - L3 reveal (!pattern) → docker cp pair
  - L2 mask pattern → post-cp rm -rf
  - Symlink / reparse point → mkdir stub, no cp
  - Empty mount_specs → no-op success with warning detail
  - All-bind config → no-op success (no detached specs)
  - OpResult.details aggregates cp and mask notes
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from IgnoreScope.core.config import ScopeDockerConfig
from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.core.op_result import OpError
from IgnoreScope.docker.container_lifecycle import (
    _detached_init,
    _EMPTY_MOUNT_SPECS_WARNING,
    _is_reparse_point,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_config(
    tmp_path: Path,
    specs: list[MountSpecPath],
) -> ScopeDockerConfig:
    """Build a config with the supplied specs."""
    return ScopeDockerConfig(
        scope_name="detached-test",
        host_project_root=tmp_path,
        host_container_root=tmp_path,
        container_root="/workspace",
        mount_specs=specs,
    )


def _spec(
    mount_root: Path,
    patterns: list[str],
    delivery: str = "detached",
) -> MountSpecPath:
    return MountSpecPath(
        mount_root=mount_root, patterns=list(patterns), delivery=delivery,
    )


# ──────────────────────────────────────────────
# Guard cases
# ──────────────────────────────────────────────


class TestGuards:
    def test_empty_mount_specs_returns_warning(self, tmp_path: Path):
        """No mount_specs → success with empty-specs warning detail."""
        config = _make_config(tmp_path, specs=[])

        result = _detached_init("scope-x", config)

        assert result.success is True
        assert result.details == [_EMPTY_MOUNT_SPECS_WARNING]

    def test_all_bind_config_is_noop(self, tmp_path: Path):
        """No detached specs → success, no docker calls."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(
            tmp_path, specs=[_spec(src, patterns=[], delivery="bind")],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running"
        ) as running, patch(
            "IgnoreScope.docker.container_lifecycle.push_file_to_container"
        ) as push, patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container"
        ) as exec_mock:
            result = _detached_init("scope-x", config)

        assert result.success is True
        running.assert_not_called()
        push.assert_not_called()
        exec_mock.assert_not_called()

    def test_container_not_running_returns_error(self, tmp_path: Path):
        """ensure_container_running failure → OpError.CONTAINER_NOT_RUNNING."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, specs=[_spec(src, patterns=[])])

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(False, "container dead"),
        ):
            result = _detached_init("scope-x", config)

        assert result.success is False
        assert result.error == OpError.CONTAINER_NOT_RUNNING


# ──────────────────────────────────────────────
# cp walk — L1 + L3
# ──────────────────────────────────────────────


class TestCpWalk:
    def test_l1_mount_root_cp_pair(self, tmp_path: Path):
        """mount_root is always cp'd."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, specs=[_spec(src, patterns=[])])

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
        ):
            result = _detached_init("scope-x", config)

        assert result.success is True
        calls = [call.args for call in push.call_args_list]
        assert any(a[1] == src for a in calls), f"Expected cp of src, got: {calls}"

    def test_reveal_pattern_adds_cp_pair(self, tmp_path: Path):
        """Negated (reveal) pattern target → cp pair."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        public = vendor / "public"
        public.mkdir(parents=True)
        config = _make_config(
            tmp_path,
            specs=[_spec(src, patterns=["vendor/", "!vendor/public/"])],
        )

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
        ):
            _detached_init("scope-x", config)

        host_paths = [call.args[1] for call in push.call_args_list]
        assert src in host_paths
        assert public in host_paths

    def test_mask_pattern_triggers_rm(self, tmp_path: Path):
        """Non-negated (mask) pattern target → rm -rf inside container."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(
            tmp_path, specs=[_spec(src, patterns=["vendor/"])],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_directories",
            return_value=(True, "dirs ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.push_file_to_container",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(True, "", ""),
        ) as exec_mock:
            result = _detached_init("scope-x", config)

        rm_calls = [call.args for call in exec_mock.call_args_list]
        assert any(
            cmd[1][:2] == ["rm", "-rf"] and cmd[1][2].endswith("/vendor")
            for cmd in rm_calls
        ), f"Expected rm -rf on vendor, got: {rm_calls}"
        assert any("masked: rm -rf" in d for d in result.details)


# ──────────────────────────────────────────────
# Mixed mode — only detached specs are processed
# ──────────────────────────────────────────────


class TestMixedMode:
    def test_bind_specs_skipped_in_mixed_config(self, tmp_path: Path):
        """Bind spec's mount_root must NOT appear in cp pairs."""
        src_bind = tmp_path / "src_bind"
        src_detached = tmp_path / "src_detached"
        src_bind.mkdir()
        src_detached.mkdir()
        config = _make_config(
            tmp_path,
            specs=[
                _spec(src_bind, patterns=[], delivery="bind"),
                _spec(src_detached, patterns=[], delivery="detached"),
            ],
        )

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
        ):
            _detached_init("scope-x", config)

        host_paths = [call.args[1] for call in push.call_args_list]
        assert src_detached in host_paths
        assert src_bind not in host_paths


# ──────────────────────────────────────────────
# Symlink / reparse-point handling
# ──────────────────────────────────────────────


class TestSymlinkHandling:
    def test_symlink_gets_stub_no_cp(self, tmp_path: Path):
        """Reparse points → mkdir stub, no cp call."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, specs=[_spec(src, patterns=[])])

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_directories",
            return_value=(True, "dirs ok"),
        ) as dirs, patch(
            "IgnoreScope.docker.container_lifecycle.push_file_to_container",
            return_value=(True, "ok"),
        ) as push, patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(True, "", ""),
        ), patch(
            "IgnoreScope.docker.container_lifecycle._is_reparse_point",
            return_value=True,
        ):
            result = _detached_init("scope-x", config)

        push.assert_not_called()
        assert any("symlink" in d for d in result.details)
        # ensure_container_directories called at least once for the stub path
        assert dirs.call_count >= 1


# ──────────────────────────────────────────────
# Details aggregation
# ──────────────────────────────────────────────


class TestDetails:
    def test_cp_failure_recorded_in_details(self, tmp_path: Path):
        """push_file_to_container failure → failure note in details, still success."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(tmp_path, specs=[_spec(src, patterns=[])])

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_directories",
            return_value=(True, "dirs ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.push_file_to_container",
            return_value=(False, "permission denied"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(True, "", ""),
        ):
            result = _detached_init("scope-x", config)

        assert any("cp failed" in d for d in result.details)


# ──────────────────────────────────────────────
# _is_reparse_point sanity
# ──────────────────────────────────────────────


class TestIsReparsePoint:
    def test_regular_directory_not_reparse(self, tmp_path: Path):
        d = tmp_path / "regular"
        d.mkdir()
        assert _is_reparse_point(d) is False

    def test_missing_path_not_reparse(self, tmp_path: Path):
        assert _is_reparse_point(tmp_path / "nonexistent") is False
