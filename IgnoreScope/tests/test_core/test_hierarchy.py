"""Baseline tests for core/hierarchy.py.

Locks down volume computation behavior BEFORE Tier 2 refactoring (CC-1, CC-5).
Tests here verify:
  - Volume entry ordering (Layer 1 → 2 → 3)
  - Volume entry format strings (path formula output)
  - Mask volume naming convention
  - Visibility computation
  - Validation rules
  - Multi-sibling interaction

These tests should pass both before AND after refactoring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.hierarchy import (
    ContainerHierarchy,
    compute_container_hierarchy,
    compute_mirrored_intermediate_paths,
    _compute_volume_entries,
    _compute_revealed_parents,
    _compute_mirrored_parents,
    _compute_stencil_volumes,
    _derive_stencil_volume_name,
    _validate_hierarchy,
    _walk_mirrored_intermediates,
)
from IgnoreScope.core.config import SiblingMount
from IgnoreScope.core.mount_spec_path import MountSpecPath


def _make_mount_specs(
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
) -> list[MountSpecPath]:
    """Convert old-style flat sets to mount_specs list (test compat helper)."""
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


def _make_sibling(
    host_path: Path,
    container_path: str,
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
    pushed_files: set[Path] | None = None,
) -> SiblingMount:
    """Build SiblingMount from old-style set kwargs (test compat helper)."""
    mount_specs = []
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
        mount_specs.append(MountSpecPath(mount_root=mount_root, patterns=patterns))
    return SiblingMount(
        host_path=host_path,
        container_path=container_path,
        mount_specs=mount_specs,
        pushed_files=pushed_files or set(),
    )


# =============================================================================
# Volume Entry Ordering
# =============================================================================

class TestVolumeEntryOrdering:
    """Verify volume entries follow strict Layer 1 → 2 → 3 order."""

    def test_layers_in_order(self, tmp_path: Path):
        """All three layers appear in correct sequence."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        entries, mask_names, visible, hidden = _compute_volume_entries(
            _make_mount_specs({src}, {api}, {public}),
            "/workspace",
            tmp_path,
        )

        assert len(entries) == 3
        # Layer 1: bind mount (has host path with ':')
        assert ":ro" not in entries[0], f"Layer 1 should be writable bind mount: {entries[0]}"
        # Layer 2: mask volume (named volume, no ':ro')
        assert "mask_" in entries[1], f"Layer 2 should be mask volume: {entries[1]}"
        assert ":ro" not in entries[1]
        # Layer 3: reveal (bind mount)
        assert ":ro" not in entries[2], f"Layer 3 should be writable reveal mount: {entries[2]}"
        assert "public" in entries[2]

    def test_multiple_mounts_sorted(self, tmp_path: Path):
        """Multiple mounts within same layer are sorted alphabetically."""
        alpha = tmp_path / "alpha"
        bravo = tmp_path / "bravo"
        charlie = tmp_path / "charlie"

        entries, *_ = _compute_volume_entries(
            _make_mount_specs({charlie, alpha, bravo}, None, None),
            "/workspace",
            tmp_path,
        )

        assert len(entries) == 3
        assert "alpha" in entries[0]
        assert "bravo" in entries[1]
        assert "charlie" in entries[2]

    def test_multiple_masks_sorted(self, tmp_path: Path):
        """Multiple masks within Layer 2 are sorted."""
        src = tmp_path / "src"
        src_api = src / "api"
        src_vendor = src / "vendor"

        entries, mask_names, *_ = _compute_volume_entries(
            _make_mount_specs({src}, {src_api, src_vendor}, None),
            "/workspace",
            tmp_path,
        )

        assert len(entries) == 3  # 1 mount + 2 masks
        # Masks should be sorted: api before vendor
        assert "api" in entries[1]
        assert "vendor" in entries[2]
        assert len(mask_names) == 2


# =============================================================================
# Volume Entry Format
# =============================================================================

class TestVolumeEntryFormat:
    """Verify exact format of volume entry strings."""

    def test_bind_mount_format(self, tmp_path: Path):
        """Bind mount: {host_posix}:{container_path}"""
        src = tmp_path / "src"

        entries, *_ = _compute_volume_entries(
            _make_mount_specs({src}, None, None),
            "/workspace",
            tmp_path,
        )

        entry = entries[0]
        # host_path:container_path  (but host on Windows has drive letter colon)
        assert not entry.endswith(":ro")
        assert "/workspace/src" in entry

    def test_mask_volume_format(self, tmp_path: Path):
        """Mask volume: mask_{sanitized_name}:{container_path}"""
        src = tmp_path / "src"
        api = src / "api"

        entries, mask_names, *_ = _compute_volume_entries(
            _make_mount_specs({src}, {api}, None),
            "/workspace",
            tmp_path,
        )

        mask_entry = entries[1]
        assert mask_entry.startswith("mask_")
        assert ":/workspace/src/api" in mask_entry
        assert ":ro" not in mask_entry
        assert mask_names == [mask_entry.split(":")[0]]

    def test_reveal_format(self, tmp_path: Path):
        """Reveal: {host_posix}:{container_path}"""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        entries, *_ = _compute_volume_entries(
            _make_mount_specs({src}, {api}, {public}),
            "/workspace",
            tmp_path,
        )

        reveal_entry = entries[2]
        assert not reveal_entry.endswith(":ro")
        assert "/workspace/src/api/public" in reveal_entry

    def test_host_container_root_includes_project(self, tmp_path: Path):
        """With host_container_root=parent, container paths include project dir name."""
        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()
        src = project_dir / "src"

        entries, *_ = _compute_volume_entries(
            _make_mount_specs({src}, None, None),
            "/workspace",
            tmp_path,
        )

        assert "/workspace/MyProject/src" in entries[0]

    def test_custom_container_root(self, tmp_path: Path):
        """Custom container_root replaces /workspace."""
        src = tmp_path / "src"

        entries, *_ = _compute_volume_entries(
            _make_mount_specs({src}, None, None),
            "/myroot",
            tmp_path,
        )

        assert "/myroot/src" in entries[0]
        assert "/workspace" not in entries[0]


