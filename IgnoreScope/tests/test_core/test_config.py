"""Unit tests for core configuration modules.

Tests ScopeDockerConfig, SiblingMount, and serialization.
No Docker required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from IgnoreScope.core.config import ScopeDockerConfig, SiblingMount
from IgnoreScope.core.mount_spec_path import MountSpecPath


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


def _make_scope_config(
    host_project_root: Path,
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
    pushed_files: set[Path] | None = None,
    **kwargs,
) -> ScopeDockerConfig:
    """Build ScopeDockerConfig from old-style set kwargs (test compat helper)."""
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
        host_project_root=host_project_root,
        **kwargs,
    )


class TestGetContainerPath:
    """Tests for get_container_path() 2-param utility."""

    def test_with_rel_path(self):
        """Standard case: root + relative path (includes project name naturally)."""
        from IgnoreScope.core.config import get_container_path

        result = get_container_path("/Projects", "MyProject/src/api")
        assert result == "/Projects/MyProject/src/api"

    def test_empty_rel_path(self):
        """Empty rel_path returns just root."""
        from IgnoreScope.core.config import get_container_path

        result = get_container_path("/Projects", "")
        assert result == "/Projects"

    def test_custom_container_root(self):
        """Custom container root is used as base."""
        from IgnoreScope.core.config import get_container_path

        result = get_container_path("/myroot", "Proj/src")
        assert result == "/myroot/Proj/src"

    def test_deep_rel_path(self):
        """Deeply nested relative path preserved."""
        from IgnoreScope.core.config import get_container_path

        result = get_container_path("/workspace", "P/a/b/c/d")
        assert result == "/workspace/P/a/b/c/d"

    def test_project_root_only(self):
        """Just project name as rel_path."""
        from IgnoreScope.core.config import get_container_path

        result = get_container_path("/Projects", "MyProject")
        assert result == "/Projects/MyProject"


class TestScopeDockerConfig:
    """Tests for ScopeDockerConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        from IgnoreScope.core.config import ScopeDockerConfig, DEFAULT_CONTAINER_ROOT

        config = ScopeDockerConfig()

        assert config.mounts == set()
        assert config.masked == set()
        assert config.revealed == set()
        assert config.pushed_files == set()
        assert config.container_files == set()
        assert config.scope_name == ""
        assert config.host_project_root is None
        assert config.host_container_root is None
        assert config.dev_mode is True
        assert config.mirrored is True
        assert config.container_root == DEFAULT_CONTAINER_ROOT
        assert config.siblings == []

    def test_custom_container_root(self, tmp_path: Path):
        """Test custom container root configuration."""
        from IgnoreScope.core.config import ScopeDockerConfig

        config = ScopeDockerConfig(
            host_project_root=tmp_path,
            container_root="/myproject",
        )

        assert config.container_root == "/myproject"

    def test_host_container_root_default(self, tmp_path: Path):
        """Test host_container_root defaults to host_project_root.parent."""
        from IgnoreScope.core.config import ScopeDockerConfig

        config = ScopeDockerConfig(host_project_root=tmp_path)

        assert config.host_container_root == tmp_path.parent

    def test_container_root_derived_from_hcr(self, tmp_path: Path):
        """Test container_root derives from host_container_root name (not /workspace)."""
        from IgnoreScope.core.config import ScopeDockerConfig

        config = ScopeDockerConfig(host_project_root=tmp_path)

        expected = f"/{tmp_path.parent.name}"
        assert config.container_root == expected

    def test_explicit_container_root_overrides_derived(self, tmp_path: Path):
        """Test explicit container_root overrides derived default."""
        from IgnoreScope.core.config import ScopeDockerConfig

        config = ScopeDockerConfig(
            host_project_root=tmp_path,
            container_root="/custom",
        )

        assert config.container_root == "/custom"
        # host_container_root still derived
        assert config.host_container_root == tmp_path.parent

    def test_host_container_root_serialization_round_trip(self, tmp_path: Path):
        """Test host_container_root serializes and deserializes correctly."""
        from IgnoreScope.core.config import ScopeDockerConfig

        original = _make_scope_config(
            host_project_root=tmp_path,
            mounts={tmp_path / "src"},
            scope_name="test",
        )

        data = original.to_dict()
        assert 'container_root' in data

        restored = ScopeDockerConfig.from_dict(data, tmp_path)
        assert restored.host_container_root == original.host_container_root
        assert restored.container_root == original.container_root

    def test_host_container_root_validation_non_ancestor(self, tmp_path: Path):
        """Test validation rejects non-ancestor host_container_root."""
        from IgnoreScope.core.config import ScopeDockerConfig

        unrelated = tmp_path / "unrelated"
        unrelated.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        config = ScopeDockerConfig(
            host_project_root=project,
            host_container_root=unrelated,
            container_root="/test",
        )

        errors = config.validate()
        assert any("host_container_root must be ancestor" in e for e in errors)

    def test_serialization_round_trip(self, tmp_path: Path):
        """Test config serializes and deserializes correctly."""
        from IgnoreScope.core.config import ScopeDockerConfig, SiblingMount

        # Create complex config
        original = _make_scope_config(
            mounts={tmp_path / "src"},
            masked={tmp_path / "src" / "api"},
            revealed={tmp_path / "src" / "api" / "public"},
            pushed_files={tmp_path / "src" / "api" / "config.json"},
            scope_name="test-container",
            host_project_root=tmp_path,
            dev_mode=False,
            mirrored=False,
            container_root="/custom",
            siblings=[
                _make_sibling(
                    host_path=Path("C:/Libs"),
                    container_path="/libs",
                    mounts={Path("C:/Libs/common")},
                )
            ],
        )

        # Serialize
        data = original.to_dict()

        # Verify structure — version always reflects the installed __version__
        from IgnoreScope._version import __version__
        assert data["version"] == __version__
        assert data["scope_name"] == "test-container"
        assert data["dev_mode"] is False
        assert data["mirrored"] is False
        # container_root serialized as relative traversal when host_container_root exists
        assert "container_root" in data
        assert "siblings" in data
        assert len(data["siblings"]) == 1
        # pushed_files should be in the local section
        assert "pushed_files" in data["local"]

        # Deserialize
        restored = ScopeDockerConfig.from_dict(data, tmp_path)

        # Verify restoration
        assert restored.scope_name == original.scope_name
        assert restored.dev_mode == original.dev_mode
        assert restored.mirrored == original.mirrored
        assert restored.container_root == original.container_root
        assert len(restored.siblings) == len(original.siblings)
        assert restored.siblings[0].container_path == "/libs"
        assert restored.pushed_files == original.pushed_files

    def test_mount_specs_round_trip(self, tmp_path: Path):
        """Test mount_specs JSON format loads correctly."""
        from IgnoreScope.core.config import ScopeDockerConfig

        data = {
            "version": "0.2.0",
            "scope_name": "test",
            "dev_mode": True,
            "local": {
                "mount_specs": [
                    {"mount_root": "src", "patterns": ["api/", "!api/public/"]},
                ],
                "pushed_files": ["src/api/config.json"],
            },
        }

        config = ScopeDockerConfig.from_dict(data, tmp_path)

        # Old exception_files should be merged into pushed_files
        assert tmp_path / "src" / "api" / "config.json" in config.pushed_files
        assert len(config.mount_specs) == 1
        assert config.mount_specs[0].patterns == ["api/", "!api/public/"]

    def test_legacy_container_mode_keys_silently_dropped(self, tmp_path: Path):
        """v0.4.x configs containing container_mode / init_source load without error."""
        from IgnoreScope.core.config import ScopeDockerConfig

        data = {
            "version": "0.4.1",
            "scope_name": "legacy",
            "dev_mode": True,
            "container_mode": "Isolation",
            "init_source": "cp",
            "local": {
                "mount_specs": [],
                "pushed_files": [],
            },
        }

        config = ScopeDockerConfig.from_dict(data, tmp_path)
        assert not hasattr(config, "container_mode")
        assert not hasattr(config, "init_source")
        assert config.validate() == []

        # Round-trip must not re-emit the legacy keys.
        round_tripped = config.to_dict()
        assert "container_mode" not in round_tripped
        assert "init_source" not in round_tripped

    def test_version_migration_dev_bypass(self, monkeypatch):
        """DEV_BYPASS_ENV_VAR skips migration and version stamping."""
        from IgnoreScope._version import (
            DEV_BYPASS_ENV_VAR, check_version_mismatch, __version__,
        )

        stale = {"version": "0.0.1", "scope_name": "stale"}

        # Default: version gets stamped to current
        stamped = check_version_mismatch(dict(stale))
        assert stamped["version"] == __version__

        # With bypass: data returned unchanged
        monkeypatch.setenv(DEV_BYPASS_ENV_VAR, "1")
        unchanged = check_version_mismatch(dict(stale))
        assert unchanged["version"] == "0.0.1"


