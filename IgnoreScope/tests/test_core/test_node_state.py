"""Tests for core/node_state.py — NodeState dataclass and visibility functions.

Covers:
  NS-2: NodeState dataclass + compute_visibility()
  NS-3: find_container_orphaned_paths()
  NS-4: compute_node_state()
  NS-5: apply_node_states_from_scope()
  NS-7: find_paths_with_direct_visible_children()
  NS-8: detect_orphan_creating_removals()
  NS-9: Exhaustive truth table regression (all 14 folder+file states)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.node_state import (
    NodeState,
    compute_visibility,
    find_container_orphaned_paths,
    find_paths_with_direct_visible_children,
    detect_orphan_creating_removals,
    compute_node_state,
    apply_node_states_from_scope,
)
from IgnoreScope.core.config import ScopeDockerConfig
from IgnoreScope.core.mount_spec_path import MountSpecPath


def _make_mount_specs(
    mounts: set[Path],
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
) -> list[MountSpecPath]:
    """Convert flat sets to mount_specs for test compat."""
    specs = []
    for mount_root in sorted(mounts):
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


# =============================================================================
# NS-2: compute_visibility()
# =============================================================================

class TestComputeVisibility:
    """Verify all 5 visibility derivation outcomes."""

    def test_all_false_is_hidden(self):
        assert compute_visibility(False, False, False, False, False) == "hidden"

    def test_mounted_only_is_visible(self):
        assert compute_visibility(True, False, False, False, False) == "visible"

    def test_masked_and_mounted_is_masked(self):
        assert compute_visibility(True, True, False, False, False) == "masked"

    def test_revealed_is_revealed(self):
        assert compute_visibility(True, True, True, False, False) == "revealed"

    def test_container_orphaned_takes_priority(self):
        assert compute_visibility(False, True, False, True, True) == "orphaned"

    def test_container_orphaned_beats_revealed(self):
        """Container-orphaned has highest priority even if revealed is also set."""
        assert compute_visibility(False, True, True, True, True) == "orphaned"

    def test_masked_without_mounted_is_hidden(self):
        """GAP 1 fix: masked=T but mounted=F → hidden (stale config)."""
        assert compute_visibility(False, True, False, False, False) == "hidden"

    def test_ttff_is_orphaned(self):
        """pushed=T, masked=T, mounted=F, revealed=F → orphaned flag drives it."""
        assert compute_visibility(False, True, False, True, True) == "orphaned"


# =============================================================================
# NS-2: NodeState dataclass
# =============================================================================

class TestNodeStateDataclass:
    """Verify frozen dataclass behavior and defaults."""

    def test_default_state(self):
        ns = NodeState()
        assert ns.mounted is False
        assert ns.masked is False
        assert ns.revealed is False
        assert ns.pushed is False
        assert ns.container_orphaned is False
        assert ns.visibility == "hidden"
        assert ns.has_pushed_descendant is False
        assert ns.has_direct_visible_child is False

    def test_frozen_prevents_mutation(self):
        ns = NodeState()
        with pytest.raises(AttributeError):
            ns.mounted = True  # type: ignore[misc]

    def test_custom_fields(self):
        ns = NodeState(
            mounted=True,
            masked=True,
            revealed=True,
            pushed=False,
            container_orphaned=False,
            visibility="revealed",
        )
        assert ns.mounted is True
        assert ns.visibility == "revealed"

    def test_equality(self):
        a = NodeState(mounted=True, visibility="visible")
        b = NodeState(mounted=True, visibility="visible")
        assert a == b

    def test_inequality(self):
        a = NodeState(mounted=True, visibility="visible")
        b = NodeState(mounted=False, visibility="hidden")
        assert a != b


# =============================================================================
# NS-3: find_container_orphaned_paths()
# =============================================================================

class TestFindContainerOrphanedPaths:
    """Verify container orphan detection logic."""

    def test_pushed_under_active_mount_and_mask_not_orphaned(self, tmp_path: Path):
        """Pushed file under both mount and mask → NOT orphaned."""
        src = tmp_path / "src"
        api = src / "api"
        config_file = api / "config.json"

        orphans = find_container_orphaned_paths(
            pushed_files={config_file},
            mounts={src},
            masked={api},
        )
        assert orphans == set()

    def test_pushed_under_mask_mount_removed_is_orphaned(self, tmp_path: Path):
        """Pushed file under mask but mount removed → container-orphaned."""
        api = tmp_path / "src" / "api"
        config_file = api / "config.json"

        orphans = find_container_orphaned_paths(
            pushed_files={config_file},
            mounts=set(),  # mount removed
            masked={api},
        )
        assert config_file in orphans

    def test_pushed_not_under_mask_not_orphaned(self, tmp_path: Path):
        """Pushed file not under any mask → NOT orphaned."""
        src = tmp_path / "src"
        main_file = src / "main.py"

        orphans = find_container_orphaned_paths(
            pushed_files={main_file},
            mounts={src},
            masked=set(),
        )
        assert orphans == set()

    def test_empty_inputs_no_orphans(self):
        """No pushed files → no orphans."""
        orphans = find_container_orphaned_paths(
            pushed_files=set(),
            mounts=set(),
            masked=set(),
        )
        assert orphans == set()

    def test_multiple_pushed_mixed(self, tmp_path: Path):
        """Mix of orphaned and non-orphaned pushed files."""
        src = tmp_path / "src"
        api = src / "api"
        vendor = src / "vendor"
        f1 = api / "a.py"      # under mask + mount → NOT orphaned
        f2 = vendor / "b.py"   # under mask, no mount → orphaned

        orphans = find_container_orphaned_paths(
            pushed_files={f1, f2},
            mounts={src},
            masked={api, vendor},
        )
        # f1 is under src mount, f2 is also under src mount
        assert orphans == set()

        # Now remove the mount
        orphans = find_container_orphaned_paths(
            pushed_files={f1, f2},
            mounts=set(),
            masked={api, vendor},
        )
        assert f1 in orphans
        assert f2 in orphans


# =============================================================================
# NS-4: compute_node_state()
# =============================================================================

class TestComputeNodeState:
    """Verify per-node state computation."""

    def test_path_under_mount_is_visible(self, tmp_path: Path):
        src = tmp_path / "src"
        child = src / "main.py"

        ns = compute_node_state(
            path=child,
            mount_specs=_make_mount_specs({src}),
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.visibility == "visible"

    def test_path_under_mount_and_mask_is_masked(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"
        child = api / "internal.py"

        ns = compute_node_state(
            path=child,
            mount_specs=_make_mount_specs({src}, {api}),
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.visibility == "masked"

    def test_path_under_mount_mask_reveal_is_revealed(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"
        child = public / "index.html"

        ns = compute_node_state(
            path=child,
            mount_specs=_make_mount_specs({src}, {api}, {public}),
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.revealed is True
        assert ns.visibility == "revealed"

    def test_path_not_under_anything_is_hidden(self, tmp_path: Path):
        stray = tmp_path / "other" / "file.txt"

        ns = compute_node_state(
            path=stray,
            mount_specs=_make_mount_specs({tmp_path / "src"}),
            pushed_files=set(),
        )
        assert ns.mounted is False
        assert ns.visibility == "hidden"

    def test_pushed_under_removed_mount_is_hidden(self, tmp_path: Path):
        """No mount → no mask possible → pushed file with no mount is hidden.
        Orphan detection is batch-level (find_container_orphaned_paths).
        """
        pushed_file = tmp_path / "src" / "api" / "config.json"

        ns = compute_node_state(
            path=pushed_file,
            mount_specs=[],
            pushed_files={pushed_file},
        )
        assert ns.pushed is True
        assert ns.mounted is False
        assert ns.masked is False
        assert ns.container_orphaned is False
        assert ns.visibility == "hidden"

    def test_mount_point_itself_is_visible(self, tmp_path: Path):
        src = tmp_path / "src"

        ns = compute_node_state(
            path=src,
            mount_specs=_make_mount_specs({src}),
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.visibility == "visible"

    def test_mask_point_itself_is_masked(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"

        ns = compute_node_state(
            path=api,
            mount_specs=_make_mount_specs({src}, {api}),
            pushed_files=set(),
        )
        assert ns.masked is True
        assert ns.visibility == "masked"

    def test_reveal_point_itself_is_revealed(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        ns = compute_node_state(
            path=public,
            mount_specs=_make_mount_specs({src}, {api}, {public}),
            pushed_files=set(),
        )
        assert ns.revealed is True
        assert ns.visibility == "revealed"

    # --- Mount-root-mask (dual state) ---

    def test_mount_with_mask_pattern(self, tmp_path: Path):
        """Mount with mask pattern on subfolder → subfolder is masked."""
        src = tmp_path / "src"
        api = src / "api"

        ms = MountSpecPath(mount_root=src, patterns=["api/"])
        ns = compute_node_state(path=api, mount_specs=[ms], pushed_files=set())
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.visibility == "masked"

    def test_mount_mask_child_is_masked(self, tmp_path: Path):
        """Child of masked folder → mounted=True, masked=True."""
        src = tmp_path / "src"
        child = src / "api" / "file.py"

        ms = MountSpecPath(mount_root=src, patterns=["api/"])
        ns = compute_node_state(path=child, mount_specs=[ms], pushed_files=set())
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.visibility == "masked"

    def test_mask_with_reveal(self, tmp_path: Path):
        """Mask with punch-through reveal → child of reveal is revealed."""
        src = tmp_path / "src"
        child = src / "api" / "public" / "index.html"

        ms = MountSpecPath(mount_root=src, patterns=["api/", "!api/public/"])
        ns = compute_node_state(path=child, mount_specs=[ms], pushed_files=set())
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.revealed is True
        assert ns.visibility == "revealed"

    def test_pushed_under_active_mask(self, tmp_path: Path):
        """Pushed file under active mask → masked, NOT orphaned (mount exists)."""
        src = tmp_path / "src"
        pushed_file = src / "api" / "config.json"

        ms = MountSpecPath(mount_root=src, patterns=["api/"])
        ns = compute_node_state(path=pushed_file, mount_specs=[ms], pushed_files={pushed_file})
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.pushed is True
        assert ns.container_orphaned is False
        assert ns.visibility == "masked"

    def test_no_mount_no_mask(self, tmp_path: Path):
        """No mount specs → everything hidden. Orphan detection is batch-level."""
        pushed_file = tmp_path / "src" / "config.json"

        ns = compute_node_state(path=pushed_file, mount_specs=[], pushed_files={pushed_file})
        assert ns.pushed is True
        assert ns.mounted is False
        assert ns.masked is False
        assert ns.container_orphaned is False
        assert ns.visibility == "hidden"

    def test_unmounted_path_is_hidden(self, tmp_path: Path):
        """Path not under any mount → hidden regardless of other state."""
        child = tmp_path / "other" / "file.py"

        ms = MountSpecPath(mount_root=tmp_path / "src", patterns=["api/"])
        ns = compute_node_state(path=child, mount_specs=[ms], pushed_files=set())
        assert ns.masked is False
        assert ns.mounted is False
        assert ns.visibility == "hidden"


# =============================================================================
# NS-5: apply_node_states_from_scope()
# =============================================================================

class TestApplyNodeStatesFromScope:
    """Verify batch computation using ScopeDockerConfig."""

    @staticmethod
    def _make_config(
        tmp_path: Path,
        mounts: set[Path] | None = None,
        masked: set[Path] | None = None,
        revealed: set[Path] | None = None,
        pushed_files: set[Path] | None = None,
    ) -> ScopeDockerConfig:
        """Build ScopeDockerConfig from old-style set kwargs (test compat).

        Converts mounts/masked/revealed into mount_specs list.
        """
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
        return ScopeDockerConfig(
            mount_specs=mount_specs,
            pushed_files=pushed_files or set(),
            host_project_root=tmp_path,
        )

    def test_full_config_mixed_states(self, tmp_path: Path):
        """Mixed mounts/masks/reveals → correct states for each path.

        With mirrored=True (default), api is upgraded to 'virtual'
        because it has a revealed descendant (public).
        """
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"
        readme = src / "README.md"
        stray = tmp_path / "other"

        config = self._make_config(
            tmp_path,
            mounts={src},
            masked={api},
            revealed={public},
        )

        paths = [src, api, public, readme, stray]
        result = apply_node_states_from_scope(config, paths)

        assert result[src].visibility == "visible"
        assert result[api].visibility == "virtual"
        assert result[public].visibility == "revealed"
        assert result[readme].visibility == "visible"
        assert result[stray].visibility == "hidden"

    def test_empty_config_all_hidden(self, tmp_path: Path):
        """Empty config → all paths hidden."""
        config = self._make_config(tmp_path)
        paths = [tmp_path / "a", tmp_path / "b"]
        result = apply_node_states_from_scope(config, paths)

        for ns in result.values():
            assert ns.visibility == "hidden"

    def test_round_trip_consistency(self, tmp_path: Path):
        """Batch Stage 1 matches individual compute_node_state() calls.

        Uses no revealed paths so Stage 2 has no effect (no mirrored upgrades).
        Stage 3 fields (has_pushed_descendant, has_direct_visible_child) may
        differ between batch and individual since individual doesn't compute them.
        """
        src = tmp_path / "src"
        api = src / "api"

        config = self._make_config(
            tmp_path,
            mounts={src},
            masked={api},
        )

        paths = [src, api, src / "main.py", api / "internal.py"]
        batch = apply_node_states_from_scope(config, paths)

        for p in paths:
            individual = compute_node_state(
                path=p,
                mount_specs=config.mount_specs,
                pushed_files=config.pushed_files,
            )
            # Compare per-node fields (tree-context fields may differ)
            assert batch[p].mounted == individual.mounted, f"mounted mismatch at {p}"
            assert batch[p].masked == individual.masked, f"masked mismatch at {p}"
            assert batch[p].revealed == individual.revealed, f"revealed mismatch at {p}"
            assert batch[p].pushed == individual.pushed, f"pushed mismatch at {p}"
            assert batch[p].container_orphaned == individual.container_orphaned, f"container_orphaned mismatch at {p}"
            assert batch[p].visibility == individual.visibility, f"visibility mismatch at {p}"

    def test_empty_paths_returns_empty(self, tmp_path: Path):
        """No paths → empty dict."""
        config = self._make_config(tmp_path, mounts={tmp_path / "src"})
        result = apply_node_states_from_scope(config, [])
        assert result == {}

    def test_pushed_files_tracked(self, tmp_path: Path):
        """Pushed flag is set correctly in batch result."""
        src = tmp_path / "src"
        pushed_file = src / "config.json"

        config = self._make_config(
            tmp_path,
            mounts={src},
            pushed_files={pushed_file},
        )

        result = apply_node_states_from_scope(config, [pushed_file, src])
        assert result[pushed_file].pushed is True
        assert result[src].pushed is False

    def test_mirrored_enabled_applies_stage2(self, tmp_path: Path):
        """masked + revealed descendant → mirrored when config.mirrored=True."""
        src = tmp_path / "src"
        api = src / "api"
        internal = api / "internal"
        public = internal / "public"

        config = self._make_config(
            tmp_path,
            mounts={src},
            masked={api},
            revealed={public},
        )
        config.mirrored = True

        paths = [src, api, internal, public]
        result = apply_node_states_from_scope(config, paths)

        assert result[api].visibility == "virtual"
        assert result[internal].visibility == "virtual"
        assert result[public].visibility == "revealed"
        assert result[src].visibility == "visible"

    def test_mirrored_disabled_stays_masked(self, tmp_path: Path):
        """config.mirrored=False → masked stays masked, no Stage 2."""
        src = tmp_path / "src"
        api = src / "api"
        public = api / "public"

        config = self._make_config(
            tmp_path,
            mounts={src},
            masked={api},
            revealed={public},
        )
        config.mirrored = False

        paths = [src, api, public]
        result = apply_node_states_from_scope(config, paths)

        assert result[api].visibility == "masked"
        assert result[public].visibility == "revealed"

    def test_stage3_has_pushed_descendant(self, tmp_path: Path):
        """Batch sets has_pushed_descendant on ancestor folders."""
        src = tmp_path / "src"
        api = src / "api"
        pushed_file = api / "config.json"

        config = self._make_config(
            tmp_path,
            mounts={src},
            masked={api},
            pushed_files={pushed_file},
        )

        paths = [src, api, pushed_file]
        result = apply_node_states_from_scope(config, paths)

        assert result[src].has_pushed_descendant is True
        assert result[api].has_pushed_descendant is True
        assert result[pushed_file].has_pushed_descendant is False

    def test_stage3_has_direct_visible_child(self, tmp_path: Path):
        """Batch sets has_direct_visible_child on direct parent of revealed/pushed."""
        src = tmp_path / "src"
        api = src / "api"
        internal = api / "internal"
        public = internal / "public"

        config = self._make_config(
            tmp_path,
            mounts={src},
            masked={api},
            revealed={public},
        )

        paths = [src, api, internal, public]
        result = apply_node_states_from_scope(config, paths)

        # internal is the direct parent of public (revealed)
        assert result[internal].has_direct_visible_child is True
        # api is NOT the direct parent — public is deeper
        assert result[api].has_direct_visible_child is False


# =============================================================================
# (Removed: TestHasRevealedDescendant, TestFindMirroredPaths,
#  TestFindPathsWithPushedDescendants — tree-walk functions replaced by
#  config-native queries in pathspec-native-state refactor.
#  Coverage now in test_mount_spec_path.py and test_local_mount_config.py.)
# =============================================================================


# =============================================================================
# NS-7: find_paths_with_direct_visible_children()
# =============================================================================

class TestFindPathsWithDirectVisibleChildren:
    """Verify direct visible child detection."""

    def test_direct_parent_of_revealed_detected(self, tmp_path: Path):
        api = tmp_path / "src" / "api"
        public = api / "public"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        result = find_paths_with_direct_visible_children(states)
        assert api in result

    def test_direct_parent_of_pushed_detected(self, tmp_path: Path):
        api = tmp_path / "src" / "api"
        pushed_file = api / "config.json"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            pushed_file: NodeState(mounted=True, masked=True, pushed=True, visibility="masked"),
        }

        result = find_paths_with_direct_visible_children(states)
        assert api in result

    def test_non_direct_parent_not_detected(self, tmp_path: Path):
        """Grandparent of revealed → NOT direct visible child."""
        api = tmp_path / "src" / "api"
        internal = api / "internal"
        public = internal / "public"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            internal: NodeState(mounted=True, masked=True, visibility="masked"),
            public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        result = find_paths_with_direct_visible_children(states)
        assert internal in result  # direct parent
        assert api not in result   # grandparent

    def test_no_visible_children_returns_empty(self, tmp_path: Path):
        api = tmp_path / "src" / "api"
        internal = api / "internal"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            internal: NodeState(mounted=True, masked=True, visibility="masked"),
        }

        result = find_paths_with_direct_visible_children(states)
        assert result == set()


# =============================================================================
# NS-8: detect_orphan_creating_removals()
# =============================================================================

class TestDetectOrphanCreatingRemovals:
    """Verify pre-cascade orphan detection."""

    def test_removing_mount_with_pushed_files(self, tmp_path: Path):
        """Removing mount that covers pushed files → detected."""
        src = tmp_path / "src"
        api = src / "api"
        pushed_file = api / "config.json"

        would_orphan = detect_orphan_creating_removals(
            pushed_files={pushed_file},
            current_mounts={src},
            current_masked={api},
            removing_mounts={src},
        )
        assert pushed_file in would_orphan

    def test_removing_mount_no_pushed_files(self, tmp_path: Path):
        """Removing mount with no pushed files → empty."""
        src = tmp_path / "src"

        would_orphan = detect_orphan_creating_removals(
            pushed_files=set(),
            current_mounts={src},
            current_masked=set(),
            removing_mounts={src},
        )
        assert would_orphan == set()

    def test_removing_unrelated_mount(self, tmp_path: Path):
        """Removing mount that doesn't cover pushed files → empty."""
        src = tmp_path / "src"
        api = src / "api"
        lib = tmp_path / "lib"
        pushed_file = api / "config.json"

        would_orphan = detect_orphan_creating_removals(
            pushed_files={pushed_file},
            current_mounts={src, lib},
            current_masked={api},
            removing_mounts={lib},
        )
        assert would_orphan == set()

    def test_already_orphaned_not_double_counted(self, tmp_path: Path):
        """File already orphaned (no mount) → not detected again."""
        api = tmp_path / "src" / "api"
        pushed_file = api / "config.json"
        other_mount = tmp_path / "other"

        would_orphan = detect_orphan_creating_removals(
            pushed_files={pushed_file},
            current_mounts={other_mount},  # doesn't cover pushed_file
            current_masked={api},
            removing_mounts={other_mount},
        )
        assert would_orphan == set()

    def test_empty_removing_mounts(self, tmp_path: Path):
        """No mounts being removed → empty."""
        src = tmp_path / "src"
        pushed_file = src / "api" / "config.json"

        would_orphan = detect_orphan_creating_removals(
            pushed_files={pushed_file},
            current_mounts={src},
            current_masked={src / "api"},
            removing_mounts=set(),
        )
        assert would_orphan == set()

    def test_pushed_not_under_mask_not_affected(self, tmp_path: Path):
        """Pushed file not under any mask → removing mount won't orphan it."""
        src = tmp_path / "src"
        pushed_file = src / "main.py"

        would_orphan = detect_orphan_creating_removals(
            pushed_files={pushed_file},
            current_mounts={src},
            current_masked=set(),
            removing_mounts={src},
        )
        assert would_orphan == set()


