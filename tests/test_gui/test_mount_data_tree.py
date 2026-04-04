"""Phase 2 tests: MountDataTree sibling hosting.

Tests that MountDataTree correctly loads sibling subtrees from config,
merges sibling sets into unified raw sets, extracts per-sibling state
via get_sibling_configs(), and excludes sibling paths from project data.

No Docker or Qt GUI required — MountDataTree is a QObject but only
needs a QApplication instance for signal/slot wiring.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from IgnoreScope.core.config import SiblingMount
from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.gui.mount_data_tree import MountDataTree, MountDataNode, NodeSource


def _make_sibling(
    host_path: Path,
    container_path: str,
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
    pushed_files: set[Path] | None = None,
) -> SiblingMount:
    """Build SiblingMount from old-style set kwargs (test compat helper).

    Converts mounts/masked/revealed sets into mount_specs list.
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
    return SiblingMount(
        host_path=host_path,
        container_path=container_path,
        mount_specs=mount_specs,
        pushed_files=pushed_files or set(),
    )


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _qapp():
    """Ensure QApplication exists for QObject-based MountDataTree."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a project directory with some subdirs and files."""
    project = tmp_path / "MyProject"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").touch()
    (project / "Content").mkdir()
    (project / "Content" / "texture.png").touch()
    return project


@pytest.fixture
def sibling_dir(tmp_path: Path) -> Path:
    """Create a sibling directory with some subdirs and files."""
    sib = tmp_path / "SharedLib"
    sib.mkdir()
    (sib / "common").mkdir()
    (sib / "common" / "utils.py").touch()
    (sib / "internal").mkdir()
    (sib / "internal" / "secret.py").touch()
    return sib


@pytest.fixture
def second_sibling_dir(tmp_path: Path) -> Path:
    """Create a second sibling directory."""
    sib2 = tmp_path / "OtherLib"
    sib2.mkdir()
    (sib2 / "tools").mkdir()
    (sib2 / "tools" / "build.py").touch()
    return sib2


@pytest.fixture
def tree(project_dir: Path) -> MountDataTree:
    """Create a MountDataTree with project root set."""
    t = MountDataTree()
    t.set_host_project_root(project_dir)
    return t


def _make_config(
    project_dir: Path,
    siblings: list[SiblingMount] | None = None,
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
    pushed_files: set[Path] | None = None,
) -> SimpleNamespace:
    """Build a config namespace matching ScopeDockerConfig's duck-typed interface."""
    # Build mount_specs from old-style sets
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
    return SimpleNamespace(
        mount_specs=mount_specs,
        mounts=mounts or set(),
        masked=masked or set(),
        revealed=revealed or set(),
        pushed_files=pushed_files or set(),
        container_files=set(),
        mirrored=True,
        siblings=siblings or [],
    )


# ── Test: load_config with siblings ──────────────────────────────

