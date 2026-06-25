"""Tests for the `exec` and `running` CLI subcommands.

Covers:
- cmd_exec (thin wrapper over canonical exec_in_container)
- cmd_exec_wrapper (positional scope, `--` separator, exit-code matrix,
  stdout/stderr forwarding)
- cmd_running (running-state dict)
- cmd_running_wrapper (positional scope, --json, exit-code matrix)

All Docker calls are mocked — no live container is required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# cmd_exec — thin wrapper over exec_in_container
# ---------------------------------------------------------------------------
class TestCmdExec:
    def test_forwards_success(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_exec

        with patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(True, "out", ""),
        ) as mock_exec:
            ok, stdout, stderr = cmd_exec(tmp_path, "dev", ["echo", "hi"])

        assert (ok, stdout, stderr) == (True, "out", "")
        # docker_name derived from scope is forwarded as first positional arg.
        called_name, called_cmd = mock_exec.call_args[0]
        assert called_cmd == ["echo", "hi"]
        assert isinstance(called_name, str) and called_name

    def test_forwards_failure(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_exec

        with patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(False, "", "boom"),
        ):
            ok, stdout, stderr = cmd_exec(tmp_path, "dev", ["false"])

        assert (ok, stdout, stderr) == (False, "", "boom")


# ---------------------------------------------------------------------------
# cmd_exec_wrapper — exit-code matrix + output forwarding
# ---------------------------------------------------------------------------
class TestCmdExecWrapper:
    def _argv(self, *rest: str) -> list[str]:
        # argv-style: [prog, "exec", *rest]
        return ["prog", "exec", *rest]

    def test_ok_exits_0_and_forwards_stdout(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("dev", "--", "echo", "hi")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.get_container_info",
            return_value={"running": True, "status": "running"},
        ), patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(True, "hello-out", ""),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "hello-out" in captured.out

    def test_cmd_failed_exits_1_and_forwards_stderr(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("dev", "--", "false")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.get_container_info",
            return_value={"running": True, "status": "running"},
        ), patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(False, "", "err-text"),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "err-text" in captured.err

    def test_no_separator_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("dev", "echo", "hi")  # no `--`
        with pytest.raises(SystemExit) as exc:
            cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "Usage" in capsys.readouterr().err

    def test_empty_command_after_separator_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("dev", "--")  # nothing after `--`
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 2

    def test_missing_scope_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("--", "echo", "hi")  # no positional scope
        with pytest.raises(SystemExit) as exc:
            cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 2

    def test_no_such_scope_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("ghost", "--", "ls")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "no such scope: ghost" in capsys.readouterr().err

    def test_not_running_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("dev", "--", "ls")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.get_container_info",
            return_value={"running": False, "status": "exited"},
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "container not running" in capsys.readouterr().err

    def test_not_created_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_exec_wrapper

        argv = self._argv("dev", "--", "ls")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.get_container_info", return_value=None
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_exec_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "container not running" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_running — running-state dict
# ---------------------------------------------------------------------------
class TestCmdRunning:
    def test_running_container(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_running

        with patch(
            "IgnoreScope.cli.commands.get_container_info",
            return_value={"running": True, "status": "running"},
        ):
            result = cmd_running(tmp_path, "dev")

        assert result["scope"] == "dev"
        assert result["exists"] is True
        assert result["running"] is True
        assert result["status"] == "running"
        assert isinstance(result["docker_name"], str) and result["docker_name"]

    def test_stopped_container(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_running

        with patch(
            "IgnoreScope.cli.commands.get_container_info",
            return_value={"running": False, "status": "exited"},
        ):
            result = cmd_running(tmp_path, "dev")

        assert result["exists"] is True
        assert result["running"] is False
        assert result["status"] == "exited"

    def test_absent_container(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_running

        with patch(
            "IgnoreScope.cli.commands.get_container_info", return_value=None
        ):
            result = cmd_running(tmp_path, "dev")

        assert result["exists"] is False
        assert result["running"] is False
        assert result["status"] == "absent"


# ---------------------------------------------------------------------------
# cmd_running_wrapper — exit-code matrix + --json
# ---------------------------------------------------------------------------
class TestCmdRunningWrapper:
    def _argv(self, *rest: str) -> list[str]:
        return ["prog", "running", *rest]

    def test_running_exits_0_human(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_running_wrapper

        argv = self._argv("dev")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.commands.get_container_info",
            return_value={"running": True, "status": "running"},
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_running_wrapper(tmp_path, argv)

        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "running" in out

    def test_stopped_exits_1_human(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_running_wrapper

        argv = self._argv("dev")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.commands.get_container_info",
            return_value={"running": False, "status": "exited"},
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_running_wrapper(tmp_path, argv)

        assert exc.value.code == 1
        assert "stopped" in capsys.readouterr().out

    def test_absent_exits_1_human(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_running_wrapper

        argv = self._argv("dev")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.commands.get_container_info", return_value=None
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_running_wrapper(tmp_path, argv)

        assert exc.value.code == 1
        assert "not created" in capsys.readouterr().out

    def test_json_running_valid_payload(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_running_wrapper

        argv = self._argv("dev", "--json")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.commands.get_container_info",
            return_value={"running": True, "status": "running"},
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_running_wrapper(tmp_path, argv)

        assert exc.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["scope"] == "dev"
        assert payload["exists"] is True
        assert payload["running"] is True
        assert payload["status"] == "running"
        assert "docker_name" in payload

    def test_no_such_scope_exits_2_human(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_running_wrapper

        argv = self._argv("ghost")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_running_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "no such scope: ghost" in capsys.readouterr().err

    def test_no_such_scope_exits_2_json(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_running_wrapper

        argv = self._argv("ghost", "--json")
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_running_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["scope"] == "ghost"
        assert payload["exists"] is False
        assert payload["running"] is False
        assert payload["status"] == "no-such-scope"

    def test_missing_scope_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_running_wrapper

        argv = self._argv()  # no positional scope
        with pytest.raises(SystemExit) as exc:
            cmd_running_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "Usage" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() dispatch — `exec` / `running` route to their wrappers
# ---------------------------------------------------------------------------
class TestMainDispatch:
    """Regression-guard the __main__.py if-elif routing for the new verbs.

    Patches the wrapper (a no-op MagicMock that never sys.exit's) so main()
    returns normally; asserts the command token routes to the right wrapper
    and forwards sys.argv.
    """

    def test_exec_routes_to_wrapper(self, monkeypatch):
        from IgnoreScope.__main__ import main

        monkeypatch.setattr(sys, "argv", ["prog", "exec", "dev", "--", "ls"])
        with patch("IgnoreScope.__main__.cmd_exec_wrapper") as mock_wrapper:
            main()

        mock_wrapper.assert_called_once()
        # called as cmd_exec_wrapper(host_project_root, sys.argv)
        assert mock_wrapper.call_args[0][1] == ["prog", "exec", "dev", "--", "ls"]

    def test_running_routes_to_wrapper(self, monkeypatch):
        from IgnoreScope.__main__ import main

        monkeypatch.setattr(sys, "argv", ["prog", "running", "dev", "--json"])
        with patch("IgnoreScope.__main__.cmd_running_wrapper") as mock_wrapper:
            main()

        mock_wrapper.assert_called_once()
        assert mock_wrapper.call_args[0][1] == ["prog", "running", "dev", "--json"]