class TestSiblingMount:
    """Tests for SiblingMount dataclass."""

    def test_creation(self):
        """Test sibling mount creation."""
        from IgnoreScope.core.config import SiblingMount

        sibling = SiblingMount(
            host_path=Path("C:/SharedLibs"),
            container_path="/shared",
        )

        assert sibling.host_path == Path("C:/SharedLibs")
        assert sibling.container_path == "/shared"
        assert sibling.mounts == set()
        assert sibling.masked == set()
        assert sibling.revealed == set()

    def test_serialization(self):
        """Test sibling mount serialization."""
        from IgnoreScope.core.config import SiblingMount

        sibling = _make_sibling(
            host_path=Path("C:/SharedLibs"),
            container_path="/shared",
            mounts={Path("C:/SharedLibs/common")},
            masked={Path("C:/SharedLibs/common/internal")},
        )

        data = sibling.to_dict()

        assert data["host_path"] == "C:\\SharedLibs"
        assert data["container_path"] == "/shared"
        assert "mount_specs" in data
        assert len(data["mount_specs"]) == 1
        assert data["mount_specs"][0]["mount_root"] == "common"

        # Deserialize
        restored = SiblingMount.from_dict(data)
        assert restored.host_path == sibling.host_path
        assert restored.container_path == sibling.container_path