class TestLoadConfigWithSiblings:
    """Test that load_config() creates sibling subtrees in root_node."""

    def test_sibling_nodes_populated(self, tree, project_dir, sibling_dir):
        """_sibling_nodes list is populated after load_config with siblings."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
        )
        config = _make_config(project_dir, siblings=[sibling])

        tree.load_config(config)

        assert len(tree._sibling_nodes) == 1
        assert tree._sibling_nodes[0].path == sibling_dir
        assert tree._sibling_nodes[0].source == NodeSource.SIBLING

    def test_sibling_appended_to_root_children(self, tree, project_dir, sibling_dir):
        """Sibling root node appears in root_node.children."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
        )
        config = _make_config(project_dir, siblings=[sibling])

        tree.load_config(config)

        root_children = tree.root_node.children
        sibling_children = [c for c in root_children if c.source == NodeSource.SIBLING]
        project_children = [c for c in root_children if c.source == NodeSource.PROJECT]

        assert len(sibling_children) == 1
        assert sibling_children[0].path == sibling_dir
        assert sibling_children[0].container_path == "/shared"
        assert len(project_children) > 0  # project dirs still present

    def test_sibling_children_loaded(self, tree, project_dir, sibling_dir):
        """Sibling root's filesystem children are loaded."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
        )
        config = _make_config(project_dir, siblings=[sibling])

        tree.load_config(config)

        sib_node = tree._sibling_nodes[0]
        assert sib_node.children_loaded
        child_names = {c.name for c in sib_node.children}
        assert "common" in child_names
        assert "internal" in child_names

    def test_sibling_children_inherit_source(self, tree, project_dir, sibling_dir):
        """Children of sibling root inherit NodeSource.SIBLING."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
        )
        config = _make_config(project_dir, siblings=[sibling])

        tree.load_config(config)

        sib_node = tree._sibling_nodes[0]
        for child in sib_node.children:
            assert child.source == NodeSource.SIBLING

    def test_sibling_sets_merged(self, tree, project_dir, sibling_dir):
        """Sibling mounts/masked/revealed/pushed merge into unified raw sets."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
            masked={sibling_dir / "common" / "internal"},
            revealed={sibling_dir / "common" / "internal" / "api"},
            pushed_files={sibling_dir / "common" / "utils.py"},
        )
        config = _make_config(
            project_dir,
            mounts={project_dir / "src"},
            siblings=[sibling],
        )

        tree.load_config(config)

        # Project + sibling mounts merged
        assert project_dir / "src" in tree.mounts
        assert sibling_dir / "common" in tree.mounts
        # Sibling-specific sets present
        assert sibling_dir / "common" / "internal" in tree.masked
        assert sibling_dir / "common" / "internal" / "api" in tree.revealed
        assert sibling_dir / "common" / "utils.py" in tree._pushed_files

    def test_multiple_siblings(self, tree, project_dir, sibling_dir, second_sibling_dir):
        """Multiple siblings all load correctly."""
        sib1 = _make_sibling(host_path=sibling_dir, container_path="/shared")
        sib2 = _make_sibling(host_path=second_sibling_dir, container_path="/other")
        config = _make_config(project_dir, siblings=[sib1, sib2])

        tree.load_config(config)

        assert len(tree._sibling_nodes) == 2
        sib_paths = {s.path for s in tree._sibling_nodes}
        assert sibling_dir in sib_paths
        assert second_sibling_dir in sib_paths

    def test_reload_replaces_old_siblings(self, tree, project_dir, sibling_dir, second_sibling_dir):
        """Reloading config replaces old siblings, doesn't accumulate."""
        sib1 = _make_sibling(host_path=sibling_dir, container_path="/shared")
        config1 = _make_config(project_dir, siblings=[sib1])
        tree.load_config(config1)
        assert len(tree._sibling_nodes) == 1

        sib2 = _make_sibling(host_path=second_sibling_dir, container_path="/other")
        config2 = _make_config(project_dir, siblings=[sib2])
        tree.load_config(config2)

        assert len(tree._sibling_nodes) == 1
        assert tree._sibling_nodes[0].path == second_sibling_dir
        # Old sibling should be removed from root_node.children
        sib_children = [c for c in tree.root_node.children if c.source == NodeSource.SIBLING]
        assert len(sib_children) == 1

    def test_no_siblings_in_config(self, tree, project_dir):
        """Config without siblings works unchanged."""
        config = _make_config(
            project_dir,
            mounts={project_dir / "src"},
        )

        tree.load_config(config)

        assert len(tree._sibling_nodes) == 0
        assert project_dir / "src" in tree.mounts


# ── Test: get_sibling_configs round-trip ─────────────────────────

class TestGetSiblingConfigsRoundTrip:
    """Test that siblings loaded via load_config can be extracted back."""

    def test_round_trip_preserves_data(self, tree, project_dir, sibling_dir):
        """load → get_sibling_configs → matches original sibling data."""
        original = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
            masked={sibling_dir / "common" / "internal"},
            pushed_files={sibling_dir / "common" / "utils.py"},
        )
        config = _make_config(project_dir, siblings=[original])

        tree.load_config(config)
        extracted = tree.get_sibling_configs()

        assert len(extracted) == 1
        sib = extracted[0]
        assert sib.host_path == original.host_path
        assert sib.container_path == original.container_path
        assert sib.mounts == original.mounts
        assert sib.masked == original.masked
        assert sib.pushed_files == original.pushed_files

    def test_round_trip_multiple_siblings(
        self, tree, project_dir, sibling_dir, second_sibling_dir,
    ):
        """Multiple siblings round-trip correctly with isolated sets."""
        sib1 = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
        )
        sib2 = _make_sibling(
            host_path=second_sibling_dir,
            container_path="/other",
            mounts={second_sibling_dir / "tools"},
        )
        config = _make_config(project_dir, siblings=[sib1, sib2])

        tree.load_config(config)
        extracted = tree.get_sibling_configs()

        assert len(extracted) == 2
        by_path = {s.host_path: s for s in extracted}
        assert by_path[sibling_dir].mounts == {sibling_dir / "common"}
        assert by_path[second_sibling_dir].mounts == {second_sibling_dir / "tools"}

    def test_empty_siblings_returns_empty(self, tree, project_dir):
        """No siblings loaded → get_sibling_configs returns empty list."""
        config = _make_config(project_dir)
        tree.load_config(config)

        assert tree.get_sibling_configs() == []


