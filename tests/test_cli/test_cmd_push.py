"""Tests for the rewritten ``push`` CLI command + the new ``push-marked`` command.

The drain is mocked (no Docker); the marked-push queue and the scope config are
real files under tmp_path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from IgnoreScope.cli.commands import cmd_push, cmd_push_marked
from IgnoreScope.core.config import ScopeDockerConfig, save_config
from IgnoreScope.core.marked_push import load_marked_push
from IgnoreScope.core.op_result import OpResult

SCOPE = "dev"


@pytest.fixture
def project(tmp_path):
    """Project root with a saved scope config and one real host file."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("x", encoding="utf-8")
    save_config(ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE))
    return tmp_path


def _ok_drain(*a, **kw):
    return OpResult(success=True, message="Drained 1 file(s)", details=["pushed: a.txt"])


def test_push_file_enqueues_then_drains(project):
    with patch("IgnoreScope.cli.commands.drain_with_user_feedback", side_effect=_ok_drain) as drain:
        ok, msg = cmd_push(project, SCOPE, ["src/a.txt"])
    assert ok
    assert load_marked_push(project, SCOPE) == {project / "src" / "a.txt"}
    drain.assert_called_once()
    assert drain.call_args.kwargs["on_stale_cb"] == "skip"
    assert "Drained 1 file(s)" in msg and "pushed: a.txt" in msg


def test_push_force_uses_replace(project):
    with patch("IgnoreScope.cli.commands.drain_with_user_feedback", side_effect=_ok_drain) as drain:
        cmd_push(project, SCOPE, ["src/a.txt"], force=True)
    assert drain.call_args.kwargs["on_stale_cb"] == "replace"


def test_push_no_args_drains_existing_queue(project):
    with patch("IgnoreScope.cli.commands.drain_with_user_feedback", side_effect=_ok_drain) as drain, \
         patch("IgnoreScope.cli.commands.load_config") as load_cfg, \
         patch("IgnoreScope.cli.commands.add_marked_push") as add:
        ok, msg = cmd_push(project, SCOPE)
    assert ok
    drain.assert_called_once()
    load_cfg.assert_not_called()
    add.assert_not_called()


def test_push_nonexistent_file_errors_without_draining(project):
    with patch("IgnoreScope.cli.commands.drain_with_user_feedback") as drain:
        ok, msg = cmd_push(project, SCOPE, ["src/nope.txt"])
    assert not ok
    assert "not found" in msg
    drain.assert_not_called()
    assert load_marked_push(project, SCOPE) == set()


def test_push_absolute_path_outside_container_root_errors(tmp_path):
    hcr = tmp_path / "hcr"
    hpr = hcr / "proj"
    hpr.mkdir(parents=True)
    save_config(ScopeDockerConfig(host_project_root=hpr, scope_name=SCOPE))
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")

    with patch("IgnoreScope.cli.commands.drain_with_user_feedback") as drain:
        ok, msg = cmd_push(hpr, SCOPE, [str(outside)])
    assert not ok
    assert "not under" in msg
    drain.assert_not_called()


def test_push_marked_drains_with_skip(project):
    with patch("IgnoreScope.cli.commands.drain_with_user_feedback", side_effect=_ok_drain) as drain:
        ok, _ = cmd_push_marked(project, SCOPE)
    assert ok
    assert drain.call_args.kwargs["on_stale_cb"] == "skip"


def test_push_marked_force_uses_replace(project):
    with patch("IgnoreScope.cli.commands.drain_with_user_feedback", side_effect=_ok_drain) as drain:
        cmd_push_marked(project, SCOPE, force=True)
    assert drain.call_args.kwargs["on_stale_cb"] == "replace"


def test_push_propagates_drain_failure(project):
    fail = OpResult(success=False, message="Drained 0 file(s), 1 still queued", details=["cp failed: a.txt — denied"])
    with patch("IgnoreScope.cli.commands.drain_with_user_feedback", return_value=fail):
        ok, msg = cmd_push(project, SCOPE, ["src/a.txt"])
    assert not ok
    assert "still queued" in msg and "cp failed" in msg