# =============================================================================
# Mask Volume Naming
# =============================================================================

class TestMaskVolumeNaming:
    """Verify mask volume name sanitization."""

    def test_simple_name(self, tmp_path: Path):
        """Simple path → mask_name."""
        src = tmp_path / "src"
        api = src / "api"

        _, mask_names, *__ = _compute_volume_entries(
            _make_mount_specs({src}, {api}, None),
            "/workspace",
            tmp_path,
        )

        assert len(mask_names) == 1
        assert mask_names[0].startswith("mask_")
        # Should contain sanitized form of "src/api" → "src_api"
        assert "src_api" in mask_names[0]

    def test_nested_path_name(self, tmp_path: Path):
        """Nested path slashes become underscores in volume name."""
        src = tmp_path / "src"
        deep = src / "api" / "internal" / "secret"

        _, mask_names, *__ = _compute_volume_entries(
            _make_mount_specs({src}, {deep}, None),
            "/workspace",
            tmp_path,
        )

        assert len(mask_names) == 1
        name = mask_names[0]
        assert "mask_" in name
        # Slashes should be sanitized to underscores
        assert "/" not in name
        assert "\\" not in name


# =============================================================================
# Exception Parents
# =============================================================================

class TestRevealedParents:
    """Verify pushed file parent directory computation."""

    def test_basic_revealed_parent(self, tmp_path: Path):
        """Pushed file in masked area → parent directory computed."""
        src = tmp_path / "src"
        api = src / "api"
        config_file = api / "config.json"

        parents = _compute_revealed_parents(
            pushed_files={config_file},
            masked={api},
            container_root="/workspace",
            host_container_root=tmp_path,
        )

        assert len(parents) > 0
        assert any("src/api" in p for p in parents)

    def test_pushed_outside_mask_ignored(self, tmp_path: Path):
        """Pushed file NOT in masked area → no parent created."""
        src = tmp_path / "src"
        api = src / "api"
        # File is in src (mounted but not masked)
        main_file = src / "main.py"

        parents = _compute_revealed_parents(
            pushed_files={main_file},
            masked={api},
            container_root="/workspace",
            host_container_root=tmp_path,
        )

        assert len(parents) == 0

    def test_deep_nested_exception(self, tmp_path: Path):
        """Deeply nested pushed file → deep parent computed."""
        src = tmp_path / "src"
        masked_dir = src / "vendor"
        deep_file = masked_dir / "a" / "b" / "c" / "target.py"

        parents = _compute_revealed_parents(
            pushed_files={deep_file},
            masked={masked_dir},
            container_root="/workspace",
            host_container_root=tmp_path,
        )

        assert len(parents) > 0
        # Parent should include the deep path
        assert any("a/b/c" in p for p in parents)

    def test_posix_format(self, tmp_path: Path):
        """All revealed parent paths use POSIX separators."""
        src = tmp_path / "src"
        api = src / "api"
        config_file = api / "config.json"

        parents = _compute_revealed_parents(
            pushed_files={config_file},
            masked={api},
            container_root="/workspace",
            host_container_root=tmp_path,
        )

        for p in parents:
            assert "\\" not in p, f"Backslash in container path: {p}"
            assert p.startswith("/"), f"Container path not absolute: {p}"

    def test_revealed_parents_with_host_container_root(self, tmp_path: Path):
        """Exception parents include project dir when host_container_root is parent."""
        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()
        src = project_dir / "src"
        api = src / "api"
        config_file = api / "config.json"

        parents = _compute_revealed_parents(
            pushed_files={config_file},
            masked={api},
            container_root="/workspace",
            host_container_root=tmp_path,
        )

        assert len(parents) > 0
        for p in parents:
            assert "/workspace/MyProject/" in p


# =============================================================================
# Visibility Computation
# =============================================================================

