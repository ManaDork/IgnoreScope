"""Tests for the marked-push drain (IgnoreScope.docker.marked_push_drain).

Docker subprocess calls are mocked; the marked-push and marked-staged queue
files are real (tmp_path). The drain is exercised with an in-flight ``config``
object (the lifecycle path); one test covers the ``config=None`` load/save path.
Staged-queue tests live in the dedicated section at the end of the file.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from IgnoreScope.core.config import ScopeDockerConfig
from IgnoreScope.core.marked_push import add_marked_push, load_marked_push
from IgnoreScope.core.marked_staged import (
    StagedEntry,
    add_marked_staged,
    load_marked_staged,
    snapshot_path_for,
)
from IgnoreScope.core.op_result import OpResult
from IgnoreScope.docker import marked_push_drain as mpd
from IgnoreScope.docker.marked_push_drain import (
    drain_marked_push,
    drain_with_user_feedback,
)

SCOPE = "dev"
DOCKER = "proj-dev"


@pytest.fixture
def project(tmp_path):
    """Project root with one real host file already queued for push."""
    f = tmp_path / "src" / "a.txt"
    f.parent.mkdir(parents=True)
    f.write_text("host-content", encoding="utf-8")
    add_marked_push(tmp_path, SCOPE, [f])
    return tmp_path


@pytest.fixture
def host_file(project):
    return project / "src" / "a.txt"


@pytest.fixture
def config(project):
    cfg = ScopeDockerConfig(host_project_root=project, scope_name=SCOPE)
    return cfg


@pytest.fixture(autouse=True)
def _stub_docker_glue():
    """Stub the cheap, deterministic glue so each test only tunes the interesting bits."""
    with patch.object(mpd, "build_docker_name", return_value=DOCKER), \
         patch.object(mpd, "resolve_container_path", side_effect=lambda hp, cr, hcr: f"/workspace/{hp.name}"), \
         patch.object(mpd, "ensure_container_directories", return_value=(True, "ok")):
        yield


def _running_info():
    return {"id": "abc", "status": "running", "running": True, "image": "x", "created": ""}


def _stopped_info():
    return {"id": "abc", "status": "exited", "running": False, "image": "x", "created": ""}


def _mtime_probe(epoch: float | None):
    """exec_in_container side_effect: pretend `stat -c %Y` returns `epoch`, or fails."""
    if epoch is None:
        return (False, "", "stat: cannot stat: No such file or directory")
    return (True, str(int(epoch)), "")


# ── Container-state handling ───────────────────────────────────────

def test_empty_queue_short_circuits(tmp_path):
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    with patch.object(mpd, "get_container_info") as gci:
        res = drain_marked_push(tmp_path, SCOPE, config=cfg)
    assert res.success and "No files queued" in res.message
    gci.assert_not_called()


def test_missing_container_keeps_queue(project, host_file, config):
    with patch.object(mpd, "get_container_info", return_value=None):
        res = drain_marked_push(project, SCOPE, config=config)
    assert res.success
    assert "not created" in res.message
    assert load_marked_push(project, SCOPE) == {host_file}
    assert host_file not in config.pushed_files


def test_stopped_container_started_then_drains(project, host_file, config):
    hm = host_file.stat().st_mtime
    with patch.object(mpd, "get_container_info", return_value=_stopped_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "started")), \
         patch.object(mpd, "exec_in_container", return_value=_mtime_probe(None)), \
         patch.object(mpd, "push_file_to_container", return_value=(True, "pushed")) as push:
        res = drain_marked_push(project, SCOPE, config=config)
    assert res.success
    push.assert_called_once()
    assert host_file in config.pushed_files
    assert load_marked_push(project, SCOPE) == set()


def test_stopped_container_start_failure_is_fatal(project, host_file, config):
    with patch.object(mpd, "get_container_info", return_value=_stopped_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(False, "boom")):
        res = drain_marked_push(project, SCOPE, config=config)
    assert not res.success
    assert load_marked_push(project, SCOPE) == {host_file}
    assert host_file not in config.pushed_files


# ── Per-file outcomes (running container) ──────────────────────────

def _run_drain(project, config, *, container_mtime, push_ok=True, on_stale=None, progress=None):
    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "exec_in_container", return_value=_mtime_probe(container_mtime)), \
         patch.object(mpd, "push_file_to_container", return_value=(push_ok, "pushed" if push_ok else "cp denied")) as push:
        res = drain_marked_push(project, SCOPE, config=config, on_stale=on_stale, progress=progress)
    return res, push


def test_container_missing_file_pushes_and_promotes(project, host_file, config):
    res, push = _run_drain(project, config, container_mtime=None)
    assert res.success
    push.assert_called_once()
    assert host_file in config.pushed_files
    assert load_marked_push(project, SCOPE) == set()


def test_host_newer_than_container_pushes(project, host_file, config):
    hm = host_file.stat().st_mtime
    res, push = _run_drain(project, config, container_mtime=hm - 500)
    assert res.success
    push.assert_called_once()
    assert host_file in config.pushed_files
    assert load_marked_push(project, SCOPE) == set()


def test_host_stale_replace(project, host_file, config):
    hm = host_file.stat().st_mtime
    res, push = _run_drain(project, config, container_mtime=hm + 500, on_stale="replace")
    assert res.success
    push.assert_called_once()
    assert host_file in config.pushed_files
    assert load_marked_push(project, SCOPE) == set()


def test_host_stale_skip_leaves_queued(project, host_file, config):
    hm = host_file.stat().st_mtime
    res, push = _run_drain(project, config, container_mtime=hm + 500, on_stale="skip")
    assert res.success
    push.assert_not_called()
    assert host_file not in config.pushed_files
    assert load_marked_push(project, SCOPE) == {host_file}


def test_host_stale_skip_and_unmark(project, host_file, config):
    hm = host_file.stat().st_mtime
    # Pretend it was previously confirmed in the container.
    config.pushed_files.add(host_file)
    res, push = _run_drain(project, config, container_mtime=hm + 500, on_stale="skip_and_unmark")
    assert res.success
    push.assert_not_called()
    assert host_file not in config.pushed_files
    assert load_marked_push(project, SCOPE) == set()


def test_on_stale_callback_receives_path(project, host_file, config):
    hm = host_file.stat().st_mtime
    seen = []

    def cb(p):
        seen.append(p)
        return "replace"

    res, push = _run_drain(project, config, container_mtime=hm + 500, on_stale=cb)
    assert seen == [host_file]
    push.assert_called_once()


def test_cp_failure_leaves_queued_and_unpromoted(project, host_file, config):
    res, push = _run_drain(project, config, container_mtime=None, push_ok=False)
    assert res.success  # per-file failure is not fatal
    push.assert_called_once()
    assert host_file not in config.pushed_files
    assert load_marked_push(project, SCOPE) == {host_file}
    assert any("cp failed" in n for n in res.details)


def test_host_file_missing_on_disk(project, host_file, config):
    host_file.unlink()
    res, push = _run_drain(project, config, container_mtime=None)
    assert res.success
    push.assert_not_called()
    assert host_file not in config.pushed_files
    assert load_marked_push(project, SCOPE) == {host_file}
    assert any("host file missing" in n for n in res.details)


def test_progress_callback_invoked(project, host_file, config):
    calls = []
    _run_drain(project, config, container_mtime=None, progress=lambda i, t: calls.append((i, t)))
    assert calls == [(1, 1)]


def test_already_in_pushed_files_not_marked_dirty_again(project, host_file, config):
    # When the file is already tracked, a successful re-push must not toggle a
    # redundant save (owns_config path) — exercised via the config=None route below.
    config.pushed_files.add(host_file)
    res, push = _run_drain(project, config, container_mtime=None)
    assert res.success
    push.assert_called_once()
    assert host_file in config.pushed_files
    assert load_marked_push(project, SCOPE) == set()


# ── config=None: own load/save ─────────────────────────────────────

def test_owns_config_loads_and_saves(project, host_file):
    loaded = ScopeDockerConfig(host_project_root=project, scope_name=SCOPE)
    with patch.object(mpd, "load_config", return_value=loaded) as load, \
         patch.object(mpd, "save_config") as save, \
         patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "exec_in_container", return_value=_mtime_probe(None)), \
         patch.object(mpd, "push_file_to_container", return_value=(True, "pushed")):
        res = drain_marked_push(project, SCOPE)
    assert res.success
    load.assert_called_once()
    save.assert_called_once()
    assert host_file in loaded.pushed_files
    assert load_marked_push(project, SCOPE) == set()


def test_owns_config_no_save_when_nothing_changed(project, host_file):
    # File already tracked + already in container (so cp still runs, but pushed_files
    # is unchanged) → no save. (The cp itself isn't conditional on tracking, but the
    # `dirty` flag only flips when pushed_files actually changes.)
    loaded = ScopeDockerConfig(host_project_root=project, scope_name=SCOPE)
    loaded.pushed_files.add(host_file)
    with patch.object(mpd, "load_config", return_value=loaded), \
         patch.object(mpd, "save_config") as save, \
         patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "exec_in_container", return_value=_mtime_probe(None)), \
         patch.object(mpd, "push_file_to_container", return_value=(True, "pushed")):
        res = drain_marked_push(project, SCOPE)
    assert res.success
    save.assert_not_called()


# ── Staged queue (marked_staged_scope.json) ────────────────────────


def _make_staged_dir(project: Path, target: str) -> StagedEntry:
    """Create an on-disk snapshot dir and return its StagedEntry (is_dir=True)."""
    snap = snapshot_path_for(project, SCOPE, target)
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "payload.txt").write_text("snap", encoding="utf-8")
    return StagedEntry(source=snap, target=target, is_dir=True)


def _make_staged_file(project: Path, target: str) -> StagedEntry:
    snap = snapshot_path_for(project, SCOPE, target)
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text("snap-file", encoding="utf-8")
    return StagedEntry(source=snap, target=target, is_dir=False)


def test_both_queues_empty_short_circuits(tmp_path):
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    with patch.object(mpd, "get_container_info") as gci:
        res = drain_marked_push(tmp_path, SCOPE, config=cfg)
    assert res.success and "No files queued" in res.message
    gci.assert_not_called()


def test_staged_dir_entry_drains_and_leaves_pushed_files_untouched(tmp_path):
    # No host queue — only a staged dir entry.
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    entry = _make_staged_dir(tmp_path, "/Projects/foo")
    add_marked_staged(tmp_path, SCOPE, [entry])

    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "push_directory_contents_to_container", return_value=(True, "ok")) as push_dir, \
         patch.object(mpd, "push_file_to_container") as push_file:
        res = drain_marked_push(tmp_path, SCOPE, config=cfg)

    assert res.success
    push_dir.assert_called_once()
    # First positional: docker name; second: source path; third: target.
    args = push_dir.call_args.args
    assert args[1] == entry.source
    assert args[2] == entry.target
    push_file.assert_not_called()
    assert load_marked_staged(tmp_path, SCOPE) == set()
    assert cfg.pushed_files == set()  # staged restores never touch pushed_files


def test_staged_dir_entry_ensures_target_dir_first(tmp_path):
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    entry = _make_staged_dir(tmp_path, "/Projects/foo")
    add_marked_staged(tmp_path, SCOPE, [entry])

    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "ensure_container_directories", return_value=(True, "ok")) as ecd, \
         patch.object(mpd, "push_directory_contents_to_container", return_value=(True, "ok")):
        drain_marked_push(tmp_path, SCOPE, config=cfg)

    ecd.assert_called_once_with(DOCKER, ["/Projects/foo"])


def test_staged_file_entry_uses_push_file_and_ensures_parent(tmp_path):
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    entry = _make_staged_file(tmp_path, "/Projects/bar.cfg")
    add_marked_staged(tmp_path, SCOPE, [entry])

    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "ensure_container_directories", return_value=(True, "ok")) as ecd, \
         patch.object(mpd, "push_file_to_container", return_value=(True, "ok")) as push_file, \
         patch.object(mpd, "push_directory_contents_to_container") as push_dir:
        res = drain_marked_push(tmp_path, SCOPE, config=cfg)

    assert res.success
    push_file.assert_called_once()
    args = push_file.call_args.args
    assert args[1] == entry.source
    assert args[2] == entry.target
    push_dir.assert_not_called()
    ecd.assert_called_once_with(DOCKER, ["/Projects"])
    assert load_marked_staged(tmp_path, SCOPE) == set()
    assert cfg.pushed_files == set()


def test_staged_entry_missing_source_is_dropped_not_fatal(tmp_path):
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    target = "/Projects/gone"
    entry = StagedEntry(
        source=snapshot_path_for(tmp_path, SCOPE, target),
        target=target,
        is_dir=True,
    )
    # Do NOT create the snapshot dir.
    add_marked_staged(tmp_path, SCOPE, [entry])

    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "push_directory_contents_to_container") as push_dir, \
         patch.object(mpd, "push_file_to_container") as push_file:
        res = drain_marked_push(tmp_path, SCOPE, config=cfg)

    assert res.success
    push_dir.assert_not_called()
    push_file.assert_not_called()
    assert load_marked_staged(tmp_path, SCOPE) == set()  # dropped
    assert any("staged snapshot missing" in n for n in res.details)


def test_staged_entry_cp_failure_leaves_queued(tmp_path):
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    entry = _make_staged_dir(tmp_path, "/Projects/foo")
    add_marked_staged(tmp_path, SCOPE, [entry])

    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "push_directory_contents_to_container", return_value=(False, "boom")):
        res = drain_marked_push(tmp_path, SCOPE, config=cfg)

    assert res.success  # per-entry failure is not fatal
    assert load_marked_staged(tmp_path, SCOPE) == {entry}
    assert any("staged restore failed" in n for n in res.details)


def test_host_drained_before_staged(project, host_file, config):
    """Host queue is processed before staged queue."""
    hm = host_file.stat().st_mtime
    entry = _make_staged_dir(project, "/Projects/foo")
    add_marked_staged(project, SCOPE, [entry])

    order: list[str] = []
    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "exec_in_container", return_value=_mtime_probe(None)), \
         patch.object(
             mpd, "push_file_to_container",
             side_effect=lambda *a, **k: (order.append("host"), (True, "ok"))[1],
         ), \
         patch.object(
             mpd, "push_directory_contents_to_container",
             side_effect=lambda *a, **k: (order.append("staged"), (True, "ok"))[1],
         ):
        drain_marked_push(project, SCOPE, config=config)

    assert order == ["host", "staged"]


def test_missing_container_message_counts_both_queues(project, host_file, config):
    entry = _make_staged_dir(project, "/Projects/foo")
    add_marked_staged(project, SCOPE, [entry])

    with patch.object(mpd, "get_container_info", return_value=None):
        res = drain_marked_push(project, SCOPE, config=config)

    assert res.success
    assert "2 file(s) still queued" in res.message
    # Neither queue was touched.
    assert load_marked_push(project, SCOPE) == {host_file}
    assert load_marked_staged(project, SCOPE) == {entry}


def test_progress_covers_host_plus_staged_total(project, host_file, config):
    entry = _make_staged_dir(project, "/Projects/foo")
    add_marked_staged(project, SCOPE, [entry])
    calls: list[tuple[int, int]] = []

    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "exec_in_container", return_value=_mtime_probe(None)), \
         patch.object(mpd, "push_file_to_container", return_value=(True, "ok")), \
         patch.object(mpd, "push_directory_contents_to_container", return_value=(True, "ok")):
        drain_marked_push(
            project, SCOPE, config=config, progress=lambda i, t: calls.append((i, t)),
        )

    assert calls == [(1, 2), (2, 2)]


# ---------------------------------------------------------------------------
# drain_with_user_feedback wrapper — cleanup-always-runs contract.
# ---------------------------------------------------------------------------
# The wrapper is the canonical drain entry-point. Its only added value over
# the engine is (1) the on_stale_cb / progress_cb kwarg names and (2) running
# cleanup_consumed_snapshots after the drain returns. These tests pin the
# cleanup contract specifically — flipping it back to orchestrator-only would
# break the CLI / GUI drain paths that rely on it.

def test_wrapper_runs_cleanup_on_normal_drain(project, host_file, config):
    """Successful drain → cleanup runs once."""
    with patch.object(mpd, "get_container_info", return_value=_running_info()), \
         patch.object(mpd, "ensure_container_running", return_value=(True, "running")), \
         patch.object(mpd, "exec_in_container", return_value=_mtime_probe(None)), \
         patch.object(mpd, "push_file_to_container", return_value=(True, "ok")), \
         patch.object(mpd, "cleanup_consumed_snapshots") as cleanup:
        drain_with_user_feedback(project, SCOPE, config=config, on_stale_cb="replace")

    cleanup.assert_called_once_with(project, SCOPE)


def test_wrapper_runs_cleanup_on_empty_queue_early_return(tmp_path):
    """Empty-queue early-return path also triggers cleanup — the GUI/CLI paths
    must clean snapshots even when both queues happen to be empty (the user
    may have manually drained then run push-marked).
    """
    fresh_config = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    with patch.object(mpd, "cleanup_consumed_snapshots") as cleanup:
        result = drain_with_user_feedback(tmp_path, SCOPE, config=fresh_config)

    assert result.success
    assert "No files queued" in result.message
    cleanup.assert_called_once_with(tmp_path, SCOPE)


def test_wrapper_runs_cleanup_on_container_not_running_failure(project, config):
    """Even when the underlying drain fails (container won't start), cleanup
    still runs — it's best-effort and only deletes consumed entries, so
    running it on a failed drain is a no-op rather than a regression.
    """
    with patch.object(mpd, "get_container_info", return_value={"running": False, "exists": True}), \
         patch.object(mpd, "ensure_container_running", return_value=(False, "won't start")), \
         patch.object(mpd, "cleanup_consumed_snapshots") as cleanup:
        result = drain_with_user_feedback(project, SCOPE, config=config)

    assert not result.success
    cleanup.assert_called_once_with(project, SCOPE)


def test_wrapper_returns_engine_opresult_verbatim(project, host_file, config):
    """The wrapper does not transform the engine's OpResult — same success
    flag, same message, same details. Cleanup runs as a side effect only.
    """
    expected = OpResult(success=True, message="Drained 7 file(s)", details=["note"])
    with patch.object(mpd, "drain_marked_push", return_value=expected), \
         patch.object(mpd, "cleanup_consumed_snapshots"):
        result = drain_with_user_feedback(project, SCOPE, config=config)

    assert result is expected