# ── Test: build_config extracts siblings from tree ───────────────

class TestBuildConfigExtractsSiblings:
    """Test that build_config() gets siblings from tree, not parameters."""

    def test_build_config_includes_siblings(self, tree, project_dir, sibling_dir):
        """build_config() returns siblings extracted from tree state."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
        )
        config = _make_config(
            project_dir,
            mounts={project_dir / "src"},
            siblings=[sibling],
        )
        tree.load_config(config)

        tree.container_root = "/workspace"
        result = tree.build_config(
            scope_name="test",
            dev_mode=True,
        )

        assert len(result.siblings) == 1
        assert result.siblings[0].host_path == sibling_dir
        assert result.siblings[0].container_path == "/shared"
        assert result.siblings[0].mounts == {sibling_dir / "common"}

    def test_build_config_no_siblings_param(self, tree, project_dir):
        """build_config() signature has no siblings parameter."""
        import inspect
        sig = inspect.signature(tree.build_config)
        assert "siblings" not in sig.parameters


# ── Test: sibling state computation ──────────────────────────────

class TestSiblingStateComputation:
    """Test that sibling paths get correct NodeState from CORE."""

    def test_sibling_mounted_path_has_mounted_state(self, tree, project_dir, sibling_dir):
        """A sibling path in mounts set gets mounted=True from CORE."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
        )
        config = _make_config(project_dir, siblings=[sibling])

        tree.load_config(config)

        state = tree.get_node_state(sibling_dir / "common")
        assert state.mounted is True

    def test_sibling_masked_path_has_masked_state(self, tree, project_dir, sibling_dir):
        """A sibling path in masked set gets masked=True from CORE."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
            masked={sibling_dir / "common" / "internal"},
        )
        config = _make_config(project_dir, siblings=[sibling])

        tree.load_config(config)

        state = tree.get_node_state(sibling_dir / "common" / "internal")
        assert state.masked is True

    def test_project_and_sibling_states_independent(self, tree, project_dir, sibling_dir):
        """Project and sibling paths compute independently."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
        )
        config = _make_config(
            project_dir,
            mounts={project_dir / "src"},
            siblings=[sibling],
        )

        tree.load_config(config)

        project_state = tree.get_node_state(project_dir / "src")
        sibling_state = tree.get_node_state(sibling_dir / "common")
        assert project_state.mounted is True
        assert sibling_state.mounted is True
        # Non-mounted paths stay default
        default_state = tree.get_node_state(project_dir / "Content")
        assert default_state.mounted is False


# ── Test: get_config_data excludes siblings ──────────────────────

class TestGetConfigDataExcludesSiblings:
    """Test that get_config_data() only returns project-root paths."""

    def test_sibling_mounts_excluded(self, tree, project_dir, sibling_dir):
        """Sibling mount paths do not appear in get_config_data()."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
        )
        config = _make_config(
            project_dir,
            mounts={project_dir / "src"},
            siblings=[sibling],
        )

        tree.load_config(config)

        data = tree.get_config_data()
        project_roots = {ms.mount_root for ms in data['mount_specs']}
        assert project_dir / "src" in project_roots
        assert sibling_dir / "common" not in project_roots

    def test_sibling_pushed_files_excluded(self, tree, project_dir, sibling_dir):
        """Sibling pushed files do not appear in get_config_data()."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            pushed_files={sibling_dir / "common" / "utils.py"},
        )
        config = _make_config(
            project_dir,
            pushed_files={project_dir / "src" / "main.py"},
            siblings=[sibling],
        )

        tree.load_config(config)

        data = tree.get_config_data()
        assert project_dir / "src" / "main.py" in data['pushed_files']
        assert sibling_dir / "common" / "utils.py" not in data['pushed_files']

    def test_config_data_includes_pushed_files_key(self, tree, project_dir):
        """get_config_data() now includes pushed_files in the returned dict."""
        config = _make_config(project_dir)
        tree.load_config(config)

        data = tree.get_config_data()
        assert 'pushed_files' in data


# ── Test: toggle on sibling path ─────────────────────────────────

class TestToggleOnSiblingPath:
    """Test that toggle operations on sibling paths extract correctly."""

    def test_toggle_mount_on_sibling_path(self, tree, project_dir, sibling_dir):
        """Toggling mount on a sibling path → extracted in get_sibling_configs."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
        )
        config = _make_config(project_dir, siblings=[sibling])
        tree.load_config(config)

        # Toggle mount on a sibling subdirectory
        tree.toggle_mounted(sibling_dir / "common", True)

        extracted = tree.get_sibling_configs()
        assert sibling_dir / "common" in extracted[0].mounts

        # Project data should NOT contain this path
        data = tree.get_config_data()
        project_roots = {ms.mount_root for ms in data['mount_specs']}
        assert sibling_dir / "common" not in project_roots

    def test_add_mask_on_sibling_path(self, tree, project_dir, sibling_dir):
        """Adding mask on sibling path → extracted to correct sibling."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
            mounts={sibling_dir / "common"},
        )
        config = _make_config(project_dir, siblings=[sibling])
        tree.load_config(config)

        tree.add_mask(sibling_dir / "common" / "internal")

        extracted = tree.get_sibling_configs()
        assert sibling_dir / "common" / "internal" in extracted[0].masked