class TestVisibility:
    """Verify visible/masked path computation."""

    def test_mounts_are_visible(self, tmp_path: Path):
        """Mounted paths appear in visible set."""
        src = tmp_path / "src"

        _, _, visible, hidden = _compute_volume_entries(
            _make_mount_specs({src}, None, None),
            "/workspace",
            tmp_path,
        )

        assert "/workspace/src" in visible
        assert len(hidden) == 0

    def test_masked_are_hidden(self, tmp_path: Path):
        """Masked paths appear in masked set."""
        src = tmp_path / "src"
        api = src / "api"

        _, _, visible, hidden = _compute_volume_entries(
            _make_mount_specs({src}, {api}, None),
            "/workspace",
            tmp_path,
        )

        assert "/workspace/src/api" in hidden
        assert "/workspace/src" in visible

    def test_revealed_are_visible(self, tmp_path: Path):
        """Revealed paths appear in visible set."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        _, _, visible, hidden = _compute_volume_entries(
            _make_mount_specs({src}, {api}, {public}),
            "/workspace",
            tmp_path,
        )

        assert "/workspace/src/api/public" in visible
        assert "/workspace/src/api" in hidden

    def test_mount_and_mask_same_path(self, tmp_path: Path):
        """Same path in mounts AND masked → appears in both sets."""
        src = tmp_path / "src"

        _, _, visible, hidden = _compute_volume_entries(
            _make_mount_specs({src}, {src}, None),
            "/workspace",
            tmp_path,
        )

        assert "/workspace/src" in visible
        assert "/workspace/src" in hidden


# =============================================================================
# Validation
# =============================================================================

class TestValidation:
    """Verify hierarchy validation rules."""

    def test_mask_without_mount_is_structurally_impossible(self, tmp_path: Path):
        """In mount_specs, masks are patterns ON a mount — orphan mask can't exist.

        Test replaced: old model had flat sets where mask without mount was expressible.
        New model: masks are patterns within MountSpecPath, so no mount = no patterns.
        """
        # Empty mount_specs = no mounts, no masks — no errors
        errors = _validate_hierarchy([])
        assert len(errors) == 0

    def test_reveal_without_mask_errors(self, tmp_path: Path):
        """Exception pattern without preceding deny → validation error."""
        src = tmp_path / "src"

        # Create a mount_spec with exception before deny
        ms = MountSpecPath(mount_root=src, patterns=["!orphan/"])
        errors = _validate_hierarchy([ms])

        assert len(errors) >= 1
        assert any("no preceding deny" in e.lower() for e in errors)

    def test_valid_hierarchy_no_errors(self, tmp_path: Path):
        """Correct hierarchy → no validation errors."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        errors = _validate_hierarchy(
            _make_mount_specs({src}, {api}, {public}),
        )

        assert len(errors) == 0

    def test_mask_equals_mount_valid(self, tmp_path: Path):
        """Mask path == mount path → valid (mount is its own parent)."""
        src = tmp_path / "src"

        errors = _validate_hierarchy(
            _make_mount_specs({src}, {src}, None),
        )

        assert len(errors) == 0


# =============================================================================
# Full Pipeline (compute_container_hierarchy)
# =============================================================================

