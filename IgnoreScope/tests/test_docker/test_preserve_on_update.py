"""Tests for Virtual Mount preserve_on_update lifecycle hook.

Covers the two helper functions that implement the preserve/restore cycle
around container recreate:

- ``_preserve_detached_folders`` — pulls container content to a host tmp
  staging dir for every ``preserve_on_update=True`` spec. Called BEFORE
  ``docker compose down``. Fail-safe: cp-out failure aborts the outer
  update without touching the container.

- ``_restore_detached_folders`` — pushes staged content back into the
  recreated container using ``docker cp src/. cname:dst``. Called AFTER
  ``_detached_init`` has mkdir'd the destination. cp-back failure is
  non-fatal: the update completes, the folder is left empty.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from IgnoreScope.core.config import ScopeDockerConfig
from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.core.op_result import OpError
from IgnoreScope.docker.container_lifecycle import (
    _preserve_detached_folders,
    _restore_detached_folders,
    _resolve_spec_container_path,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_config(
    tmp_path: Path,
    specs: list[MountSpecPath],
    container_root: str = "/workspace",
) -> ScopeDockerConfig:
    return ScopeDockerConfig(
        scope_name="preserve-test",
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
        """Config with no preserve specs → empty snapshots, no docker calls."""
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
            result, snapshots = _preserve_detached_folders(
                "scope-x", config, tmp_path / "staging",
            )

        assert result.success is True
        assert snapshots == {}
        running.assert_not_called()
        pull.assert_not_called()
        exec_mock.assert_not_called()

    def test_happy_path_pulls_content(self, tmp_path: Path):
        """Preserve spec with existing container path → pull_file_from_container called."""
        cache = Path("/workspace/cache")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )
        staging = tmp_path / "staging"
        staging.mkdir()

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
            result, snapshots = _preserve_detached_folders(
                "scope-x", config, staging,
            )

        assert result.success is True
        assert 0 in snapshots
        cpath, snap_dir = snapshots[0]
        assert cpath == "/workspace/cache"
        assert snap_dir == staging / "spec_0"
        # test -e check was run
        exec_calls = [call.args for call in exec_mock.call_args_list]
        assert any(
            cmd[1][:2] == ["test", "-e"] and cmd[1][2] == "/workspace/cache"
            for cmd in exec_calls
        )
        # pull_file_from_container called with the resolved path and snap dir
        pull.assert_called_once()
        assert pull.call_args.args[1] == "/workspace/cache"
        assert pull.call_args.args[2] == snap_dir

    def test_missing_container_path_skips_without_pull(self, tmp_path: Path):
        """test -e reports missing → snapshot entry recorded, no pull call."""
        cache = Path("/workspace/first_run")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )
        staging = tmp_path / "staging"
        staging.mkdir()

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.exec_in_container",
            return_value=(False, "", ""),  # test -e → not exists
        ), patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container"
        ) as pull:
            result, snapshots = _preserve_detached_folders(
                "scope-x", config, staging,
            )

        assert result.success is True
        assert 0 in snapshots  # placeholder for restore's no-op branch
        pull.assert_not_called()
        assert any("not present" in d for d in result.details)

    def test_cp_out_failure_aborts(self, tmp_path: Path):
        """pull_file_from_container failure → success=False, empty snapshots."""
        cache = Path("/workspace/cache")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )
        staging = tmp_path / "staging"
        staging.mkdir()

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
            result, snapshots = _preserve_detached_folders(
                "scope-x", config, staging,
            )

        assert result.success is False
        assert snapshots == {}
        assert "cp-out failed" in result.message
        assert "permission denied" in result.message

    def test_container_not_running_aborts(self, tmp_path: Path):
        """ensure_container_running failure → CONTAINER_NOT_RUNNING error, no pull."""
        cache = Path("/workspace/cache")
        config = _make_config(
            tmp_path, specs=[_preserve_spec(cache, host_path=None)],
        )
        staging = tmp_path / "staging"
        staging.mkdir()

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(False, "container dead"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.pull_file_from_container"
        ) as pull:
            result, snapshots = _preserve_detached_folders(
                "scope-x", config, staging,
            )

        assert result.success is False
        assert result.error == OpError.CONTAINER_NOT_RUNNING
        assert snapshots == {}
        pull.assert_not_called()

    def test_mixed_preserve_and_non_preserve(self, tmp_path: Path):
        """Only preserve=True specs are snapshotted, in their original index order."""
        src_a = tmp_path / "a"
        src_a.mkdir()
        cache_b = Path("/workspace/b")
        src_c = tmp_path / "c"
        src_c.mkdir()
        config = _make_config(
            tmp_path,
            specs=[
                # Index 0: not preserved — excluded.
                _preserve_spec(src_a, host_path=src_a, preserve=False),
                # Index 1: preserved, container-only.
                _preserve_spec(cache_b, host_path=None, preserve=True),
                # Index 2: not preserved.
                _preserve_spec(src_c, host_path=src_c, preserve=False),
            ],
        )
        staging = tmp_path / "staging"
        staging.mkdir()

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
            result, snapshots = _preserve_detached_folders(
                "scope-x", config, staging,
            )

        assert result.success is True
        assert list(snapshots.keys()) == [1]  # only the preserve=True spec
        # pull called exactly once, for spec 1
        assert pull.call_count == 1
        assert pull.call_args.args[1] == "/workspace/b"


# ──────────────────────────────────────────────
# _restore_detached_folders
# ──────────────────────────────────────────────


class TestRestoreDetachedFolders:
    def test_empty_snapshots_is_noop(self, tmp_path: Path):
        """Empty snapshots dict → returns [] without any docker calls."""
        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running"
        ) as running, patch(
            "IgnoreScope.docker.container_lifecycle.push_directory_contents_to_container"
        ) as push:
            notes = _restore_detached_folders("scope-x", {})

        assert notes == []
        running.assert_not_called()
        push.assert_not_called()

    def test_happy_path_pushes_contents(self, tmp_path: Path):
        """Populated snapshot dir → push_directory_contents_to_container called."""
        snap = tmp_path / "snap0"
        snap.mkdir()
        (snap / "data.txt").write_text("preserved", encoding="utf-8")
        snapshots = {0: ("/workspace/cache", snap)}

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.push_directory_contents_to_container",
            return_value=(True, "ok"),
        ) as push:
            notes = _restore_detached_folders("scope-x", snapshots)

        push.assert_called_once_with("scope-x", snap, "/workspace/cache")
        assert any("restored:" in n for n in notes)

    def test_empty_snapshot_dir_skipped(self, tmp_path: Path):
        """Snapshot dir doesn't exist (missing source case) → skipped, no push."""
        snap = tmp_path / "never_created"
        snapshots = {0: ("/workspace/first_run", snap)}

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.push_directory_contents_to_container"
        ) as push:
            notes = _restore_detached_folders("scope-x", snapshots)

        push.assert_not_called()
        assert any("empty snapshot" in n for n in notes)

    def test_cp_back_failure_non_fatal(self, tmp_path: Path):
        """push_directory_contents_to_container failure → warning note, no exception."""
        snap = tmp_path / "snap0"
        snap.mkdir()
        (snap / "data.txt").write_text("x", encoding="utf-8")
        snapshots = {0: ("/workspace/cache", snap)}

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.push_directory_contents_to_container",
            return_value=(False, "no space left"),
        ):
            notes = _restore_detached_folders("scope-x", snapshots)

        assert any("restore FAILED" in n and "no space left" in n for n in notes)

    def test_container_not_running_returns_notice(self, tmp_path: Path):
        """ensure_container_running failure → single notice note, no pushes."""
        snap = tmp_path / "snap0"
        snap.mkdir()
        snapshots = {0: ("/workspace/cache", snap)}

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(False, "not running"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.push_directory_contents_to_container"
        ) as push:
            notes = _restore_detached_folders("scope-x", snapshots)

        push.assert_not_called()
        assert len(notes) == 1
        assert "restore skipped" in notes[0]

    def test_mixed_success_and_failure_aggregated(self, tmp_path: Path):
        """Multiple specs: each outcome reported independently."""
        snap_a = tmp_path / "snap_a"
        snap_a.mkdir()
        (snap_a / "a.txt").write_text("a", encoding="utf-8")
        snap_b = tmp_path / "snap_b"
        snap_b.mkdir()
        (snap_b / "b.txt").write_text("b", encoding="utf-8")
        snapshots = {
            0: ("/workspace/a", snap_a),
            1: ("/workspace/b", snap_b),
        }

        # First push succeeds, second fails
        def fake_push(cname, host_dir, cpath, timeout=60):
            if cpath == "/workspace/a":
                return (True, "ok")
            return (False, "io error")

        with patch(
            "IgnoreScope.docker.container_lifecycle.ensure_container_running",
            return_value=(True, "ok"),
        ), patch(
            "IgnoreScope.docker.container_lifecycle.push_directory_contents_to_container",
            side_effect=fake_push,
        ):
            notes = _restore_detached_folders("scope-x", snapshots)

        assert any("restored:" in n and "/workspace/a" in n for n in notes)
        assert any("restore FAILED" in n and "/workspace/b" in n for n in notes)


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
