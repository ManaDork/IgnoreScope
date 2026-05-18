"""Tests for Virtual Mount preserve_on_update lifecycle hook.

Covers ``_preserve_detached_folders`` — pulls container content into a
persistent host snapshot dir and enqueues a ``StagedEntry`` in
``marked_staged_scope.json`` for every ``preserve_on_update=True`` spec.
Called BEFORE ``docker compose down``. Fail-safe: cp-out failure aborts the
outer update without touching the container.

The complementary restore is the existing ``drain_marked_push`` (Phase 10a);
its behavior on staged entries lives in
``tests/test_docker/test_marked_push_drain.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from IgnoreScope.core.config import ScopeDockerConfig
from IgnoreScope.core.marked_staged import (
    load_marked_staged,
    snapshot_path_for,
)
from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.core.op_result import OpError
from IgnoreScope.docker.container_lifecycle import (
    _preserve_detached_folders,
    _resolve_spec_container_path,
)


SCOPE = "preserve-test"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_config(
    tmp_path: Path,
    specs: list[MountSpecPath],
    container_root: str = "/workspace",
) -> ScopeDockerConfig:
    return ScopeDockerConfig(
        scope_name=SCOPE,
        host_project_root=tmp_path,
        host_container_root=tmp_path,
        container_root=container_root,
        mount_specs=specs,
    )


def _preserve_spec(
    mount_root: Path,
    *,
    host_path: Path | None,
    preserve: bool = True,
) -> MountSpecPath:
    """Build a detached+folder spec with preserve_on_update toggleable."""
    return MountSpecPath(
        mount_root=mount_root,
        patterns=[],
        delivery="detached",
        host_path=host_path,
        content_seed="folder",
        preserve_on_update=preserve,
    )


# ──────────────────────────────────────────────
# _resolve_spec_container_path
# ──────────────────────────────────────────────


class TestResolveSpecContainerPath:
    def test_container_only_uses_mount_root_as_posix(self, tmp_path: Path):
        """host_path=None spec: mount_root is container-logical."""
        cpath = Path("/workspace/cache")
        config = _make_config(tmp_path, specs=[])
        ms = _preserve_spec(cpath, host_path=None)

        assert _resolve_spec_container_path(ms, config) == "/workspace/cache"

    def test_host_backed_translates_via_hierarchy(self, tmp_path: Path):
        """host_path=set spec: translates via to_container_path."""
        host_sub = tmp_path / "sub"
        host_sub.mkdir()
        config = _make_config(tmp_path, specs=[])
        ms = _preserve_spec(host_sub, host_path=host_sub)

        cpath = _resolve_spec_container_path(ms, config)
        # to_container_path → {container_root}/{rel to host_container_root}
        assert cpath.endswith("/sub")
        assert cpath.startswith("/workspace")


# ──────────────────────────────────────────────
# _preserve_detached_folders
# ──────────────────────────────────────────────


class TestPreserveDetachedFolders:
    def test_no_preserve_specs_is_noop(self, tmp_path: Path):
        """Config with no preserve specs → success, no docker calls, no queue file."""
        src = tmp_path / "src"
        src.mkdir()
        config = _make_config(
            tmp_path,
            specs=[_preserve_spec(src, host_path=src, preserve=False)],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running"
        ) as running, patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container"
        ) as pull, patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container"
        ) as exec_mock:
            result = _preserve_detached_folders(
                "scope-x", config,
                host_project_root=tmp_path, scope_name=SCOPE,
            )

        assert result.success is True
        assert load_marked_staged(tmp_path, SCOPE) == set()
        running.assert_not_called()
        pull.assert_not_called()
        exec_mock.assert_not_called()

    def test_happy_path_pulls_content_and_enqueues_staged(self, tmp_path: Path):
        """Preserve spec with existing container path → pull + StagedEntry enqueued."""
        cache = Path("/workspace/cache")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(True, "", ""),
        ) as exec_mock, patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container",
            return_value=(True, "ok"),
        ) as pull:
            result = _preserve_detached_folders(
                "scope-x", config,
                host_project_root=tmp_path, scope_name=SCOPE,
            )

        assert result.success is True

        # test -e check was run for the cpath
        exec_calls = [call.args for call in exec_mock.call_args_list]
        assert any(
            cmd[1][:2] == ["test", "-e"] and cmd[1][2] == "/workspace/cache"
            for cmd in exec_calls
        )

        # pull_file_from_container called with the resolved path and the
        # deterministic snapshot dir under .ignore_scope/<scope>/_snapshots/.
        expected_snap = snapshot_path_for(tmp_path, SCOPE, "/workspace/cache")
        pull.assert_called_once()
        assert pull.call_args.args[1] == "/workspace/cache"
        assert pull.call_args.args[2] == expected_snap

        # marked_staged_scope.json now holds exactly one entry for this target.
        staged = load_marked_staged(tmp_path, SCOPE)
        assert len(staged) == 1
        entry = next(iter(staged))
        assert entry.target == "/workspace/cache"
        assert entry.is_dir is True
        assert entry.source == expected_snap

    def test_missing_container_path_skips_without_pull_or_enqueue(self, tmp_path: Path):
        """test -e reports missing → nothing enqueued, no pull call (restore is no-op)."""
        cache = Path("/workspace/first_run")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(False, "", ""),  # test -e → not exists
        ), patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container"
        ) as pull:
            result = _preserve_detached_folders(
                "scope-x", config,
                host_project_root=tmp_path, scope_name=SCOPE,
            )

        assert result.success is True
        assert load_marked_staged(tmp_path, SCOPE) == set()
        pull.assert_not_called()
        assert any("not present" in d for d in result.details)

    def test_cp_out_failure_aborts(self, tmp_path: Path):
        """pull_file_from_container failure → success=False; partial enqueue persists for recovery."""
        cache = Path("/workspace/cache")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(True, "", ""),  # test -e → exists
        ), patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container",
            return_value=(False, "permission denied"),
        ):
            result = _preserve_detached_folders(
                "scope-x", config,
                host_project_root=tmp_path, scope_name=SCOPE,
            )

        assert result.success is False
        assert "cp-out failed" in result.message
        assert "permission denied" in result.message
        # This spec's pull failed before enqueue, so the queue is still empty;
        # the abort intentionally leaves earlier-enqueued entries on disk so
        # `push-marked` can recover. Single-spec failure → no entries.
        assert load_marked_staged(tmp_path, SCOPE) == set()

    def test_container_not_running_aborts(self, tmp_path: Path):
        """ensure_container_running failure → CONTAINER_NOT_RUNNING error, no pull, no enqueue."""
        cache = Path("/workspace/cache")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(False, "container dead"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container"
        ) as pull:
            result = _preserve_detached_folders(
                "scope-x", config,
                host_project_root=tmp_path, scope_name=SCOPE,
            )

        assert result.success is False
        assert result.error == OpError.CONTAINER_NOT_RUNNING
        assert load_marked_staged(tmp_path, SCOPE) == set()
        pull.assert_not_called()

    def test_mixed_preserve_and_non_preserve(self, tmp_path: Path):
        """Only preserve=True specs are snapshotted and enqueued."""
        src_a = tmp_path / "a"
        src_a.mkdir()
        cache_b = Path("/workspace/b")
        src_c = tmp_path / "c"
        src_c.mkdir()
        config = _make_config(
            tmp_path,
            specs=[
                _preserve_spec(src_a, host_path=src_a, preserve=False),
                _preserve_spec(cache_b, host_path=None, preserve=True),
                _preserve_spec(src_c, host_path=src_c, preserve=False),
            ],
        )

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(True, "", ""),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container",
            return_value=(True, "ok"),
        ) as pull:
            result = _preserve_detached_folders(
                "scope-x", config,
                host_project_root=tmp_path, scope_name=SCOPE,
            )

        assert result.success is True
        # pull called exactly once, for the preserve=True spec
        assert pull.call_count == 1
        assert pull.call_args.args[1] == "/workspace/b"
        # Exactly one staged entry, for that target.
        staged = load_marked_staged(tmp_path, SCOPE)
        assert {e.target for e in staged} == {"/workspace/b"}

    def test_wipes_stale_snapshot_dir_before_pull(self, tmp_path: Path):
        """If a snapshot dir from a prior aborted preserve exists, it's wiped first
        (pull_file_from_container's dst must not pre-exist)."""
        cache = Path("/workspace/cache")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )
        # Plant a stale snapshot from a previous aborted run.
        stale = snapshot_path_for(tmp_path, SCOPE, "/workspace/cache")
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "old.txt").write_text("stale", encoding="utf-8")

        captured: dict[str, bool] = {}

        def fake_pull(name, cpath, dst, timeout=30):
            # Assert dst doesn't pre-exist at pull time.
            captured["dst_existed"] = dst.exists()
            return (True, "ok")

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(True, "", ""),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container",
            side_effect=fake_pull,
        ):
            result = _preserve_detached_folders(
                "scope-x", config,
                host_project_root=tmp_path, scope_name=SCOPE,
            )

        assert result.success is True
        assert captured["dst_existed"] is False


