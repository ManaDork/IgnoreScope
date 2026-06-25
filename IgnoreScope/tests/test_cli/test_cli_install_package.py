"""Tests for the `install-package` CLI subcommand.

Covers:
- _load_package_manifest (JSON load + schema validation → ValueError)
- cmd_install_package (thin install-loop + optional verify over exec_in_container)
- cmd_install_package_wrapper (positional scope + manifest path, ensure flow,
  exit-code matrix, stdout/stderr routing)
- main() dispatch routing `install-package` → its wrapper

All Docker calls are mocked — no live container is required. Manifest files
are written to tmp_path so the validator exercises real file I/O.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _write_manifest(tmp_path: Path, data, *, name: str = "m.json") -> Path:
    """Write `data` to a JSON manifest file under tmp_path; return its path.

    `data` may be a dict (json-dumped) or a raw string (written verbatim —
    used to exercise the invalid-JSON path).
    """
    path = tmp_path / name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data), encoding="utf-8")
    return path


_VALID_MANIFEST = {
    "name": "uv",
    "install": [["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]],
    "verify": ["uv", "--version"],
}


# ---------------------------------------------------------------------------
# _load_package_manifest — schema validation
# ---------------------------------------------------------------------------
class TestLoadPackageManifest:
    def test_valid_parse(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, _VALID_MANIFEST)
        manifest = _load_package_manifest(path)

        assert manifest["name"] == "uv"
        assert manifest["install"] == [
            ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
        ]
        assert manifest["verify"] == ["uv", "--version"]

    def test_valid_without_verify(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        data = {"name": "uv", "install": [["echo", "hi"]]}
        path = _write_manifest(tmp_path, data)
        manifest = _load_package_manifest(path)

        assert "verify" not in manifest

    def test_missing_file_raises_filenotfound(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        with pytest.raises(FileNotFoundError):
            _load_package_manifest(tmp_path / "absent.json")

    def test_invalid_json_raises_valueerror(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, "{not valid json")
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_missing_name_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, {"install": [["echo", "hi"]]})
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_empty_name_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, {"name": "", "install": [["echo", "hi"]]})
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_missing_install_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, {"name": "uv"})
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_empty_install_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, {"name": "uv", "install": []})
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_install_not_list_of_lists_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        # install is a list of strings, not a list of lists.
        path = _write_manifest(tmp_path, {"name": "uv", "install": ["echo hi"]})
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_install_step_empty_list_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, {"name": "uv", "install": [[]]})
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_install_step_non_string_token_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        path = _write_manifest(tmp_path, {"name": "uv", "install": [["echo", 7]]})
        with pytest.raises(ValueError):
            _load_package_manifest(path)

    def test_verify_wrong_type_raises(self, tmp_path: Path):
        from IgnoreScope.cli.interactive import _load_package_manifest

        data = {"name": "uv", "install": [["echo", "hi"]], "verify": "uv --version"}
        path = _write_manifest(tmp_path, data)
        with pytest.raises(ValueError):
            _load_package_manifest(path)


# ---------------------------------------------------------------------------
# cmd_install_package — thin install-loop + verify
# ---------------------------------------------------------------------------
class TestCmdInstallPackage:
    def test_all_install_ok_and_verify_ok(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_install_package

        manifest = {
            "name": "uv",
            "install": [["a"], ["b"]],
            "verify": ["uv", "--version"],
        }
        with patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(True, "uv 0.1.0", ""),
        ) as mock_exec:
            ok, msg = cmd_install_package(tmp_path, "dev", manifest)

        assert ok is True
        assert "uv" in msg
        assert "uv 0.1.0" in msg  # verify stdout folded into success message
        # 2 install cmds + 1 verify = 3 calls.
        assert mock_exec.call_count == 3

    def test_no_verify_key_succeeds_after_install(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_install_package

        manifest = {"name": "tool", "install": [["a"], ["b"]]}
        with patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(True, "", ""),
        ) as mock_exec:
            ok, msg = cmd_install_package(tmp_path, "dev", manifest)

        assert ok is True
        assert "tool" in msg
        # 2 install cmds, no verify call.
        assert mock_exec.call_count == 2

    def test_install_step_fails(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_install_package

        manifest = {"name": "uv", "install": [["a"], ["b"]]}
        with patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(False, "", "curl: not found"),
        ) as mock_exec:
            ok, msg = cmd_install_package(tmp_path, "dev", manifest)

        assert ok is False
        assert "install step failed" in msg
        assert "curl: not found" in msg
        # Stops at first failing install step.
        assert mock_exec.call_count == 1

    def test_verify_fails(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_install_package

        manifest = {
            "name": "uv",
            "install": [["a"]],
            "verify": ["uv", "--version"],
        }

        # First call (install) ok; second call (verify) fails.
        outcomes = [(True, "", ""), (False, "", "command not found")]

        with patch(
            "IgnoreScope.cli.commands.exec_in_container",
            side_effect=outcomes,
        ) as mock_exec:
            ok, msg = cmd_install_package(tmp_path, "dev", manifest)

        assert ok is False
        assert "verify failed" in msg
        assert "command not found" in msg
        assert mock_exec.call_count == 2

    def test_exec_called_once_per_install_cmd_plus_verify(self, tmp_path: Path):
        from IgnoreScope.cli.commands import cmd_install_package

        manifest = {
            "name": "uv",
            "install": [["x"], ["y"], ["z"]],
            "verify": ["v"],
        }
        with patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(True, "ok", ""),
        ) as mock_exec:
            cmd_install_package(tmp_path, "dev", manifest)

        # 3 install + 1 verify = 4.
        assert mock_exec.call_count == 4
        forwarded_cmds = [call.args[1] for call in mock_exec.call_args_list]
        assert forwarded_cmds == [["x"], ["y"], ["z"], ["v"]]


# ---------------------------------------------------------------------------
# cmd_install_package_wrapper — exit-code matrix + output routing
# ---------------------------------------------------------------------------
class TestCmdInstallPackageWrapper:
    def _argv(self, *rest: str) -> list[str]:
        return ["prog", "install-package", *rest]

    def test_happy_exits_0_stdout_has_name(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        path = _write_manifest(tmp_path, _VALID_MANIFEST)
        argv = self._argv("dev", str(path))
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.ensure_container_running",
            return_value=(True, "running"),
        ), patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(True, "uv 0.1.0", ""),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 0
        assert "uv" in capsys.readouterr().out

    def test_install_fail_exits_1_stderr(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        path = _write_manifest(tmp_path, _VALID_MANIFEST)
        argv = self._argv("dev", str(path))
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.ensure_container_running",
            return_value=(True, "running"),
        ), patch(
            "IgnoreScope.cli.commands.exec_in_container",
            return_value=(False, "", "boom"),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "install step failed" in captured.err

    def test_verify_fail_exits_1_stderr(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        path = _write_manifest(tmp_path, _VALID_MANIFEST)
        argv = self._argv("dev", str(path))
        outcomes = [(True, "", ""), (False, "", "no such binary")]
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.ensure_container_running",
            return_value=(True, "running"),
        ), patch(
            "IgnoreScope.cli.commands.exec_in_container",
            side_effect=outcomes,
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 1
        assert "verify failed" in capsys.readouterr().err

    def test_missing_args_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        # Only scope, no manifest path.
        argv = self._argv("dev")
        with pytest.raises(SystemExit) as exc:
            cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "Usage" in capsys.readouterr().err

    def test_no_such_scope_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        path = _write_manifest(tmp_path, _VALID_MANIFEST)
        argv = self._argv("ghost", str(path))
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "no such scope: ghost" in capsys.readouterr().err

    def test_manifest_file_missing_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        argv = self._argv("dev", str(tmp_path / "absent.json"))
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert capsys.readouterr().err.strip()  # a clear message went to stderr

    def test_invalid_json_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        path = _write_manifest(tmp_path, "{nope")
        argv = self._argv("dev", str(path))
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert capsys.readouterr().err.strip()

    def test_bad_schema_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        # Missing 'install'.
        path = _write_manifest(tmp_path, {"name": "uv"})
        argv = self._argv("dev", str(path))
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert capsys.readouterr().err.strip()

    def test_ensure_fails_exits_2(self, tmp_path: Path, capsys):
        from IgnoreScope.cli.interactive import cmd_install_package_wrapper

        path = _write_manifest(tmp_path, _VALID_MANIFEST)
        argv = self._argv("dev", str(path))
        with patch(
            "IgnoreScope.cli.interactive.list_containers", return_value=["dev"]
        ), patch(
            "IgnoreScope.cli.interactive.ensure_container_running",
            return_value=(False, "Container not found: x"),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_install_package_wrapper(tmp_path, argv)

        assert exc.value.code == 2
        assert "container not available" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() dispatch — `install-package` routes to its wrapper
# ---------------------------------------------------------------------------
class TestMainDispatch:
    def test_install_package_routes_to_wrapper(self, monkeypatch):
        from IgnoreScope.__main__ import main

        monkeypatch.setattr(
            sys, "argv", ["prog", "install-package", "dev", "m.json"]
        )
        with patch("IgnoreScope.__main__.cmd_install_package_wrapper") as mock_wrapper:
            main()

        mock_wrapper.assert_called_once()
        # called as cmd_install_package_wrapper(host_project_root, sys.argv)
        assert mock_wrapper.call_args[0][1] == [
            "prog",
            "install-package",
            "dev",
            "m.json",
        ]