class TestComputeContainerHierarchy:
    """Integration tests for the full computation pipeline."""

    def test_empty_config(self, tmp_path: Path):
        """Empty config → empty hierarchy with no errors."""
        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs(None, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        assert hierarchy.ordered_volumes == []
        assert hierarchy.revealed_parents == set()
        assert hierarchy.validation_errors == []
        assert hierarchy.visible_paths == set()
        assert hierarchy.masked_paths == set()

    def test_full_pipeline(self, tmp_path: Path):
        """Full config produces consistent hierarchy across all fields."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"
        config_file = api / "config.json"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}, {public}),
            pushed_files={config_file},
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        # No errors
        assert len(hierarchy.validation_errors) == 0

        # 3 volumes: mount + mask + reveal
        assert len(hierarchy.ordered_volumes) == 3

        # Exception parents for pushed file
        assert len(hierarchy.revealed_parents) > 0

        # Visibility consistent
        assert "/workspace/src" in hierarchy.visible_paths
        assert "/workspace/src/api" in hierarchy.masked_paths
        assert "/workspace/src/api/public" in hierarchy.visible_paths

    def test_sibling_volumes_appended(self, tmp_path: Path):
        """Sibling volumes appear after primary volumes."""
        src = tmp_path / "src"
        sibling = _make_sibling(
            host_path=Path("C:/Libs"),
            container_path="/libs",
            mounts={Path("C:/Libs/common")},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
        )

        # Primary + sibling volumes
        assert len(hierarchy.ordered_volumes) == 2
        assert "/workspace/src" in hierarchy.ordered_volumes[0]
        assert "/libs/common" in hierarchy.ordered_volumes[1]

    def test_sibling_validation_prefixed(self, tmp_path: Path):
        """Sibling validation errors include sibling path prefix."""
        sibling = _make_sibling(
            host_path=Path("C:/Libs"),
            container_path="/libs",
            mounts=set(),
            masked={Path("C:/Libs/orphan")},  # No parent mount
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path / "src"}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
        )

        # Sibling with orphan mask is structurally impossible in mount_specs.
        # The _make_sibling helper silently drops masks without owning mounts.
        # No validation errors expected.
        assert len(hierarchy.validation_errors) == 0

    def test_multiple_siblings(self, tmp_path: Path):
        """Multiple siblings each contribute their own volumes."""
        sibling1 = _make_sibling(
            host_path=Path("C:/Libs"),
            container_path="/libs",
            mounts={Path("C:/Libs/common")},
        )
        sibling2 = _make_sibling(
            host_path=Path("C:/Tools"),
            container_path="/tools",
            mounts={Path("C:/Tools/scripts")},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path / "src"}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling1, sibling2],
        )

        # 1 primary + 2 sibling volumes
        assert len(hierarchy.ordered_volumes) == 3
        assert any("/libs" in v for v in hierarchy.ordered_volumes)
        assert any("/tools" in v for v in hierarchy.ordered_volumes)

    def test_mask_volume_names_populated(self, tmp_path: Path):
        """mask_volume_names contains names from primary masked dirs."""
        src = tmp_path / "src"
        api = src / "api"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        assert len(hierarchy.mask_volume_names) == 1
        assert hierarchy.mask_volume_names[0].startswith("mask_")

    def test_mask_volume_names_includes_siblings(self, tmp_path: Path):
        """mask_volume_names includes sibling mask names."""
        src = tmp_path / "src"
        sibling = _make_sibling(
            host_path=Path("C:/Libs"),
            container_path="/libs",
            mounts={Path("C:/Libs/common")},
            masked={Path("C:/Libs/common/internal")},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
        )

        # Sibling has 1 mask
        assert len(hierarchy.mask_volume_names) == 1
        assert hierarchy.mask_volume_names[0].startswith("mask_")

    def test_mask_volume_names_empty_when_no_masks(self, tmp_path: Path):
        """mask_volume_names is empty when no masked dirs."""
        src = tmp_path / "src"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        assert hierarchy.mask_volume_names == []

    def test_dataclass_defaults(self):
        """ContainerHierarchy defaults to empty collections."""
        h = ContainerHierarchy()
        assert h.ordered_volumes == []
        assert h.mask_volume_names == []
        assert h.isolation_volume_names == []
        assert h.revealed_parents == set()
        assert h.validation_errors == []
        assert h.visible_paths == set()
        assert h.masked_paths == set()


# =============================================================================
# Mirrored Parents
# =============================================================================

class TestMirroredParents:
    """Verify mirrored intermediate directory computation."""

    def test_mirrored_parents_computed(self, tmp_path: Path):
        """Masked + deep reveal → intermediates in revealed_parents."""
        src = tmp_path / "src"
        api = src / "api"
        handlers = api / "handlers"
        public = handlers / "public"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}, {public}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            mirrored=True,
        )

        # Intermediates: api/handlers should be in revealed_parents
        assert any("api/handlers" in p for p in hierarchy.revealed_parents)

    def test_mirrored_disabled_no_extra_parents(self, tmp_path: Path):
        """mirrored=False → only pushed file parents, no mirrored intermediates."""
        src = tmp_path / "src"
        api = src / "api"
        handlers = api / "handlers"
        public = handlers / "public"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}, {public}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            mirrored=False,
        )

        # No pushed files and mirrored disabled → no revealed parents
        assert len(hierarchy.revealed_parents) == 0

    def test_mirrored_direct_child_no_intermediates(self, tmp_path: Path):
        """Reveal is direct child of mask → no intermediates needed."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        parents = _compute_mirrored_parents(
            masked={api},
            revealed={public},
            mounts={src},
            container_root="/workspace",
            host_container_root=tmp_path,
        )

        # public.parent == api (the mask), so no intermediates
        assert len(parents) == 0

    def test_mirrored_with_siblings(self, tmp_path: Path):
        """Sibling has mask + reveal → sibling intermediates computed."""
        src = tmp_path / "src"
        sibling_host = Path("C:/Libs")
        sibling_common = sibling_host / "common"
        sibling_internal = sibling_common / "internal"
        sibling_public = sibling_internal / "public"

        sibling = _make_sibling(
            host_path=sibling_host,
            container_path="/libs",
            mounts={sibling_common},
            masked={sibling_common},
            revealed={sibling_public},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
            mirrored=True,
        )

        # Sibling intermediate: common/internal should be in revealed_parents
        assert any("internal" in p for p in hierarchy.revealed_parents)


# =============================================================================
# Mask Volume Name Collision (Bug Fix)
# =============================================================================