class TestHierarchy:
    """Tests for ContainerHierarchy computation."""

    def test_basic_hierarchy(self, tmp_path: Path):
        """Test basic hierarchy computation."""
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        src = tmp_path / "src"
        api = src / "api"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        assert len(hierarchy.validation_errors) == 0
        assert len(hierarchy.ordered_volumes) == 2  # mount + mask
        assert any("/workspace/src" in v for v in hierarchy.ordered_volumes)

    def test_hierarchy_with_host_container_root(self, tmp_path: Path):
        """Test hierarchy with host_container_root=parent includes project dir in paths."""
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()
        src = project_dir / "src"
        api = src / "api"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}),
            pushed_files=set(),
            host_project_root=project_dir,
            host_container_root=tmp_path,
        )

        assert len(hierarchy.validation_errors) == 0
        assert len(hierarchy.ordered_volumes) == 2  # mount + mask
        # Paths should include project dir: /workspace/MyProject/src
        assert any("/workspace/MyProject/src" in v for v in hierarchy.ordered_volumes)

    def test_revealed_parents_computed(self, tmp_path: Path):
        """Test pushed file parent directories are computed."""
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        src = tmp_path / "src"
        api = src / "api"
        deep = api / "deep" / "nested"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}),
            pushed_files={deep / "config.ini"},
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        # Should have parent directories for pushed file
        assert len(hierarchy.revealed_parents) > 0
        # Check POSIX format
        for parent in hierarchy.revealed_parents:
            assert "/" in parent
            assert "\\" not in parent

    def test_revealed_parents_with_host_container_root(self, tmp_path: Path):
        """Test revealed parents include project dir when host_container_root is parent."""
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()
        src = project_dir / "src"
        api = src / "api"
        deep = api / "deep" / "nested"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}, {api}),
            pushed_files={deep / "config.ini"},
            host_project_root=project_dir,
            host_container_root=tmp_path,
        )

        # Should have parent directories for pushed file with project dir
        assert len(hierarchy.revealed_parents) > 0
        # All parents should start with /workspace/MyProject/
        for parent in hierarchy.revealed_parents:
            assert parent.startswith("/workspace/MyProject/"), f"Expected path to start with /workspace/MyProject/, got {parent}"

    def test_validation_errors(self, tmp_path: Path):
        """Test validation error detection."""
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        # Exception pattern without preceding deny → validation error
        src = tmp_path / "src"
        ms = MountSpecPath(mount_root=src, patterns=["!orphan/"])
        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=[ms],
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        assert len(hierarchy.validation_errors) > 0
        assert any("no preceding deny" in e.lower() for e in hierarchy.validation_errors)

    def test_sibling_hierarchy(self, tmp_path: Path):
        """Test hierarchy with sibling mounts."""
        from IgnoreScope.core.config import SiblingMount
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        sibling = _make_sibling(
            host_path=Path("C:/Libs"),
            container_path="/libs",
            mounts={Path("C:/Libs/common")},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path / "src"}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
        )

        # Should have volumes for both primary and sibling
        assert any("/workspace" in v for v in hierarchy.ordered_volumes)
        assert any("/libs" in v for v in hierarchy.ordered_volumes)

    def test_mount_root_mask_volume(self, tmp_path: Path):
        """Test that a folder can be both mounted AND masked.

        When src/ is in BOTH mounts and masked, the volume entries should
        produce two entries targeting the SAME container path:
          1. Bind mount:  host/src → /workspace/src       (Layer 1)
          2. Named volume: mask_src → /workspace/src      (Layer 2)

        Docker processes volumes in order, so the named volume overlays
        the bind mount — effectively hiding all files at the mount root.
        A reveal can then punch through to re-expose specific subdirs.
        """
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        src = tmp_path / "src"
        public = src / "api" / "public"

        # src/ is mounted; mask api/, reveal api/public/
        api = src / "api"
        ms = MountSpecPath(mount_root=src, patterns=["api/", "!api/public/"])
        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=[ms],
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
        )

        # No validation errors — mask under mount, reveal under mask
        assert len(hierarchy.validation_errors) == 0

        # Should have 3 volume entries: bind mount + mask + reveal
        assert len(hierarchy.ordered_volumes) == 3, (
            f"Expected 3 volumes (mount + mask + reveal), got {hierarchy.ordered_volumes}"
        )

        # Extract container paths from each volume entry
        bind_mount = hierarchy.ordered_volumes[0]   # Layer 1
        mask_volume = hierarchy.ordered_volumes[1]   # Layer 2
        reveal_mount = hierarchy.ordered_volumes[2]  # Layer 3

        # Both mount and mask target the SAME container path
        assert ":/workspace/src" in bind_mount, f"Bind mount missing target: {bind_mount}"
        assert ":/workspace/src/api" in mask_volume, f"Mask volume missing target: {mask_volume}"
        assert ":ro" not in bind_mount, "Bind mount should be writable"
        assert ":ro" not in mask_volume, "Mask volume should NOT be read-only"

        # Mask uses a named volume (no host path with slashes before the colon)
        mask_source = mask_volume.split(":")[0]
        assert "mask_" in mask_source, f"Mask should use named volume, got: {mask_source}"

        # Reveal punches through to the specific subdir
        assert ":/workspace/src/api/public" in reveal_mount
        assert ":ro" not in reveal_mount

        # Visibility: src is visible (mounted), api is masked
        assert "/workspace/src" in hierarchy.visible_paths
        assert "/workspace/src/api" in hierarchy.masked_paths
        # Reveal is visible
        assert "/workspace/src/api/public" in hierarchy.visible_paths

    def test_sibling_hierarchy_with_host_container_root(self, tmp_path: Path):
        """Test siblings remain at their own paths while project uses host_container_root."""
        from IgnoreScope.core.config import SiblingMount
        from IgnoreScope.core.hierarchy import compute_container_hierarchy

        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()
        sibling = _make_sibling(
            host_path=Path("C:/SharedLib"),
            container_path="/workspace/SharedLib",  # True sibling at same level
            mounts={Path("C:/SharedLib/common")},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({project_dir / "src"}),
            pushed_files=set(),
            host_project_root=project_dir,
            host_container_root=tmp_path,
            siblings=[sibling],
        )

        # Primary volumes should include project dir name
        primary_volumes = [v for v in hierarchy.ordered_volumes if "MyProject" in v]
        assert len(primary_volumes) > 0, "Should have volumes with project dir name"

        # Sibling should be at /workspace/SharedLib (true sibling)
        sibling_volumes = [v for v in hierarchy.ordered_volumes if "/workspace/SharedLib" in v]
        assert len(sibling_volumes) > 0, "Should have sibling volumes"