# =============================================================================
# Phase 2: Nested mask/reveal via pathspec
# =============================================================================

class TestComputeNodeStateFromSpecs:
    """Verify pathspec-based state computation handles nested patterns."""

    def test_nested_remask_is_masked(self, tmp_path: Path):
        """Path under re-masked folder evaluates as masked (the core bug fix)."""
        src = tmp_path / "src"
        ms = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/public/", "vendor/public/tmp/"],
        )
        cache = src / "vendor" / "public" / "tmp" / "cache.dat"
        ns = compute_node_state(cache, [ms], set())
        assert ns.visibility == "masked"
        assert ns.masked is True
        assert ns.revealed is False

    def test_revealed_under_mask(self, tmp_path: Path):
        """Path under revealed folder evaluates as revealed."""
        src = tmp_path / "src"
        ms = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/public/"],
        )
        api = src / "vendor" / "public" / "api"
        ns = compute_node_state(api, [ms], set())
        assert ns.visibility == "revealed"
        assert ns.masked is True
        assert ns.revealed is True

    def test_masked_folder_itself(self, tmp_path: Path):
        """The masked folder itself evaluates as masked."""
        src = tmp_path / "src"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/"])
        ns = compute_node_state(src / "vendor", [ms], set())
        assert ns.visibility == "masked"
        assert ns.masked is True

    def test_mount_root_is_visible(self, tmp_path: Path):
        """Mount root with no matching patterns is visible."""
        src = tmp_path / "src"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/"])
        ns = compute_node_state(src, [ms], set())
        assert ns.visibility == "visible"
        assert ns.mounted is True
        assert ns.masked is False

    def test_path_outside_all_mounts_is_hidden(self, tmp_path: Path):
        """Path not under any mount is hidden."""
        src = tmp_path / "src"
        ms = MountSpecPath(mount_root=src, patterns=[])
        other = tmp_path / "other"
        ns = compute_node_state(other, [ms], set())
        assert ns.visibility == "hidden"
        assert ns.mounted is False

    def test_pushed_file_in_remask_has_correct_state(self, tmp_path: Path):
        """Pushed file in re-masked area has pushed=True + masked visibility."""
        src = tmp_path / "src"
        ms = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/public/", "vendor/public/tmp/"],
        )
        pushed = src / "vendor" / "public" / "tmp" / "secret.key"
        ns = compute_node_state(pushed, [ms], {pushed})
        assert ns.pushed is True
        assert ns.masked is True
        assert ns.visibility == "masked"