class TestMaskVolumeCollision:
    """Verify mask volume names are disambiguated when paths sanitize identically."""

    def test_colliding_paths_get_unique_names(self, tmp_path: Path):
        """Two paths that sanitize to the same volume name get unique names.

        E.g., 'test_assets/compound+special/secret' and
              'test_assets/compound.special/secret'
        both sanitize to 'mask_..._test_assets_compoundspecial_secret'.
        """
        src = tmp_path / "src"
        # These two differ only in chars stripped by sanitize_volume_name
        mask_a = src / "test_assets" / "compound+special" / "secret"
        mask_b = src / "test_assets" / "compound.special" / "secret"

        _, mask_names, *__ = _compute_volume_entries(
            _make_mount_specs({src}, {mask_a, mask_b}, None),
            "/workspace",
            tmp_path,
        )

        assert len(mask_names) == 2
        assert mask_names[0] != mask_names[1], (
            f"Volume names must be unique but both are '{mask_names[0]}'"
        )

    def test_non_colliding_paths_get_clean_names(self, tmp_path: Path):
        """Non-colliding paths get clean names without numeric suffixes."""
        src = tmp_path / "src"
        api = src / "api"
        vendor = src / "vendor"

        _, mask_names, *__ = _compute_volume_entries(
            _make_mount_specs({src}, {api, vendor}, None),
            "/workspace",
            tmp_path,
        )

        assert len(mask_names) == 2
        for name in mask_names:
            # No _2, _3 suffix on non-colliding names
            assert not name.endswith("_2"), f"Spurious suffix on '{name}'"
            assert not name.endswith("_3"), f"Spurious suffix on '{name}'"

    def test_collision_suffix_increments(self, tmp_path: Path):
        """Three-way collision produces _2 and _3 suffixes."""
        src = tmp_path / "src"
        # Three paths that all sanitize identically
        mask_a = src / "a+b" / "c"
        mask_b = src / "a.b" / "c"
        mask_c = src / "a!b" / "c"

        _, mask_names, *__ = _compute_volume_entries(
            _make_mount_specs({src}, {mask_a, mask_b, mask_c}, None),
            "/workspace",
            tmp_path,
        )

        assert len(mask_names) == 3
        assert len(set(mask_names)) == 3, (
            f"All names must be unique: {mask_names}"
        )

    def test_collision_in_full_pipeline(self, tmp_path: Path):
        """Full pipeline handles collisions without YAML errors."""
        src = tmp_path / "src"
        mask_a = src / "compound+special" / "secret"
        mask_b = src / "compound.special" / "secret"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {mask_a, mask_b}, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        assert len(hierarchy.mask_volume_names) == 2
        assert hierarchy.mask_volume_names[0] != hierarchy.mask_volume_names[1]
        assert len(hierarchy.validation_errors) == 0


# =============================================================================
# Validation: Path Under HCR
# =============================================================================

