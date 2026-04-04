"""Unit tests for scripts/container_probe.py probe_volume_masks().

Tests the three container location conditions using tmp_path mock filesystem:
  1. Virtual mkdir (mirrored) — empty directory, simulates mask volume
  2. Hybrid mounted (bind mount) — visible content, mask not applied
  3. Volume location (revealed) — visible content inside masked area

Single source of truth: scripts/container_probe.py
Integration tests (real Docker containers) are in test_docker/test_integration.py
and gated behind @pytest.mark.docker.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Import probe_volume_masks from scripts/ (single source of truth)
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from container_probe import probe_volume_masks


@pytest.fixture
def mock_container(tmp_path):
    """Simulate container filesystem with three location conditions.

    Structure:
        workspace/
            .ignore_scope/default/scope_docker_desktop.json
            Intermediate/Masked/              (Condition 1: empty — mirrored mkdir)
            Content/Cache/                    (Condition 2: visible — mask leak)
                file1.bin
                file2.bin
                Keep/                         (Condition 3: revealed — visible)
                    important.txt
    """
    mount_root = tmp_path / "workspace"
    mount_root.mkdir()

    # Write IgnoreScope config
    scope_dir = mount_root / ".ignore_scope" / "default"
    scope_dir.mkdir(parents=True)
    config = {
        "version": "0.2.0",
        "scope_name": "default",
        "local": {
            "mount_specs": [
                {
                    "mount_root": ".",
                    "patterns": [
                        "Intermediate/Masked/",
                        "Content/Cache/",
                        "!Content/Cache/Keep/",
                    ],
                }
            ],
        },
    }
    (scope_dir / "scope_docker_desktop.json").write_text(
        json.dumps(config, indent=2)
    )

    # Condition 1: Virtual mkdir (mirrored) — empty directory
    (mount_root / "Intermediate" / "Masked").mkdir(parents=True)

    # Condition 2: Hybrid mounted — visible content (mask NOT enforced)
    cache = mount_root / "Content" / "Cache"
    cache.mkdir(parents=True)
    (cache / "file1.bin").write_bytes(b"leaked content")
    (cache / "file2.bin").write_bytes(b"more leaked content")

    # Condition 3: Revealed inside masked — has entries (punch-through working)
    keep = cache / "Keep"
    keep.mkdir()
    (keep / "important.txt").write_text("visible")

    return mount_root


class TestProbeVolumeMasks:
    """Test probe_volume_masks() against mock container filesystem."""

    def test_auto_discovers_config(self, mock_container):
        """Probe finds scope_docker_desktop.json via .ignore_scope/ auto-discovery."""
        result = probe_volume_masks(mount_point=str(mock_container))
        assert result["config_path"] is not None
        assert "scope_docker_desktop.json" in result["config_path"]
        assert result["scope_name"] == "default"
        assert result["scope_version"] == "0.2.0"

    def test_masked_empty_dir_passes(self, mock_container):
        """Condition 1: Empty directory (mirrored mkdir) correctly detected as masked."""
        result = probe_volume_masks(mount_point=str(mock_container))
        checks = {c["path"]: c for c in result["checks"]}

        masked_check = checks["Intermediate/Masked"]
        assert masked_check["expected"] == "masked"
        assert masked_check["actual"] == "empty_directory"
        assert masked_check["pass"] is True

    def test_masked_visible_content_fails(self, mock_container):
        """Condition 2: Visible content in masked path detected as leak."""
        result = probe_volume_masks(mount_point=str(mock_container))
        checks = {c["path"]: c for c in result["checks"]}

        cache_check = checks["Content/Cache"]
        assert cache_check["expected"] == "masked"
        assert cache_check["actual"] == "fully_visible"
        assert cache_check["pass"] is False
        assert cache_check["file_count"] > 0

    def test_revealed_visible_passes(self, mock_container):
        """Condition 3: Visible content in revealed path is correct."""
        result = probe_volume_masks(mount_point=str(mock_container))
        checks = {c["path"]: c for c in result["checks"]}

        keep_check = checks["Content/Cache/Keep"]
        assert keep_check["expected"] == "revealed"
        assert keep_check["actual"] == "visible"
        assert keep_check["pass"] is True
        assert keep_check["entry_count"] > 0

    def test_summary_counts(self, mock_container):
        """Summary correctly reports pass/fail totals."""
        result = probe_volume_masks(mount_point=str(mock_container))
        summary = result["summary"]

        assert summary["total"] == 3  # 2 masked + 1 revealed
        assert summary["passed"] == 2  # empty dir + revealed visible
        assert summary["failed"] == 1  # cache leak
        assert summary["all_enforced"] is False

    def test_no_config_returns_error(self, tmp_path):
        """Missing config returns error, not crash."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = probe_volume_masks(mount_point=str(empty_dir))
        assert "error" in result

    def test_explicit_config_path(self, mock_container):
        """Can specify config path directly instead of auto-discovery."""
        config_path = str(
            mock_container / ".ignore_scope" / "default" / "scope_docker_desktop.json"
        )
        result = probe_volume_masks(
            scope_config=config_path,
            mount_point=str(mock_container),
        )
        assert result["config_path"] == config_path
        assert result["summary"]["total"] == 3
