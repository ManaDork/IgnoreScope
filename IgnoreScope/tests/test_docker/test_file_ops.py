"""Tests for host-side file operation helpers (docker/file_ops.py).

Verifies resolve_file_subset() and resolve_pull_output() behavior.
No Docker required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScopeDocker.docker.file_ops import resolve_file_subset, resolve_pull_output


class TestResolvePushFiles:
    """Tests for resolve_file_subset()."""

    def test_no_filter_returns_all(self, tmp_path: Path):
        """Without specific_files, returns all pushed files."""
        files = {tmp_path / "a.py", tmp_path / "b.py"}
        result = resolve_file_subset(files, tmp_path)
        assert result == files

    def test_filter_to_subset(self, tmp_path: Path):
        """With specific_files, returns only matching files."""
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        c = tmp_path / "c.py"
        files = {a, b, c}
        result = resolve_file_subset(files, tmp_path, ["a.py", "c.py"])
        assert result == {a, c}

    def test_filter_no_matches(self, tmp_path: Path):
        """Filter with no matches returns empty set."""
        files = {tmp_path / "a.py"}
        result = resolve_file_subset(files, tmp_path, ["nonexistent.py"])
        assert result == set()

    def test_empty_pushed_files(self, tmp_path: Path):
        """Empty pushed files returns empty regardless of filter."""
        result = resolve_file_subset(set(), tmp_path, ["a.py"])
        assert result == set()


class TestResolvePullOutput:
    """Tests for resolve_pull_output()."""

    def test_dev_mode_with_timestamp(self, tmp_path: Path):
        """Dev mode returns Pulled/{timestamp}/{rel_path}."""
        result = resolve_pull_output(
            tmp_path, Path("src/config.json"), dev_mode=True, timestamp="20260101_120000"
        )
        assert result == tmp_path / "Pulled" / "20260101_120000" / "src" / "config.json"

    def test_dev_mode_auto_timestamp(self, tmp_path: Path):
        """Dev mode without explicit timestamp generates one."""
        result = resolve_pull_output(tmp_path, Path("file.txt"), dev_mode=True)
        # Should be under Pulled/ with some timestamp
        assert "Pulled" in str(result)
        assert result.name == "file.txt"

    def test_production_mode(self, tmp_path: Path):
        """Production mode returns host_project_root / rel_path."""
        result = resolve_pull_output(
            tmp_path, Path("src/config.json"), dev_mode=False
        )
        assert result == tmp_path / "src" / "config.json"

    def test_nested_rel_path(self, tmp_path: Path):
        """Deeply nested relative paths preserved in both modes."""
        rel = Path("a/b/c/deep.txt")

        dev_result = resolve_pull_output(tmp_path, rel, dev_mode=True, timestamp="T")
        assert dev_result == tmp_path / "Pulled" / "T" / "a" / "b" / "c" / "deep.txt"

        prod_result = resolve_pull_output(tmp_path, rel, dev_mode=False)
        assert prod_result == tmp_path / "a" / "b" / "c" / "deep.txt"
