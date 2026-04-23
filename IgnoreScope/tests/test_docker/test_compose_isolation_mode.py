"""Compose generation: project-content vs L4-only shapes.

Structural assertions verifying that generate_compose_with_masks:
  - Preserves the full structure when project-content volumes are provided.
  - Omits project-content volumes when caller passes empty project lists
    (the shape produced by an all-detached scope).
  - Emits extension-synthesized L_volume entries (formerly "L4 + auth" —
    unified into the vol_* tier in Phase 1 Tasks 1.3-1.7).

compose.py is a pure formatter — it emits whatever lists it's given.
"""

from __future__ import annotations

from pathlib import Path

from IgnoreScope.core.hierarchy import compute_container_hierarchy
from IgnoreScope.core.local_mount_config import ExtensionConfig
from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.docker.compose import generate_compose_with_masks


def _make_mount_specs(
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
) -> list[MountSpecPath]:
    specs = []
    for mount_root in sorted(mounts or set()):
        patterns = []
        for m in sorted(masked or set()):
            try:
                rel = str(m.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"{rel}/")
            except ValueError:
                pass
        for r in sorted(revealed or set()):
            try:
                rel = str(r.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"!{rel}/")
            except ValueError:
                pass
        specs.append(MountSpecPath(mount_root=mount_root, patterns=patterns))
    return specs


def _rich_hierarchy(tmp_path: Path):
    """Fixture hierarchy with L1 mount + L2 mask + L3 reveal + L_volume tier entry.

    Post-Task-1.3, extension isolation paths flow through the unified-synth
    pipeline; L4 output surfaces on ``volume_entries`` / ``volume_names``
    (renamed from ``stencil_volume_*`` in Task 1.6) under the
    ``vol_{owner_segment}_{path}`` naming scheme introduced in Task 1.4.
    """
    src = tmp_path / "src"
    api = src / "api"
    public = api / "public"
    return compute_container_hierarchy(
        container_root="/workspace",
        mount_specs=_make_mount_specs({src}, {api}, {public}),
        pushed_files=set(),
        host_project_root=tmp_path,
        host_container_root=tmp_path,
        extensions=[ExtensionConfig(name="Claude Code", isolation_paths=["/root/.local"])],
    )


def _volumes_section(compose: str) -> str:
    lines = compose.split("\n")
    idx = next(i for i, l in enumerate(lines) if l.startswith("volumes:"))
    return "\n".join(lines[idx:])


# =============================================================================
# Hybrid mode — structure preserved
# =============================================================================

class TestHybridMode:
    """Hybrid mode emits all project-content volumes + L4."""

    def test_hybrid_preserves_volume_structure(self, tmp_path: Path):
        hierarchy = _rich_hierarchy(tmp_path)

        compose = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=tmp_path,
            docker_container_name="test-hybrid",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=hierarchy.volume_entries,
            volume_names=hierarchy.volume_names,
            ports=["3900:3900"],
        )

        # Volume layers block present
        assert "# === Volume layers" in compose
        # L1 bind mount for the src root
        assert "/workspace/src" in compose
        # L2 mask volume mount + declaration
        assert "mask_" in compose
        volumes_section = _volumes_section(compose)
        assert any(l.strip().startswith("mask_") for l in volumes_section.split("\n"))
        # L_volume tier entry (extension-synthesized) mount + declaration
        assert "vol_" in compose
        assert any(l.strip().startswith("vol_") for l in volumes_section.split("\n"))
        # Container config preserved
        assert "working_dir:" in compose
        assert "stdin_open: true" in compose
        assert "tty: true" in compose
        # Ports preserved
        assert '"3900:3900"' in compose


# =============================================================================
# Isolation mode — project content omitted, L_volume preserved
# =============================================================================