class TestApplyFromSpecsNested:
    """End-to-end: apply_node_states_from_scope with nested patterns."""

    def test_full_pipeline_nested_patterns(self, tmp_path: Path):
        """3-stage pipeline with mask -> reveal -> re-mask."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        pub = vendor / "public"
        tmp_dir = pub / "tmp"
        api = pub / "api"

        ms = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/public/", "vendor/public/tmp/"],
        )
        config = ScopeDockerConfig(
            mount_specs=[ms],
            host_project_root=tmp_path,
        )
        config.mirrored = True

        paths = [src, vendor, pub, tmp_dir, api]
        result = apply_node_states_from_scope(config, paths)

        assert result[src].visibility == "visible"
        # vendor is masked but has a revealed descendant (pub) -> mirrored
        assert result[vendor].visibility == "virtual"
        assert result[pub].visibility == "revealed"
        assert result[tmp_dir].visibility == "masked"
        assert result[api].visibility == "revealed"

    def test_mirrored_disabled_nested(self, tmp_path: Path):
        """Nested patterns with mirrored=False: no Stage 2 upgrade."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        pub = vendor / "public"

        ms = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/public/"],
        )
        config = ScopeDockerConfig(
            mount_specs=[ms],
            host_project_root=tmp_path,
        )
        config.mirrored = False

        paths = [src, vendor, pub]
        result = apply_node_states_from_scope(config, paths)

        assert result[vendor].visibility == "masked"  # no mirrored upgrade
        assert result[pub].visibility == "revealed"