# ──────────────────────────────────────────────
# Schema integration sanity — volume specs never preserve
# ──────────────────────────────────────────────


class TestSchemaIntegration:
    def test_volume_delivery_cannot_set_preserve(self):
        """delivery='volume' + preserve_on_update=True is a validator error —
        volumes survive recreate natively and don't need the flag.
        """
        ms = MountSpecPath(
            mount_root=Path("/workspace/persistent"),
            patterns=[],
            delivery="volume",
            host_path=None,
            content_seed="folder",
            preserve_on_update=True,
        )
        errors = ms.validate()
        assert any("preserve_on_update" in e for e in errors)

    def test_bind_delivery_cannot_set_preserve(self):
        """delivery='bind' + preserve_on_update=True is a validator error."""
        tmp = Path("/tmp/x")
        ms = MountSpecPath(
            mount_root=tmp,
            patterns=[],
            delivery="bind",
            host_path=tmp,
            content_seed="tree",
            preserve_on_update=True,
        )
        errors = ms.validate()
        assert any("preserve_on_update" in e for e in errors)

    def test_detached_folder_preserve_is_valid(self):
        """delivery='detached' + content_seed='folder' + preserve=True is the only valid combo."""
        ms = MountSpecPath(
            mount_root=Path("/workspace/cache"),
            patterns=[],
            delivery="detached",
            host_path=None,
            content_seed="folder",
            preserve_on_update=True,
        )
        errors = ms.validate()
        assert not any("preserve_on_update" in e for e in errors)