class TestIsolationMode:
    """Isolation mode (caller passes empty project lists) strips project content."""

    def test_isolation_omits_project_content_volumes(self, tmp_path: Path):
        hierarchy = _rich_hierarchy(tmp_path)

        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-isolation",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=hierarchy.volume_entries,
            volume_names=hierarchy.volume_names,
            ports=["3900:3900"],
        )

        # No L1 bind mount for project content
        assert "/workspace/src" not in compose
        # No L2 mask volumes anywhere
        assert "mask_" not in compose
        # L_volume tier entry (extension-synthesized) mount + declaration still present
        vol_name = hierarchy.volume_names[0]
        assert f"{vol_name}:/root/.local" in compose
        volumes_section = _volumes_section(compose)
        assert any(l.strip().startswith("vol_") for l in volumes_section.split("\n"))
        # Container config preserved
        assert "working_dir:" in compose
        assert "stdin_open: true" in compose
        assert "tty: true" in compose
        # Ports preserved
        assert '"3900:3900"' in compose

    def test_isolation_with_no_l4_emits_no_volume_layers_block(self, tmp_path: Path):
        """No L1-L3 (caller passed []) and no L_volume → skip the volume layers block."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-bare",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=[],
            volume_names=[],
        )

        assert "# === Volume layers" not in compose
        # Post-Task-1.7 the standalone `{name}-claude-auth` volume is gone —
        # the auth path flows through the extension synth pipeline, so an
        # empty-scope/no-extension compose emits no top-level volumes block
        # at all.
        assert "-claude-auth" not in compose
        assert "\nvolumes:\n" not in compose

    def test_isolation_with_only_l4(self, tmp_path: Path):
        """Empty project lists + one L4 → L4 emits; no mask_* anywhere."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-l4-only",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=["vol_claude_code_root_.local:/root/.local"],
            volume_names=["vol_claude_code_root_.local"],
        )

        assert "vol_claude_code_root_.local:/root/.local" in compose
        assert "# === Volume layers" in compose
        assert "mask_" not in compose


# =============================================================================
# Stencil volume mode — delivery="volume" specs (Task 4.4)
# =============================================================================

class TestStencilVolumeMode:
    """delivery='volume' specs emit a named volume entry + top-level declaration."""

    def test_stencil_volume_emits_entry_and_declaration(self, tmp_path: Path):
        """Single volume-delivery spec emits both mount entry and volumes decl."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-volume",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=["vol_user_workspace_cache:/workspace/cache"],
            volume_names=["vol_user_workspace_cache"],
        )

        assert "vol_user_workspace_cache:/workspace/cache" in compose
        assert "# === Volume layers" in compose
        volumes_section = _volumes_section(compose)
        assert any(
            l.strip().startswith("vol_user_workspace_cache:")
            for l in volumes_section.split("\n")
        )

    def test_stencil_volume_coexists_with_l1_l2_l4(self, tmp_path: Path):
        """Bind/mask + volume tier (L4 + user-volume) all emit in the same compose file."""
        hierarchy = _rich_hierarchy(tmp_path)

        # Combine the L4 extension-synth volume entries with an explicit
        # user-declared volume-delivery spec. Post-Task-1.3 both live on the
        # ``volume_entries`` output list; compose renders the unified list.
        volume_entries = list(hierarchy.volume_entries) + [
            "vol_user_workspace_data:/workspace/data",
        ]
        volume_names = list(hierarchy.volume_names) + ["vol_user_workspace_data"]

        compose = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=tmp_path,
            docker_container_name="test-mixed",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=volume_entries,
            volume_names=volume_names,
        )

        assert "mask_" in compose
        assert "vol_user_workspace_data:/workspace/data" in compose
        volumes_section = _volumes_section(compose)
        assert any(
            l.strip().startswith("vol_user_workspace_data:")
            for l in volumes_section.split("\n")
        )
        # L4 extension-synthesized entry also renders.
        assert any(":/root/.local" in e for e in volume_entries)
        assert any(":/root/.local" in l for l in compose.split("\n"))

    def test_no_stencil_volumes_omits_nothing_else(self, tmp_path: Path):
        """Volume tier populated only by the L4 extension synth output."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-bare-container",
            container_root="/workspace",
            project_name="plain",
            volume_entries=["vol_claude_code_root_.local:/root/.local"],
            volume_names=["vol_claude_code_root_.local"],
        )

        # Only the single L4-origin volume-tier entry is present.
        assert "vol_claude_code_root_.local:/root/.local" in compose
        volumes_section = _volumes_section(compose)
        volume_lines = [
            l for l in volumes_section.split("\n") if l.strip().startswith("vol_")
        ]
        assert len(volume_lines) == 1