# ═══════════════════════════════════════════════════════════════════
# Phase 3 tests: Sibling UX Workflow
# ═══════════════════════════════════════════════════════════════════


# ── Test: _derive_container_path ─────────────────────────────────

class TestDeriveContainerPath:
    """Test config_manager._derive_container_path collision handling."""

    def test_no_collision(self, tree, project_dir, sibling_dir):
        """First sibling gets {container_root}/{name} with no suffix."""
        config = _make_config(project_dir)
        tree.load_config(config)
        tree.container_root = "/workspace"

        from IgnoreScope.gui.config_manager import ConfigManager

        class _MockApp:
            _mount_data_tree = tree
        cm = ConfigManager.__new__(ConfigManager)
        cm._app = _MockApp()

        result = cm._derive_container_path(sibling_dir)
        assert result == f"/workspace/{sibling_dir.name}"

    def test_collision_gets_suffix(self, tree, project_dir, sibling_dir, second_sibling_dir):
        """Second sibling with same name gets {container_root}/{name}_2."""
        # Load a sibling first to create a collision
        sib1 = _make_sibling(
            host_path=sibling_dir,
            container_path=f"/workspace/{sibling_dir.name}",
        )
        config = _make_config(project_dir, siblings=[sib1])
        tree.load_config(config)
        tree.container_root = "/workspace"

        from IgnoreScope.gui.config_manager import ConfigManager

        class _MockApp:
            _mount_data_tree = tree
        cm = ConfigManager.__new__(ConfigManager)
        cm._app = _MockApp()

        # Create a path with the same folder name as sibling_dir
        # (different parent, same .name)
        import tempfile
        import os
        collision_dir = Path(tempfile.mkdtemp()) / sibling_dir.name
        collision_dir.mkdir()
        try:
            result = cm._derive_container_path(collision_dir)
            assert result == f"/workspace/{sibling_dir.name}_2"
        finally:
            collision_dir.rmdir()
            os.rmdir(collision_dir.parent)


# ── Test: no folder_actions imports remain ───────────────────────

class TestNoFolderActionsImport:
    """Verify dead module references are fully removed."""

    def test_no_folder_actions_import(self):
        """No .py file in IgnoreScope/ imports folder_actions or sibling_dialog modules."""
        import os
        import re
        root = Path(__file__).resolve().parents[2] / "IgnoreScope"
        # Match import statements, not method names like add_sibling_dialog
        patterns = [
            re.compile(r'\bfrom\s+\S*folder_actions\b'),
            re.compile(r'\bimport\s+\S*folder_actions\b'),
            re.compile(r'\bfrom\s+\S*sibling_dialog\b'),
            re.compile(r'\bimport\s+\S*sibling_dialog\b'),
        ]
        hits = []
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                fpath = Path(dirpath) / fname
                text = fpath.read_text(encoding="utf-8", errors="ignore")
                for pat in patterns:
                    if pat.search(text):
                        hits.append(str(fpath.relative_to(root)))
                        break
        assert hits == [], (
            f"Dead module references found in: {hits}"
        )


# ── Test: _collect_all_paths no double walk ──────────────────────

class TestCollectAllPathsNoDoubleWalk:
    """Verify sibling paths are collected once via root walk, not twice."""

    def test_sibling_paths_collected_via_root(self, tree, project_dir, sibling_dir):
        """Sibling paths appear in _collect_all_paths via root_node walk."""
        sibling = _make_sibling(
            host_path=sibling_dir,
            container_path="/shared",
        )
        config = _make_config(project_dir, siblings=[sibling])
        tree.load_config(config)

        paths = tree._collect_all_paths()

        # Sibling root and its children should be in collected paths
        assert sibling_dir in paths
        assert sibling_dir / "common" in paths
        assert sibling_dir / "internal" in paths

    def test_no_explicit_sibling_walk(self):
        """_collect_all_paths source has no 'for sib_node in self._sibling_nodes'."""
        import inspect
        source = inspect.getsource(MountDataTree._collect_all_paths)
        assert "for sib_node in self._sibling_nodes" not in source