class TestValidationPathUnderHCR:
    """Verify _validate_hierarchy catches paths not under host_container_root."""

    def test_path_not_under_hcr_errors(self, tmp_path: Path):
        """Path on different drive/root → validation error."""
        foreign = Path("D:/foreign/mount")

        errors = _validate_hierarchy(
            _make_mount_specs({foreign}, None, None),
            host_container_root=tmp_path,
        )

        assert any("not under host container root" in e for e in errors)

    def test_all_under_hcr_no_extra_errors(self, tmp_path: Path):
        """All paths under HCR → no HCR-related errors."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        errors = _validate_hierarchy(
            _make_mount_specs({src}, {api}, {public}),
            host_container_root=tmp_path,
        )

        assert len(errors) == 0

    def test_hcr_none_skips_check(self, tmp_path: Path):
        """host_container_root=None → HCR check skipped (backwards compat)."""
        foreign = Path("D:/foreign/mount")

        errors = _validate_hierarchy(
            _make_mount_specs({foreign}, None, None),
        )

        # Only "no parent mount" would fire for masked, but masked is empty
        # Foreign mount itself is not an error without HCR check
        assert not any("host container root" in e for e in errors)

    def test_mount_not_under_hcr(self, tmp_path: Path):
        """Mount root not under HCR → validation error."""
        foreign_mount = Path("D:/other/src")
        ms = MountSpecPath(mount_root=foreign_mount, patterns=[])

        errors = _validate_hierarchy(
            [ms],
            host_container_root=tmp_path,
        )

        hcr_errors = [e for e in errors if "not under host container root" in e]
        assert len(hcr_errors) == 1
        assert "Mount" in hcr_errors[0]


# =============================================================================
# Walk Mirrored Intermediates (Unified Walk)
# =============================================================================

class TestWalkMirroredIntermediates:
    """Verify _walk_mirrored_intermediates with per-mask and fixed ceilings."""

    def test_ceiling_none_walks_to_mask(self, tmp_path: Path):
        """ceiling=None → same result as existing mask-only behavior."""
        src = tmp_path / "src"
        api = src / "api"
        internal = api / "internal"
        handlers = internal / "handlers"
        public = handlers / "public"

        result = _walk_mirrored_intermediates(
            masked={api},
            revealed={public},
            mounts={src},
            ceiling=None,
        )

        assert internal in result
        assert handlers in result
        assert api not in result  # ceiling (exclusive)
        assert public not in result  # reveal itself
        assert src not in result  # above mask

    def test_ceiling_above_mount_includes_ancestors(self, tmp_path: Path):
        """Fixed ceiling above mount → includes dirs between mount and mask."""
        project_root = tmp_path / "project"
        subdir = project_root / "SubDir"
        content = subdir / "Content"
        stuff = content / "Stuff"
        internal = stuff / "Internal"
        public = internal / "Public"

        ceiling = project_root.parent  # tmp_path (exclusive)

        result = _walk_mirrored_intermediates(
            masked={stuff},
            revealed={public},
            mounts={content},
            ceiling=ceiling,
        )

        # Between public.parent and ceiling (exclusive)
        assert internal in result  # between mask and reveal
        assert stuff in result  # the mask itself (below ceiling)
        assert content in result  # the mount (below ceiling)
        assert subdir in result  # above mount, below ceiling
        assert project_root in result  # above mount, below ceiling
        assert tmp_path not in result  # ceiling itself (exclusive)

    def test_ceiling_exclusive(self, tmp_path: Path):
        """Ceiling path itself is NOT included in result."""
        src = tmp_path / "src"
        api = src / "api"
        internal = api / "internal"
        public = internal / "public"

        ceiling = tmp_path  # exclusive

        result = _walk_mirrored_intermediates(
            masked={api},
            revealed={public},
            mounts={src},
            ceiling=ceiling,
        )

        assert tmp_path not in result
        assert src in result
        assert api in result
        assert internal in result

    def test_reveal_direct_child_with_ceiling(self, tmp_path: Path):
        """Reveal is direct child of mask — no mask-to-reveal intermediates,
        but mount-to-ceiling intermediates still present with fixed ceiling."""
        project_root = tmp_path / "project"
        subdir = project_root / "SubDir"
        content = subdir / "Content"
        stuff = content / "Stuff"
        public = stuff / "Public"

        ceiling = project_root.parent  # tmp_path

        result = _walk_mirrored_intermediates(
            masked={stuff},
            revealed={public},
            mounts={content},
            ceiling=ceiling,
        )

        # public.parent == stuff, so walk covers stuff → content → subdir → project_root
        assert stuff in result
        assert content in result
        assert subdir in result
        assert project_root in result
        assert tmp_path not in result  # ceiling (exclusive)

    def test_multiple_reveals_union(self, tmp_path: Path):
        """Two reveals under same mask → union of both walks."""
        src = tmp_path / "src"
        api = src / "api"
        handlers = api / "handlers"
        models = api / "models"
        public_h = handlers / "public"
        public_m = models / "public"

        result = _walk_mirrored_intermediates(
            masked={api},
            revealed={public_h, public_m},
            mounts={src},
            ceiling=None,
        )

        assert handlers in result
        assert models in result
        assert api not in result  # ceiling (per-mask)

    def test_mount_only_no_reveals_with_ceiling(self, tmp_path: Path):
        """Mount at depth, no masks, no reveals — mount parents walked to ceiling."""
        project_root = tmp_path / "project"
        compound = project_root / "CompoundWords"
        public = compound / "public"

        ceiling = project_root.parent  # tmp_path (exclusive)

        result = _walk_mirrored_intermediates(
            masked=set(),
            revealed=set(),
            mounts={public},
            ceiling=ceiling,
        )

        # Mount parents between public.parent and ceiling
        assert compound in result  # public.parent
        assert project_root in result  # above mount, below ceiling
        assert tmp_path not in result  # ceiling (exclusive)

    def test_mount_parents_not_walked_without_ceiling(self, tmp_path: Path):
        """ceiling=None → mount parents NOT walked (container mkdir-p mode)."""
        project_root = tmp_path / "project"
        compound = project_root / "CompoundWords"
        public = compound / "public"

        result = _walk_mirrored_intermediates(
            masked=set(),
            revealed=set(),
            mounts={public},
            ceiling=None,
        )

        assert result == set()  # No reveals → nothing to walk

    def test_matches_compute_mirrored_intermediate_paths_default(self, tmp_path: Path):
        """compute_mirrored_intermediate_paths(ceiling=None) matches direct walk."""
        src = tmp_path / "src"
        api = src / "api"
        internal = api / "internal"
        public = internal / "public"

        direct = _walk_mirrored_intermediates(
            masked={api}, revealed={public}, mounts={src},
        )
        via_public = compute_mirrored_intermediate_paths(
            masked={api}, revealed={public}, mounts={src},
        )

        assert direct == via_public


# =============================================================================
# Isolation Volumes (Layer 4)
# =============================================================================

class TestIsolationVolumes:
    """Verify Layer 4 isolation volume computation."""

    def test_isolation_paths_produce_volumes(self, tmp_path: Path):
        """isolation_paths → entries in isolation_volume_entries + isolation_volume_names."""
        src = tmp_path / "src"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            isolation_paths=[("Claude Code", "/root/.local")],
        )

        # L4 lives in its own list, separate from ordered_volumes (L1-L3 + siblings)
        assert len(hierarchy.isolation_volume_entries) == 1
        assert ":/root/.local" in hierarchy.isolation_volume_entries[0]
        assert not any("iso_" in v for v in hierarchy.ordered_volumes)

        # Name tracked in isolation_volume_names
        assert len(hierarchy.isolation_volume_names) == 1
        assert hierarchy.isolation_volume_names[0].startswith("iso_")

    def test_isolation_separate_from_ordered_volumes(self, tmp_path: Path):
        """L4 entries are stored separately from L1-L3 + siblings."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}, {public}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            isolation_paths=[("Git", "/usr/bin")],
        )

        # L1 mount + L2 mask + L3 reveal = 3 entries in ordered_volumes
        assert len(hierarchy.ordered_volumes) == 3
        assert not any("iso_" in v for v in hierarchy.ordered_volumes)
        # L4 is in isolation_volume_entries
        assert len(hierarchy.isolation_volume_entries) == 1
        assert ":/usr/bin" in hierarchy.isolation_volume_entries[0]

    def test_multiple_isolation_paths(self, tmp_path: Path):
        """Multiple isolation paths from different extensions."""
        src = tmp_path / "src"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            isolation_paths=[
                ("Claude Code", "/root/.local"),
                ("P4 MCP Server", "/usr/local/lib/p4-mcp-server"),
            ],
        )

        assert len(hierarchy.isolation_volume_names) == 2
        assert len(hierarchy.isolation_volume_entries) == 2
        assert any("/root/.local" in v for v in hierarchy.isolation_volume_entries)
        assert any("/usr/local/lib/p4-mcp-server" in v for v in hierarchy.isolation_volume_entries)

    def test_no_isolation_paths_empty_list(self, tmp_path: Path):
        """No isolation_paths → isolation_volume_names stays empty."""
        src = tmp_path / "src"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        assert hierarchy.isolation_volume_names == []

    def test_isolation_volume_naming(self, tmp_path: Path):
        """Volume name is iso_{ext}_{sanitized_path}."""
        src = tmp_path / "src"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            isolation_paths=[("Claude Code", "/root/.local")],
        )

        name = hierarchy.isolation_volume_names[0]
        assert name.startswith("iso_")
        assert "claude" in name.lower()
        assert "root" in name.lower()
        # No slashes or invalid chars
        assert "/" not in name
        assert "\\" not in name

    def test_isolation_with_siblings(self, tmp_path: Path):
        """Isolation volumes are separate from sibling volumes."""
        src = tmp_path / "src"
        sibling = _make_sibling(
            host_path=Path("C:/Libs"),
            container_path="/libs",
            mounts={Path("C:/Libs/common")},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, None, None),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
            isolation_paths=[("Claude Code", "/root/.local")],
        )

        # primary mount + sibling mount = 2 entries in ordered_volumes
        assert len(hierarchy.ordered_volumes) == 2
        assert not any("iso_" in v for v in hierarchy.ordered_volumes)
        # L4 is tracked separately
        assert len(hierarchy.isolation_volume_entries) == 1
        assert ":/root/.local" in hierarchy.isolation_volume_entries[0]


