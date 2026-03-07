"""Tests for core/node_state.py — NodeState dataclass and visibility functions.

Covers:
  NS-2: NodeState dataclass + compute_visibility()
  NS-3: find_container_orphaned_paths()
  NS-4: compute_node_state()
  NS-5: apply_node_states_from_scope()
  NS-6: find_paths_with_pushed_descendants()
  NS-7: find_paths_with_direct_visible_children()
  NS-8: detect_orphan_creating_removals()
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.node_state import (
    NodeState,
    compute_visibility,
    find_container_orphaned_paths,
    has_revealed_descendant,
    find_mirrored_paths,
    find_paths_with_pushed_descendants,
    find_paths_with_direct_visible_children,
    detect_orphan_creating_removals,
    compute_node_state,
    apply_node_states_from_scope,
)
from IgnoreScope.core.config import ScopeDockerConfig


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
            mounts={src},
            masked=set(),
            revealed=set(),
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
            mounts={src},
            masked={api},
            revealed=set(),
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
            mounts={src},
            masked={api},
            revealed={public},
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
            mounts={tmp_path / "src"},
            masked=set(),
            revealed=set(),
            pushed_files=set(),
        )
        assert ns.mounted is False
        assert ns.visibility == "hidden"

    def test_pushed_under_removed_mount_is_orphaned(self, tmp_path: Path):
        """TTFF: pushed=T, masked=T, mounted=F, revealed=F → container_orphaned."""
        api = tmp_path / "src" / "api"
        pushed_file = api / "config.json"

        ns = compute_node_state(
            path=pushed_file,
            mounts=set(),
            masked={api},
            revealed=set(),
            pushed_files={pushed_file},
        )
        assert ns.pushed is True
        assert ns.masked is True
        assert ns.mounted is False
        assert ns.revealed is False
        assert ns.container_orphaned is True
        assert ns.visibility == "orphaned"

    def test_mount_point_itself_is_visible(self, tmp_path: Path):
        src = tmp_path / "src"

        ns = compute_node_state(
            path=src,
            mounts={src},
            masked=set(),
            revealed=set(),
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.visibility == "visible"

    def test_mask_point_itself_is_masked(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"

        ns = compute_node_state(
            path=api,
            mounts={src},
            masked={api},
            revealed=set(),
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
            mounts={src},
            masked={api},
            revealed={public},
            pushed_files=set(),
        )
        assert ns.revealed is True
        assert ns.visibility == "revealed"

    # --- Mount-root-mask (dual state) ---

    def test_mount_root_mask_same_path(self, tmp_path: Path):
        """Path in both mounts AND masked → mounted=True, masked=True, visibility=masked."""
        src = tmp_path / "src"

        ns = compute_node_state(
            path=src,
            mounts={src},
            masked={src},
            revealed=set(),
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.visibility == "masked"

    def test_mount_root_mask_child_is_masked(self, tmp_path: Path):
        """Child of mount-root-mask → mounted=True, masked=True."""
        src = tmp_path / "src"
        child = src / "file.py"

        ns = compute_node_state(
            path=child,
            mounts={src},
            masked={src},
            revealed=set(),
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.visibility == "masked"

    def test_mount_root_mask_with_reveal(self, tmp_path: Path):
        """Mount-root-mask with punch-through reveal."""
        src = tmp_path / "src"
        public = src / "public"
        child = public / "index.html"

        ns = compute_node_state(
            path=child,
            mounts={src},
            masked={src},
            revealed={public},
            pushed_files=set(),
        )
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.revealed is True
        assert ns.visibility == "revealed"

    def test_mount_root_mask_pushed_under_active_mount(self, tmp_path: Path):
        """Pushed file under active mount-root-mask → masked, NOT orphaned."""
        src = tmp_path / "src"
        pushed_file = src / "config.json"

        ns = compute_node_state(
            path=pushed_file,
            mounts={src},
            masked={src},
            pushed_files={pushed_file},
            revealed=set(),
        )
        assert ns.mounted is True
        assert ns.masked is True
        assert ns.pushed is True
        assert ns.container_orphaned is False
        assert ns.visibility == "masked"

    def test_mount_root_mask_mount_removed_orphan(self, tmp_path: Path):
        """TTFF on mount-root-mask after mount removed → container_orphaned."""
        src = tmp_path / "src"
        pushed_file = src / "config.json"

        ns = compute_node_state(
            path=pushed_file,
            mounts=set(),       # mount removed
            masked={src},       # mask volume still exists
            revealed=set(),
            pushed_files={pushed_file},
        )
        assert ns.pushed is True
        assert ns.masked is True
        assert ns.mounted is False
        assert ns.revealed is False
        assert ns.container_orphaned is True
        assert ns.visibility == "orphaned"

    def test_masked_without_mount_is_hidden(self, tmp_path: Path):
        """GAP 1: masked=T but mounted=F (stale config) → hidden, not masked."""
        api = tmp_path / "src" / "api"
        child = api / "file.py"

        ns = compute_node_state(
            path=child,
            mounts=set(),
            masked={api},
            revealed=set(),
            pushed_files=set(),
        )
        assert ns.masked is True
        assert ns.mounted is False
        assert ns.visibility == "hidden"


# =============================================================================
# NS-5: apply_node_states_from_scope()
# =============================================================================

class TestApplyNodeStatesFromScope:
    """Verify batch computation using ScopeDockerConfig."""

    def _make_config(
        self,
        tmp_path: Path,
        mounts: set[Path] | None = None,
        masked: set[Path] | None = None,
        revealed: set[Path] | None = None,
        pushed_files: set[Path] | None = None,
    ) -> ScopeDockerConfig:
        return ScopeDockerConfig(
            mounts=mounts or set(),
            masked=masked or set(),
            revealed=revealed or set(),
            pushed_files=pushed_files or set(),
            host_project_root=tmp_path,
        )

    def test_full_config_mixed_states(self, tmp_path: Path):
        """Mixed mounts/masks/reveals → correct states for each path.

        With mirrored=True (default), api is upgraded to 'mirrored'
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
        assert result[api].visibility == "mirrored"
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
                mounts=config.mounts,
                masked=config.masked,
                revealed=config.revealed,
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

        assert result[api].visibility == "mirrored"
        assert result[internal].visibility == "mirrored"
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

    def test_mirrored_upgrades_hidden_intermediates(self, tmp_path: Path):
        """Hidden ancestors of mounted paths → mirrored (bug fix).

        Mount tree: root/a/b/c/ where only c/ is mounted.
        a/ and b/ are hidden intermediates — Stage 2 must upgrade them.
        """
        a = tmp_path / "a"
        b = a / "b"
        c = b / "c"

        config = self._make_config(
            tmp_path,
            mounts={c},
        )
        config.mirrored = True

        paths = [a, b, c]
        result = apply_node_states_from_scope(config, paths)

        assert result[c].visibility == "visible"
        assert result[a].visibility == "mirrored"
        assert result[b].visibility == "mirrored"

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
# Stage 2: has_revealed_descendant()
# =============================================================================

