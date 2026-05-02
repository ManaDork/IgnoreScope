"""Compose generation: full-stack vs empty-project-content shapes.

Structural assertions verifying that generate_compose_with_masks:
  - Preserves the full structure when project-content volumes are provided.
  - Omits project-content volumes when caller passes empty project lists
    (the shape produced by an all-detached scope).
  - Emits extension-synthesized entries through the unified L_volume tier
    (former separate Layer 4 emission tier — unified into the vol_* scheme
    in Phase 1 Tasks 1.3-1.7 of unify-l4-reclaim-isolation-term).

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
    pipeline; extension-owned volume tier output surfaces on ``volume_entries``
    / ``volume_names`` (renamed from ``stencil_volume_*`` in Task 1.6) under
    the ``vol_{owner_segment}_{path}`` naming scheme introduced in Task 1.4.
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
# Full-stack compose — all layers present, structure preserved
# =============================================================================

class TestFullStackCompose:
    """Project-content volumes + extension-synthesized volume tier emit together."""

    def test_full_stack_preserves_volume_structure(self, tmp_path: Path):
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
# Empty project content — caller-stripped L1-L3, L_volume tier preserved
# =============================================================================

class TestEmptyProjectContent:
    """Caller passing empty project lists strips L1-L3 but keeps the volume tier."""

    def test_empty_project_omits_project_content_volumes(self, tmp_path: Path):
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

    def test_empty_project_with_no_volume_tier_emits_no_volume_layers_block(self, tmp_path: Path):
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

    def test_empty_project_with_only_volume_tier(self, tmp_path: Path):
        """Empty project lists + one volume-tier entry → emits; no mask_* anywhere."""
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="test-volume-only",
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

    def test_stencil_volume_coexists_with_l1_l2_and_extension_volume(self, tmp_path: Path):
        """Bind/mask + volume tier (extension + user-volume) all emit in the same compose file."""
        hierarchy = _rich_hierarchy(tmp_path)

        # Combine the extension-synthesized volume entries with an explicit
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
        # Extension-synthesized volume-tier entry also renders.
        assert any(":/root/.local" in e for e in volume_entries)
        assert any(":/root/.local" in l for l in compose.split("\n"))

    def test_no_stencil_volumes_omits_nothing_else(self, tmp_path: Path):
        """Volume tier populated only by the extension-synth output."""
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

        # Only the single extension-origin volume-tier entry is present.
        assert "vol_claude_code_root_.local:/root/.local" in compose
        volumes_section = _volumes_section(compose)
        volume_lines = [
            l for l in volumes_section.split("\n") if l.strip().startswith("vol_")
        ]
        assert len(volume_lines) == 1


# =============================================================================
# Retired naming schemes — regression guard (Phase 1 Task 1.13)
# =============================================================================

class TestRetiredNamingAbsent:
    """No emitted compose YAML may contain `iso_*` or `-claude-auth` literals.

    Task 1.4 eliminated ``iso_{ext}_{path}`` naming (now ``vol_*`` only).
    Task 1.7 retired the hard-coded ``{docker_name}-claude-auth`` volume.
    The auth path flows through the unified extension synth pipeline and
    surfaces as ``vol_claude_code_root_.claude``.

    This suite runs the compose formatter over a representative sample of
    scope shapes and asserts neither retired token appears anywhere in the
    output — structure, volume declarations, or mount entries.
    """

    @staticmethod
    def _assert_no_retired_tokens(compose: str) -> None:
        assert "iso_" not in compose, (
            "emitted compose contains retired `iso_*` volume naming"
        )
        assert "-claude-auth" not in compose, (
            "emitted compose contains retired `-claude-auth` volume naming"
        )

    def test_hybrid_scope_has_no_retired_tokens(self, tmp_path: Path):
        hierarchy = _rich_hierarchy(tmp_path)
        compose = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=tmp_path,
            docker_container_name="guard-hybrid",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=hierarchy.volume_entries,
            volume_names=hierarchy.volume_names,
            ports=["3900:3900"],
        )
        self._assert_no_retired_tokens(compose)

    def test_isolation_only_scope_has_no_retired_tokens(self, tmp_path: Path):
        hierarchy = _rich_hierarchy(tmp_path)
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="guard-iso-only",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=hierarchy.volume_entries,
            volume_names=hierarchy.volume_names,
        )
        self._assert_no_retired_tokens(compose)

    def test_bare_scope_has_no_retired_tokens(self, tmp_path: Path):
        compose = generate_compose_with_masks(
            ordered_volumes=[],
            mask_volume_names=[],
            host_project_root=tmp_path,
            docker_container_name="guard-bare",
            container_root="/workspace",
            project_name="plain",
            volume_entries=[],
            volume_names=[],
        )
        self._assert_no_retired_tokens(compose)

    def test_user_volume_plus_claude_ext_has_no_retired_tokens(self, tmp_path: Path):
        """Mixed user-volume + Claude ext isolation paths — post-Task-1.7 both
        routes produce `vol_*`; neither emits `iso_*` or `-claude-auth`."""
        claude_ext = ExtensionConfig(
            name="Claude Code",
            isolation_paths=["/root/.local", "/root/.claude"],
        )
        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path / "src"}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            extensions=[claude_ext],
        )
        volume_entries = list(hierarchy.volume_entries) + [
            "vol_user_workspace_data:/workspace/data",
        ]
        volume_names = list(hierarchy.volume_names) + ["vol_user_workspace_data"]
        compose = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=tmp_path,
            docker_container_name="guard-mixed",
            container_root="/workspace",
            project_name=tmp_path.name,
            volume_entries=volume_entries,
            volume_names=volume_names,
        )
        self._assert_no_retired_tokens(compose)
        assert "vol_claude_code_root_.claude" in compose
        assert "vol_claude_code_root_.local" in compose