# ──────────────────────────────────────────────
# TEST: per-spec delivery (bind vs detached) — Task 2.3
# ──────────────────────────────────────────────


class TestPerSpecDelivery:
    """Detached specs emit no L1/L2/L3 volumes; bind specs behave as before."""

    def test_detached_spec_emits_no_volume_entries(self, tmp_path: Path):
        """A single detached spec produces an empty ordered_volumes list."""
        src = tmp_path / "src"
        detached = MountSpecPath(
            mount_root=src, patterns=["vendor/"], delivery="detached",
        )

        entries, masks, visible, hidden = _compute_volume_entries(
            [detached], "/workspace", tmp_path,
        )
        assert entries == []
        assert masks == []
        # Tracking still reflects container-side visibility semantics.
        assert "/workspace/src" in visible
        assert "/workspace/src/vendor" in hidden

    def test_bind_spec_unchanged_baseline(self, tmp_path: Path):
        """A pure-bind spec produces the same entries as before delivery existed."""
        src = tmp_path / "src"
        bind = MountSpecPath(
            mount_root=src, patterns=["vendor/", "!vendor/public/"], delivery="bind",
        )

        entries, masks, _visible, _hidden = _compute_volume_entries(
            [bind], "/workspace", tmp_path,
        )
        assert len(entries) == 3  # L1 bind + L2 mask + L3 reveal
        assert entries[0].endswith(":/workspace/src")
        assert any(e.startswith("mask_") for e in entries)
        assert len(masks) == 1

    def test_mixed_scope_only_bind_spec_emits_volumes(self, tmp_path: Path):
        """A scope with one bind + one detached spec emits only the bind's volumes."""
        src = tmp_path / "src"
        assets = tmp_path / "assets"
        bind = MountSpecPath(mount_root=src, patterns=[], delivery="bind")
        detached = MountSpecPath(
            mount_root=assets, patterns=["cache/"], delivery="detached",
        )

        entries, masks, visible, hidden = _compute_volume_entries(
            [bind, detached], "/workspace", tmp_path,
        )
        # Only the bind mount_root produces an entry.
        assert len(entries) == 1
        assert entries[0].endswith(":/workspace/src")
        assert masks == []
        # Both specs contribute to visibility tracking.
        assert "/workspace/src" in visible
        assert "/workspace/assets" in visible
        assert "/workspace/assets/cache" in hidden

    def test_detached_ignores_reveal_pattern_in_compose(self, tmp_path: Path):
        """Reveal patterns on a detached spec do not produce L3 bind entries."""
        src = tmp_path / "src"
        detached = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/public/"],
            delivery="detached",
        )

        entries, masks, visible, hidden = _compute_volume_entries(
            [detached], "/workspace", tmp_path,
        )
        assert entries == []
        assert masks == []
        assert "/workspace/src" in visible
        assert "/workspace/src/vendor/public" in visible
        assert "/workspace/src/vendor" in hidden

    def test_l4_still_emitted_for_all_detached_scope(self, tmp_path: Path):
        """An all-detached scope still emits L4 isolation volumes."""
        src = tmp_path / "src"
        detached = MountSpecPath(
            mount_root=src, patterns=[], delivery="detached",
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=[detached],
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            isolation_paths=[("Claude Code", "/root/.local")],
        )
        assert hierarchy.ordered_volumes == []
        assert hierarchy.mask_volume_names == []
        assert len(hierarchy.isolation_volume_entries) == 1
        assert ":/root/.local" in hierarchy.isolation_volume_entries[0]

    def test_bind_only_scope_byte_identical_to_legacy_baseline(self, tmp_path: Path):
        """A scope built without ever mentioning delivery matches bind-by-default output."""
        src = tmp_path / "src"
        legacy = MountSpecPath(mount_root=src, patterns=["vendor/"])  # default bind
        explicit = MountSpecPath(
            mount_root=src, patterns=["vendor/"], delivery="bind",
        )

        entries_legacy, masks_legacy, vis_legacy, hid_legacy = _compute_volume_entries(
            [legacy], "/workspace", tmp_path,
        )
        entries_explicit, masks_explicit, vis_explicit, hid_explicit = _compute_volume_entries(
            [explicit], "/workspace", tmp_path,
        )
        assert entries_legacy == entries_explicit
        assert masks_legacy == masks_explicit
        assert vis_legacy == vis_explicit
        assert hid_legacy == hid_explicit