class TestHasRevealedDescendant:
    """Verify descendant-walk logic for mirrored detection."""

    def test_descendant_revealed_returns_true(self, tmp_path: Path):
        """Reveal is child of path → True."""
        api = tmp_path / "src" / "api"
        public = api / "public"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        assert has_revealed_descendant(api, states) is True

    def test_no_descendants_returns_false(self, tmp_path: Path):
        """Masked dir, no reveals below → False."""
        api = tmp_path / "src" / "api"
        internal = api / "internal"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            internal: NodeState(mounted=True, masked=True, visibility="masked"),
        }

        assert has_revealed_descendant(api, states) is False

    def test_self_revealed_returns_false(self, tmp_path: Path):
        """Path itself is revealed — not a descendant of itself."""
        public = tmp_path / "src" / "api" / "public"

        states = {
            public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        assert has_revealed_descendant(public, states) is False

    def test_non_descendant_revealed_returns_false(self, tmp_path: Path):
        """Reveal in different subtree → False."""
        src = tmp_path / "src"
        api = src / "api"
        vendor = src / "vendor"
        vendor_public = vendor / "public"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            vendor_public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        assert has_revealed_descendant(api, states) is False

    def test_deep_descendant(self, tmp_path: Path):
        """Reveal several levels deep → True."""
        api = tmp_path / "src" / "api"
        deep = api / "internal" / "handlers" / "public"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            deep: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        assert has_revealed_descendant(api, states) is True


# =============================================================================
# Stage 2: find_mirrored_paths()
# =============================================================================

class TestFindMirroredPaths:
    """Verify mirrored path detection."""

    def test_masked_with_revealed_descendant_is_mirrored(self, tmp_path: Path):
        api = tmp_path / "src" / "api"
        public = api / "public"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        result = find_mirrored_paths(states)
        assert api in result

    def test_masked_without_descendant_not_mirrored(self, tmp_path: Path):
        api = tmp_path / "src" / "api"
        internal = api / "internal"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            internal: NodeState(mounted=True, masked=True, visibility="masked"),
        }

        result = find_mirrored_paths(states)
        assert result == set()

    def test_revealed_node_not_mirrored(self, tmp_path: Path):
        """Visibility is 'revealed', not 'masked' → not mirrored."""
        public = tmp_path / "src" / "api" / "public"
        child = public / "index.html"

        states = {
            public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
            child: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        result = find_mirrored_paths(states)
        assert result == set()

    def test_multiple_mirrored_paths(self, tmp_path: Path):
        """Several intermediates between mask and reveal."""
        api = tmp_path / "src" / "api"
        internal = api / "internal"
        handlers = internal / "handlers"
        public = handlers / "public"

        states = {
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            internal: NodeState(mounted=True, masked=True, visibility="masked"),
            handlers: NodeState(mounted=True, masked=True, visibility="masked"),
            public: NodeState(mounted=True, masked=True, revealed=True, visibility="revealed"),
        }

        result = find_mirrored_paths(states)
        assert api in result
        assert internal in result
        assert handlers in result
        assert public not in result

    def test_hidden_intermediate_with_visible_descendant(self, tmp_path: Path):
        """Hidden intermediate ancestors of mounted child → mirrored.

        Bug trace: Mount ProjectRoot/a/b/c/ with no masks.
        Walk 2 computes a/, b/ as hidden intermediates.
        c/ is visible (mounted). Old code skipped hidden nodes.
        Fix: truth table upgrades hidden intermediates too.
        """
        root = tmp_path
        a = root / "a"
        b = a / "b"
        c = b / "c"

        states = {
            a: NodeState(visibility="hidden"),
            b: NodeState(visibility="hidden"),
            c: NodeState(mounted=True, visibility="visible"),
        }

        result = find_mirrored_paths(states)
        assert a in result, "hidden intermediate 'a' should be mirrored"
        assert b in result, "hidden intermediate 'b' should be mirrored"
        assert c not in result, "visible leaf 'c' should NOT be mirrored"

    def test_hidden_intermediate_with_pushed_descendant(self, tmp_path: Path):
        """Hidden intermediate with pushed descendant → mirrored."""
        root = tmp_path
        a = root / "a"
        b = a / "b"
        pushed_file = b / "config.json"

        states = {
            a: NodeState(visibility="hidden"),
            b: NodeState(visibility="hidden"),
            pushed_file: NodeState(pushed=True, visibility="hidden"),
        }

        result = find_mirrored_paths(states)
        assert a in result
        assert b in result
        assert pushed_file not in result

    def test_empty_states_returns_empty(self):
        result = find_mirrored_paths({})
        assert result == set()


# =============================================================================
# NS-6: find_paths_with_pushed_descendants()
# =============================================================================

class TestFindPathsWithPushedDescendants:
    """Verify pushed descendant detection."""

    def test_ancestor_of_pushed_file_detected(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"
        pushed_file = api / "config.json"

        states = {
            src: NodeState(mounted=True, visibility="visible"),
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            pushed_file: NodeState(mounted=True, masked=True, pushed=True, visibility="masked"),
        }

        result = find_paths_with_pushed_descendants(states)
        assert src in result
        assert api in result
        assert pushed_file not in result

    def test_no_pushed_files_returns_empty(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"

        states = {
            src: NodeState(mounted=True, visibility="visible"),
            api: NodeState(mounted=True, masked=True, visibility="masked"),
        }

        result = find_paths_with_pushed_descendants(states)
        assert result == set()

    def test_pushed_file_itself_not_included(self, tmp_path: Path):
        pushed_file = tmp_path / "src" / "file.py"

        states = {
            pushed_file: NodeState(pushed=True, visibility="masked"),
        }

        result = find_paths_with_pushed_descendants(states)
        assert result == set()

    def test_non_ancestor_not_included(self, tmp_path: Path):
        src = tmp_path / "src"
        api = src / "api"
        vendor = src / "vendor"
        pushed_file = api / "config.json"

        states = {
            src: NodeState(mounted=True, visibility="visible"),
            api: NodeState(mounted=True, masked=True, visibility="masked"),
            vendor: NodeState(mounted=True, masked=True, visibility="masked"),
            pushed_file: NodeState(mounted=True, masked=True, pushed=True, visibility="masked"),
        }

        result = find_paths_with_pushed_descendants(states)
        assert src in result
        assert api in result
        assert vendor not in result  # vendor is sibling, not ancestor


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