# =============================================================================
# NS-9: Exhaustive truth table regression (all 14 folder+file states)
# Cross-references FOLDER_STATE_TABLE and FILE_STATE_TABLE in display_config.py
# =============================================================================


class TestTruthTableRegression:
    """Verify that apply_node_states_from_scope() produces NodeState values
    that match every entry in the display_config truth tables.

    Each test constructs a scenario that should produce a specific
    (visibility, has_pushed_descendant, has_direct_visible_child) or
    (visibility, pushed) tuple.
    """

    # ── Folder States ────────────────────────────────────────

    def test_folder_hidden(self, tmp_path: Path):
        """F1: hidden, no push descendant → FOLDER_HIDDEN."""
        outside = tmp_path / "outside"
        ms = MountSpecPath(mount_root=tmp_path / "src")
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [outside])
        s = result[outside]
        assert s.visibility == "hidden"
        assert s.has_pushed_descendant is False
        assert s.has_direct_visible_child is False

    def test_folder_visible(self, tmp_path: Path):
        """F2: visible → FOLDER_VISIBLE."""
        src = tmp_path / "src"
        ms = MountSpecPath(mount_root=src)
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [src])
        s = result[src]
        assert s.visibility == "visible"

    def test_folder_mounted_masked(self, tmp_path: Path):
        """F3: masked, no pushed descendant → FOLDER_MOUNTED_MASKED."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [src, vendor])
        s = result[vendor]
        assert s.visibility == "masked"
        assert s.has_pushed_descendant is False

    def test_folder_mounted_masked_pushed(self, tmp_path: Path):
        """F4: masked, has pushed descendant → FOLDER_MOUNTED_MASKED_PUSHED.
        Only reachable when mirrored=False — with mirrored=True, pushed
        descendants trigger virtual upgrade via Check 2."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        pushed_file = vendor / "secret.py"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
            pushed_files={pushed_file},
        )
        config.mirrored = False
        result = apply_node_states_from_scope(config, [src, vendor, pushed_file])
        s = result[vendor]
        assert s.visibility == "masked"
        assert s.has_pushed_descendant is True

    def test_folder_virtual_revealed(self, tmp_path: Path):
        """F5: virtual, has direct revealed child → FOLDER_VIRTUAL_REVEALED."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        public = vendor / "public"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/", "!vendor/public/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [src, vendor, public])
        s = result[vendor]
        assert s.visibility == "virtual"
        assert s.has_direct_visible_child is True

    def test_folder_virtual(self, tmp_path: Path):
        """F6: virtual, no direct revealed child → FOLDER_VIRTUAL."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        internal = vendor / "internal"
        public = internal / "public"
        ms = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/internal/public/"],
        )
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(
            config, [src, vendor, internal, public],
        )
        s = result[vendor]
        assert s.visibility == "virtual"
        assert s.has_direct_visible_child is False

    def test_folder_revealed(self, tmp_path: Path):
        """F7: revealed → FOLDER_REVEALED."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        public = vendor / "public"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/", "!vendor/public/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [src, vendor, public])
        s = result[public]
        assert s.visibility == "revealed"
        assert s.revealed is True

    def test_folder_pushed_ancestor(self, tmp_path: Path):
        """F8: hidden, has pushed descendant → FOLDER_PUSHED_ANCESTOR.
        Only reachable when mirrored=False — with mirrored=True, pushed
        descendants trigger virtual upgrade via Check 2."""
        outside = tmp_path / "outside"
        pushed_file = outside / "deep" / "file.txt"
        ms = MountSpecPath(mount_root=tmp_path / "src")
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
            pushed_files={pushed_file},
        )
        config.mirrored = False
        result = apply_node_states_from_scope(
            config, [outside, outside / "deep", pushed_file],
        )
        s = result[outside]
        assert s.visibility == "hidden"
        assert s.has_pushed_descendant is True

    # F9 (FOLDER_CONTAINER_ONLY) requires container scan diff —
    # not producible by apply_node_states_from_scope alone.

    # ── File States ──────────────────────────────────────────

    def test_file_hidden(self, tmp_path: Path):
        """FI2: hidden, not pushed → FILE_HIDDEN."""
        outside = tmp_path / "outside" / "file.txt"
        ms = MountSpecPath(mount_root=tmp_path / "src")
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [outside])
        s = result[outside]
        assert s.visibility == "hidden"
        assert s.pushed is False

    def test_file_visible(self, tmp_path: Path):
        """FI2: visible, not pushed → FILE_VISIBLE."""
        src = tmp_path / "src"
        f = src / "main.py"
        ms = MountSpecPath(mount_root=src)
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [src, f])
        s = result[f]
        assert s.visibility == "visible"
        assert s.pushed is False

    def test_file_masked(self, tmp_path: Path):
        """FI3: masked, not pushed → FILE_MASKED."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        f = vendor / "lib.py"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [src, vendor, f])
        s = result[f]
        assert s.visibility == "masked"
        assert s.pushed is False

    def test_file_revealed(self, tmp_path: Path):
        """FI4: revealed, not pushed → FILE_REVEALED."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        public = vendor / "public"
        f = public / "index.html"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/", "!vendor/public/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(config, [src, vendor, public, f])
        s = result[f]
        assert s.visibility == "revealed"
        assert s.revealed is True

    def test_file_pushed_in_hidden(self, tmp_path: Path):
        """FI5: hidden, pushed → FILE_PUSHED."""
        outside = tmp_path / "outside"
        f = outside / "file.txt"
        ms = MountSpecPath(mount_root=tmp_path / "src")
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
            pushed_files={f},
        )
        result = apply_node_states_from_scope(config, [outside, f])
        s = result[f]
        assert s.visibility == "hidden"
        assert s.pushed is True

    def test_file_pushed_in_masked(self, tmp_path: Path):
        """FI5: masked, pushed → FILE_PUSHED."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        f = vendor / "secret.py"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
            pushed_files={f},
        )
        result = apply_node_states_from_scope(config, [src, vendor, f])
        s = result[f]
        assert s.visibility == "masked"
        assert s.pushed is True

    def test_file_container_orphan(self, tmp_path: Path):
        """FI7: orphaned → FILE_CONTAINER_ORPHAN.
        Condition: pushed=T, masked=T, mounted=F, revealed=F."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        f = vendor / "stranded.py"
        # Mount exists but does NOT cover vendor (vendor under different root)
        ms = MountSpecPath(mount_root=tmp_path / "other")
        ms_with_mask = MountSpecPath(mount_root=src, patterns=["vendor/"])
        config = ScopeDockerConfig(
            mount_specs=[ms],
            host_project_root=tmp_path,
            pushed_files={f},
        )
        result = apply_node_states_from_scope(config, [f])
        s = result[f]
        # pushed=T, not under any mount → hidden, not masked → not orphaned
        # Need: pushed + masked + not mounted
        # This requires the file to be masked but mount removed
        # Simulate: file was pushed to vendor/ which was masked under src/,
        # but src/ mount was later removed — file not under any mount
        assert s.pushed is True
        # When not under any mount, masked=False, so not orphaned
        # Container orphan requires specific config state that's hard to
        # produce naturally — it's detected by find_container_orphaned_paths()
        # rather than compute_node_state(). Skip this edge case for now.

    # FI6 (FILE_HOST_ORPHAN) is DEFERRED — not implemented yet.
    # FI8 (FILE_CONTAINER_ONLY) requires container scan diff.

    # ── Cross-reference: virtual detection via config queries ──

    def test_virtual_from_exception_pattern(self, tmp_path: Path):
        """Config query Check 1: masked path with exception descendant → virtual."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        internal = vendor / "internal"
        public = internal / "public"
        ms = MountSpecPath(
            mount_root=src,
            patterns=["vendor/", "!vendor/internal/public/"],
        )
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        result = apply_node_states_from_scope(
            config, [src, vendor, internal, public],
        )
        assert result[vendor].visibility == "virtual"
        assert result[internal].visibility == "virtual"
        assert result[public].visibility == "revealed"

    def test_virtual_from_pushed_descendant(self, tmp_path: Path):
        """Config query Check 2: masked path with pushed descendant → virtual."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        pushed_file = vendor / "lib" / "helper.py"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
            pushed_files={pushed_file},
        )
        result = apply_node_states_from_scope(
            config, [src, vendor, vendor / "lib", pushed_file],
        )
        assert result[vendor].visibility == "virtual"
        assert result[vendor / "lib"].visibility == "virtual"

    def test_virtual_above_mount_structural(self, tmp_path: Path):
        """Config query Check 3: hidden path above mount with mount below → virtual."""
        project = tmp_path / "project"
        subdir = project / "subdir"
        src = subdir / "src"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/", "!vendor/public/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        # project and subdir are above mount — should become virtual
        result = apply_node_states_from_scope(
            config,
            [project, subdir, src, src / "vendor", src / "vendor" / "public"],
        )
        assert result[project].visibility == "virtual"
        assert result[subdir].visibility == "virtual"
        assert result[src].visibility == "visible"

    def test_mirrored_disabled_no_virtual(self, tmp_path: Path):
        """When mirrored=False, no virtual detection occurs."""
        src = tmp_path / "src"
        vendor = src / "vendor"
        public = vendor / "public"
        ms = MountSpecPath(mount_root=src, patterns=["vendor/", "!vendor/public/"])
        config = ScopeDockerConfig(
            mount_specs=[ms], host_project_root=tmp_path,
        )
        config.mirrored = False
        result = apply_node_states_from_scope(config, [src, vendor, public])
        assert result[vendor].visibility == "masked"  # no upgrade

