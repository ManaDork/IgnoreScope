"""Compose generation: project-content vs L4-only shapes.

Structural assertions verifying that generate_compose_with_masks:
  - Preserves the full structure when project-content volumes are provided.
  - Omits project-content volumes when caller passes empty project lists
    (the shape produced by an all-detached scope).
  - Always emits L4 isolation volumes and the auth volume.

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
    """Fixture hierarchy with L1 mount + L2 mask + L3 reveal + L4 stencil isolation.

    Post-Task-1.3, extension isolation paths flow through the unified-synth
    pipeline; L4 output surfaces on ``stencil_volume_entries`` / ``stencil_volume_names``
    under the ``stencil_{idx}_{path}`` naming scheme.
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
            stencil_volume_entries=hierarchy.stencil_volume_entries,
            stencil_volume_names=hierarchy.stencil_volume_names,
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
        # L4 stencil isolation volume mount + declaration (post-Task-1.3)
        assert "stencil_" in compose
        assert any(l.strip().startswith("stencil_") for l in volumes_section.split("\n"))
        # Auth volume preserved
        assert "test-hybrid-claude-auth" in compose
        # Container config preserved
        assert "working_dir:" in compose
        assert "stdin_open: true" in compose
        assert "tty: true" in compose
        # Ports preserved
        assert '"3900:3900"' in compose


# =============================================================================
# Isolation mode — project content omitted, L4 preserved
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
            stencil_volume_entries=hierarchy.stencil_volume_entries,
            stencil_volume_names=hierarchy.stencil_volume_names,
            ports=["3900:3900"],
        )

        # No L1 bind mount for project content
        assert "/workspace/src" not in compose
        # No L2 mask volumes anywhere
        assert "mask_" not in compose
        # L4 stencil isolation volume mount + declaration still present
        sten_name = hierarchy.stencil_volume_names[0]
        assert f"{sten_name}:/root/.local" in compose
        volumes_section = _volumes_section(compose)
        assert any(l.strip().startswith("stencil_") for l in volumes_section.split("\n"))
        # Auth volume preserved
        assert "test-isolation-claude-auth" in compose
        # Container config preserved
        assert "working_dir:" in compose
        assert "stdin_open: true" in compose
        assert "tty: true" in compose
        # Ports preserved
        assert '"3900:3900"' in compose

    def test_isolation_with_no_l4_emits_no_volume_layers_block(self, tmp_path: Path):
        """No L1-L3 (caller passed []) and no L4 → skip the volume layers block."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-bare",
            container_root="/workspace",
            project_name=tmp_path.name,
            stencil_volume_entries=[],
            stencil_volume_names=[],
        )

        assert "# === Volume layers" not in compose
        # Auth volume still present (lives outside the volume layers block)
        assert "test-bare-claude-auth" in compose

    def test_isolation_with_only_l4(self, tmp_path: Path):
        """Empty project lists + one L4 → L4 emits; no mask_* anywhere."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-l4-only",
            container_root="/workspace",
            project_name=tmp_path.name,
            stencil_volume_entries=["stencil_0_root_local:/root/.local"],
            stencil_volume_names=["stencil_0_root_local"],
        )

        assert "stencil_0_root_local:/root/.local" in compose
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
            stencil_volume_entries=["stencil_0_workspace_cache:/workspace/cache"],
            stencil_volume_names=["stencil_0_workspace_cache"],
        )

        assert "stencil_0_workspace_cache:/workspace/cache" in compose
        assert "# === Volume layers" in compose
        volumes_section = _volumes_section(compose)
        assert any(
            l.strip().startswith("stencil_0_workspace_cache:")
            for l in volumes_section.split("\n")
        )

    def test_stencil_volume_coexists_with_l1_l2_l4(self, tmp_path: Path):
        """Bind/mask + stencil (L4 + user-volume) all emit in the same compose file."""
        hierarchy = _rich_hierarchy(tmp_path)

        # Combine the L4 extension-synth stencil entries with an explicit
        # user-declared volume-delivery spec. Post-Task-1.3 both live on the
        # stencil_volume_* output lists; compose renders the unified list.
        stencil_entries = list(hierarchy.stencil_volume_entries) + [
            "stencil_1_workspace_data:/workspace/data",
        ]
        stencil_names = list(hierarchy.stencil_volume_names) + ["stencil_1_workspace_data"]

        compose = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=tmp_path,
            docker_container_name="test-mixed",
            container_root="/workspace",
            project_name=tmp_path.name,
            stencil_volume_entries=stencil_entries,
            stencil_volume_names=stencil_names,
        )

        assert "mask_" in compose
        assert "stencil_1_workspace_data:/workspace/data" in compose
        volumes_section = _volumes_section(compose)
        assert any(
            l.strip().startswith("stencil_1_workspace_data:")
            for l in volumes_section.split("\n")
        )
        # L4 extension stencil entry also renders.
        assert any(":/root/.local" in e for e in stencil_entries)
        assert any(":/root/.local" in l for l in compose.split("\n"))

    def test_no_stencil_volumes_omits_nothing_else(self, tmp_path: Path):
        """Stencil tier populated only by the L4 extension synth output."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-bare-container",
            container_root="/workspace",
            project_name="plain",
            stencil_volume_entries=["stencil_0_root_local:/root/.local"],
            stencil_volume_names=["stencil_0_root_local"],
        )

        # Only the single L4-origin stencil volume is present.
        assert "stencil_0_root_local:/root/.local" in compose
        volumes_section = _volumes_section(compose)
        stencil_lines = [
            l for l in volumes_section.split("\n") if l.strip().startswith("stencil_")
        ]
        assert len(stencil_lines) == 1