# =============================================================================
# Stencil volume emission (Task 4.4)
# =============================================================================

class TestStencilVolumes:
    """_compute_stencil_volumes emits L_volume entries for delivery='volume' specs."""

    def test_no_volume_specs_returns_empty(self, tmp_path: Path):
        """Bind-only mount_specs produce no stencil volumes."""
        specs = [MountSpecPath(mount_root=tmp_path / "src", delivery="bind")]
        entries, names = _compute_stencil_volumes(specs, "/workspace", tmp_path)
        assert entries == []
        assert names == []

    def test_volume_spec_container_only(self, tmp_path: Path):
        """Container-only volume-delivery spec emits entry at mount_root posix path."""
        spec = MountSpecPath(
            mount_root=Path("/workspace/cache"),
            delivery="volume",
            content_seed="folder",
            host_path=None,
        )
        entries, names = _compute_stencil_volumes([spec], "/workspace", tmp_path)
        assert len(entries) == 1
        assert len(names) == 1
        assert entries[0].endswith(":/workspace/cache")
        assert names[0].startswith("stencil_0_")
        # Entry and name share the same volume name prefix
        assert entries[0].split(":")[0] == names[0]

    def test_volume_name_stable_across_calls(self, tmp_path: Path):
        """Same spec → same derived name (config round-trip stability)."""
        spec = MountSpecPath(
            mount_root=Path("/workspace/data"),
            delivery="volume",
            content_seed="folder",
            host_path=None,
        )
        e1, n1 = _compute_stencil_volumes([spec], "/workspace", tmp_path)
        e2, n2 = _compute_stencil_volumes([spec], "/workspace", tmp_path)
        assert n1 == n2
        assert e1 == e2

    def test_multiple_volume_specs_indexed(self, tmp_path: Path):
        """Multiple volume specs get distinct indexed names."""
        specs = [
            MountSpecPath(
                mount_root=Path("/workspace/a"),
                delivery="volume",
                content_seed="folder",
                host_path=None,
            ),
            MountSpecPath(
                mount_root=Path("/workspace/b"),
                delivery="volume",
                content_seed="folder",
                host_path=None,
            ),
        ]
        entries, names = _compute_stencil_volumes(specs, "/workspace", tmp_path)
        assert len(names) == 2
        assert names[0] != names[1]
        assert names[0].startswith("stencil_0_")
        assert names[1].startswith("stencil_1_")

    def test_mixed_delivery_only_volume_emits(self, tmp_path: Path):
        """Mix of bind/detached/volume — only volume specs emit here."""
        specs = [
            MountSpecPath(mount_root=tmp_path / "src", delivery="bind"),
            MountSpecPath(
                mount_root=Path("/workspace/vol"),
                delivery="volume",
                content_seed="folder",
                host_path=None,
            ),
            MountSpecPath(
                mount_root=tmp_path / "snap",
                delivery="detached",
                content_seed="tree",
                host_path=tmp_path / "snap",
            ),
        ]
        entries, names = _compute_stencil_volumes(specs, "/workspace", tmp_path)
        assert len(entries) == 1
        # Index follows original mount_specs order — volume was at idx 1
        assert names[0].startswith("stencil_1_")

    def test_derive_volume_name_sanitized(self):
        """_derive_stencil_volume_name strips leading slash and sanitizes."""
        name = _derive_stencil_volume_name(3, "/workspace/nested/path")
        assert name.startswith("stencil_3_")
        # No leading slash in the key portion
        assert "//" not in name


class TestStencilVolumeHierarchyIntegration:
    """End-to-end: compute_container_hierarchy populates stencil_volume_* fields."""

    def test_hierarchy_exposes_stencil_volumes(self, tmp_path: Path):
        """Volume-delivery spec surfaces on hierarchy fields for compose consumption."""
        specs = [
            MountSpecPath(
                mount_root=Path("/workspace/perm"),
                delivery="volume",
                content_seed="folder",
                host_path=None,
            ),
        ]
        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=specs,
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )
        assert len(hierarchy.stencil_volume_entries) == 1
        assert len(hierarchy.stencil_volume_names) == 1
        assert hierarchy.stencil_volume_entries[0].endswith(":/workspace/perm")