class TestPathHelpers:
    """Tests for sibling config path helper functions."""

    def test_get_igsc_root(self, tmp_path: Path):
        """Test IGSC root path generation."""
        from IgnoreScope.core.config import get_igsc_root

        host_project_root = tmp_path / "MyProject"
        host_project_root.mkdir()

        igsc_root = get_igsc_root(host_project_root)

        # Should be inside project: {project}/.ignore_scope
        assert igsc_root.parent == host_project_root
        assert igsc_root.name == ".ignore_scope"

    def test_get_container_dir(self, tmp_path: Path):
        """Test container directory path generation."""
        from IgnoreScope.core.config import get_container_dir

        host_project_root = tmp_path / "MyProject"
        host_project_root.mkdir()

        container_dir = get_container_dir(host_project_root, "dev")

        # Should be {project}/.ignore_scope/{scope}/
        assert container_dir.parent.name == ".ignore_scope"
        assert container_dir.name == "dev"

    def test_get_llm_dir(self, tmp_path: Path):
        """Test LLM config directory path generation."""
        from IgnoreScope.core.config import get_llm_dir

        host_project_root = tmp_path / "MyProject"
        host_project_root.mkdir()

        llm_dir = get_llm_dir(host_project_root, "dev", "claude")

        # Should be {project}/.ignore_scope/{scope}/.llm/{llm}/
        assert llm_dir.name == "claude"
        assert llm_dir.parent.name == ".llm"
        assert llm_dir.parent.parent.name == "dev"

    def test_list_containers_empty(self, tmp_path: Path):
        """Test listing containers when none exist."""
        from IgnoreScope.core.config import list_containers

        host_project_root = tmp_path / "MyProject"
        host_project_root.mkdir()

        containers = list_containers(host_project_root)

        assert containers == []

    def test_list_containers(self, tmp_path: Path):
        """Test listing existing containers."""
        from IgnoreScope.core.config import list_containers, get_container_dir

        host_project_root = tmp_path / "MyProject"
        host_project_root.mkdir()

        # Create some container directories
        get_container_dir(host_project_root, "dev").mkdir(parents=True)
        get_container_dir(host_project_root, "prod").mkdir(parents=True)
        get_container_dir(host_project_root, "test").mkdir(parents=True)

        containers = list_containers(host_project_root)

        assert containers == ["dev", "prod", "test"]

    def test_load_save_config_sibling_path(self, tmp_path: Path):
        """Test config is saved to sibling path structure."""
        from IgnoreScope.core.config import (
            ScopeDockerConfig, load_config, save_config, get_container_dir
        )

        host_project_root = tmp_path / "MyProject"
        host_project_root.mkdir()

        # Create and save config
        config = _make_scope_config(
            scope_name="mycontainer",
            host_project_root=host_project_root,
            mounts={host_project_root / "src"},
        )
        save_config(config)

        # Verify file location
        expected_path = get_container_dir(host_project_root, "mycontainer") / "scope_docker_desktop.json"
        assert expected_path.exists()

        # Verify can load
        loaded = load_config(host_project_root, "mycontainer")
        assert loaded.scope_name == "mycontainer"
