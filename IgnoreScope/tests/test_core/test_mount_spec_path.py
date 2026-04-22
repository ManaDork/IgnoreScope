"""Tests for MountSpecPath descendant query and stencil derivation methods.

Tests:
  MSP-1: has_exception_descendant()
  MSP-2: get_stencil_paths()
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.mount_spec_path import MountSpecPath


# ──────────────────────────────────────────────
# MSP-1: has_exception_descendant()
# ──────────────────────────────────────────────


class TestHasExceptionDescendant:
    """Tests for MountSpecPath.has_exception_descendant()."""

    def _make_spec(self, tmp_path: Path, patterns: list[str]) -> MountSpecPath:
        return MountSpecPath(mount_root=tmp_path, patterns=patterns)

    def test_exception_directly_under_path(self, tmp_path: Path):
        """Exception pattern is an immediate child of the queried path."""
        spec = self._make_spec(tmp_path, ["vendor/", "!vendor/public/"])
        assert spec.has_exception_descendant(tmp_path / "vendor") is True

    def test_exception_deeply_nested(self, tmp_path: Path):
        """Exception is several levels below the queried path."""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "!vendor/internal/handlers/public/",
        ])
        assert spec.has_exception_descendant(tmp_path / "vendor") is True
        assert spec.has_exception_descendant(tmp_path / "vendor" / "internal") is True
        assert spec.has_exception_descendant(tmp_path / "vendor" / "internal" / "handlers") is True

    def test_no_exception_under_path(self, tmp_path: Path):
        """Path has no exception descendants."""
        spec = self._make_spec(tmp_path, ["vendor/", "!other/public/"])
        assert spec.has_exception_descendant(tmp_path / "vendor") is False

    def test_exception_is_the_path_itself(self, tmp_path: Path):
        """Exception pattern matches the exact path — not a descendant."""
        spec = self._make_spec(tmp_path, ["vendor/", "!vendor/"])
        assert spec.has_exception_descendant(tmp_path / "vendor") is False

    def test_empty_patterns(self, tmp_path: Path):
        """No patterns at all."""
        spec = self._make_spec(tmp_path, [])
        assert spec.has_exception_descendant(tmp_path / "anything") is False

    def test_deny_only_patterns(self, tmp_path: Path):
        """Only deny patterns, no exceptions."""
        spec = self._make_spec(tmp_path, ["vendor/", "dist/"])
        assert spec.has_exception_descendant(tmp_path / "vendor") is False

    def test_path_above_mount_root(self, tmp_path: Path):
        """Path above mount_root returns False (_to_relative returns None)."""
        spec = self._make_spec(tmp_path / "project", ["vendor/", "!vendor/public/"])
        assert spec.has_exception_descendant(tmp_path) is False

    def test_mount_root_itself(self, tmp_path: Path):
        """Querying mount_root returns False — _to_relative produces '.'
        which doesn't prefix-match exception patterns. This is acceptable
        because mount_root always gets visibility='visible' in Stage 1
        and is never checked for stencil upgrade."""
        spec = self._make_spec(tmp_path, ["vendor/", "!vendor/public/"])
        assert spec.has_exception_descendant(tmp_path) is False

    def test_sibling_exception_not_matched(self, tmp_path: Path):
        """Exception under a sibling path should not match."""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "dist/",
            "!dist/public/",
        ])
        assert spec.has_exception_descendant(tmp_path / "vendor") is False
        assert spec.has_exception_descendant(tmp_path / "dist") is True

    def test_nested_remask_with_exception(self, tmp_path: Path):
        """Nested mask/reveal: vendor/ → !vendor/public/ → vendor/public/tmp/ → !vendor/public/tmp/logs/"""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "!vendor/public/",
            "vendor/public/tmp/",
            "!vendor/public/tmp/logs/",
        ])
        assert spec.has_exception_descendant(tmp_path / "vendor") is True
        assert spec.has_exception_descendant(tmp_path / "vendor" / "public") is True
        assert spec.has_exception_descendant(tmp_path / "vendor" / "public" / "tmp") is True


# ──────────────────────────────────────────────
# MSP-2: get_stencil_paths()
# ──────────────────────────────────────────────


class TestGetStencilPaths:
    """Tests for MountSpecPath.get_stencil_paths()."""

    def _make_spec(self, tmp_path: Path, patterns: list[str]) -> MountSpecPath:
        return MountSpecPath(mount_root=tmp_path, patterns=patterns)

    def test_simple_mask_reveal(self, tmp_path: Path):
        """vendor/ + !vendor/public/ → vendor is stencil."""
        spec = self._make_spec(tmp_path, ["vendor/", "!vendor/public/"])
        result = spec.get_stencil_paths()
        assert result == {tmp_path / "vendor"}

    def test_deep_reveal(self, tmp_path: Path):
        """vendor/ + !vendor/internal/handlers/public/ → vendor, vendor/internal, vendor/internal/handlers are stencils."""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "!vendor/internal/handlers/public/",
        ])
        result = spec.get_stencil_paths()
        expected = {
            tmp_path / "vendor",
            tmp_path / "vendor" / "internal",
            tmp_path / "vendor" / "internal" / "handlers",
        }
        assert result == expected

    def test_nested_remask(self, tmp_path: Path):
        """Nested: vendor/ → !vendor/public/ → vendor/public/tmp/ → !vendor/public/tmp/logs/"""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "!vendor/public/",
            "vendor/public/tmp/",
            "!vendor/public/tmp/logs/",
        ])
        result = spec.get_stencil_paths()
        # vendor → stencil (covers vendor/public exception)
        # vendor/public/tmp → stencil (covers vendor/public/tmp/logs exception)
        assert tmp_path / "vendor" in result
        assert tmp_path / "vendor" / "public" / "tmp" in result

    def test_no_exceptions(self, tmp_path: Path):
        """Deny-only patterns produce no stencil paths."""
        spec = self._make_spec(tmp_path, ["vendor/", "dist/"])
        assert spec.get_stencil_paths() == set()

    def test_empty_patterns(self, tmp_path: Path):
        """No patterns at all."""
        spec = self._make_spec(tmp_path, [])
        assert spec.get_stencil_paths() == set()

    def test_exception_without_covering_deny(self, tmp_path: Path):
        """Orphan exception (no deny above it) — produces no stencil paths."""
        spec = self._make_spec(tmp_path, ["!vendor/public/"])
        assert spec.get_stencil_paths() == set()

    def test_multiple_independent_exceptions(self, tmp_path: Path):
        """Two separate deny/exception pairs."""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "!vendor/public/",
            "dist/",
            "!dist/assets/",
        ])
        result = spec.get_stencil_paths()
        assert tmp_path / "vendor" in result
        assert tmp_path / "dist" in result

    def test_exception_immediately_under_deny(self, tmp_path: Path):
        """Exception is immediate child of deny — deny path itself is stencil."""
        spec = self._make_spec(tmp_path, ["src/", "!src/api/"])
        result = spec.get_stencil_paths()
        assert result == {tmp_path / "src"}


# ──────────────────────────────────────────────
# MSP-3: delivery field (bind vs detached)
# ──────────────────────────────────────────────


class TestDeliveryField:
    """Tests for MountSpecPath.delivery (per-spec content-delivery mode)."""

    def test_delivery_defaults_to_bind(self, tmp_path: Path):
        """A spec created without an explicit delivery defaults to 'bind'."""
        spec = MountSpecPath(mount_root=tmp_path / "src", patterns=["vendor/"])
        assert spec.delivery == "bind"

    def test_delivery_explicit_detached(self, tmp_path: Path):
        """Detached delivery can be set at construction."""
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="detached",
        )
        assert spec.delivery == "detached"

    def test_to_dict_emits_delivery(self, tmp_path: Path):
        """to_dict serializes the delivery value."""
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/"],
            delivery="detached",
        )
        data = spec.to_dict(tmp_path)
        assert data["delivery"] == "detached"

    def test_to_dict_emits_bind_by_default(self, tmp_path: Path):
        """to_dict emits 'bind' for default-constructed specs."""
        spec = MountSpecPath(mount_root=tmp_path / "src", patterns=[])
        assert spec.to_dict(tmp_path)["delivery"] == "bind"

    def test_from_dict_defaults_missing_delivery_to_bind(self, tmp_path: Path):
        """Legacy configs without 'delivery' default to 'bind'."""
        data = {"mount_root": "src", "patterns": ["vendor/"]}
        spec = MountSpecPath.from_dict(data, tmp_path)
        assert spec.delivery == "bind"

    def test_from_dict_round_trip_detached(self, tmp_path: Path):
        """Host-backed detached delivery survives to_dict / from_dict."""
        original = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/"],
            delivery="detached",
            host_path=tmp_path / "src",
        )
        restored = MountSpecPath.from_dict(original.to_dict(tmp_path), tmp_path)
        assert restored.delivery == "detached"
        assert restored.mount_root == original.mount_root
        assert restored.host_path == original.host_path
        assert restored.patterns == original.patterns

    def test_validate_rejects_invalid_delivery(self, tmp_path: Path):
        """validate() flags any delivery value other than bind / detached."""
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="bogus",  # type: ignore[arg-type]
        )
        errors = spec.validate()
        assert any("delivery" in e for e in errors)

    def test_validate_accepts_bind_and_detached(self, tmp_path: Path):
        """validate() returns no delivery-enum error for legitimate values."""
        bind = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="bind",
            host_path=tmp_path / "src",
        )
        detached = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="detached",
            host_path=tmp_path / "src",
        )
        assert not any("delivery must be" in e for e in bind.validate())
        assert not any("delivery must be" in e for e in detached.validate())

    def test_validate_no_overlap_is_delivery_agnostic(self, tmp_path: Path):
        """Overlap check ignores delivery — two specs at the same root still overlap."""
        a = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="bind",
            host_path=tmp_path / "src",
        )
        b = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="detached",
            host_path=tmp_path / "src",
        )
        errors = MountSpecPath.validate_no_overlap([a, b])
        assert any("Duplicate mount root" in e for e in errors)


# ──────────────────────────────────────────────
# MSP-4: Phase 3 schema extensions
#   host_path / content_seed / preserve_on_update / delivery="volume"
# ──────────────────────────────────────────────


class TestPhase3SchemaDefaults:
    """Phase 3 fields default to backward-compatible values."""

    def test_host_path_defaults_to_none_for_non_bind(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/folder"),
            delivery="detached",
            content_seed="folder",
        )
        assert spec.host_path is None

    def test_host_path_auto_fills_from_mount_root_for_bind(self, tmp_path: Path):
        """Default delivery is 'bind'; __post_init__ fills host_path."""
        spec = MountSpecPath(mount_root=tmp_path / "src")
        assert spec.delivery == "bind"
        assert spec.host_path == tmp_path / "src"

    def test_content_seed_defaults_to_tree(self, tmp_path: Path):
        spec = MountSpecPath(mount_root=tmp_path / "src")
        assert spec.content_seed == "tree"

    def test_preserve_on_update_defaults_to_false(self, tmp_path: Path):
        spec = MountSpecPath(mount_root=tmp_path / "src")
        assert spec.preserve_on_update is False


class TestPhase3ValidateHostPath:
    """host_path=None is valid only for non-bind deliveries."""

    def test_bind_auto_fills_host_path_from_mount_root(self, tmp_path: Path):
        """__post_init__ fills host_path = mount_root when unset on a bind spec."""
        spec = MountSpecPath(
            mount_root=tmp_path / "src", delivery="bind", host_path=None,
        )
        assert spec.host_path == tmp_path / "src"
        assert not any("host_path" in e for e in spec.validate())

    def test_bind_with_explicit_none_post_construction_rejected(self, tmp_path: Path):
        """Explicit post-construction tampering is caught by validate()."""
        spec = MountSpecPath(
            mount_root=tmp_path / "src", delivery="bind",
            host_path=tmp_path / "src",
        )
        spec.host_path = None  # tamper
        assert any("host_path is required" in e for e in spec.validate())

    def test_bind_with_host_path_ok(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            delivery="bind",
            host_path=tmp_path / "src",
        )
        assert not any("host_path" in e for e in spec.validate())

    def test_detached_container_only_ok(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/folder"),
            delivery="detached",
            host_path=None,
            content_seed="folder",
        )
        assert not any("host_path" in e for e in spec.validate())

    def test_volume_container_only_ok(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/folder"),
            delivery="volume",
            host_path=None,
            content_seed="folder",
        )
        assert not any("host_path" in e for e in spec.validate())


class TestPhase3ValidateVolumeRequiresFolderSeed:
    """delivery='volume' rejects tree-seeding at this phase."""

    def test_volume_with_tree_seed_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/data"),
            delivery="volume",
            host_path=None,
            content_seed="tree",
        )
        assert any("delivery='volume' requires content_seed='folder'" in e
                   for e in spec.validate())

    def test_volume_with_folder_seed_ok(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/data"),
            delivery="volume",
            host_path=None,
            content_seed="folder",
        )
        errors = spec.validate()
        assert not any("content_seed" in e for e in errors)


class TestPhase3ValidatePreserveOnUpdate:
    """preserve_on_update is only valid on detached+folder specs."""

    def test_preserve_on_tree_seed_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            delivery="detached",
            host_path=tmp_path / "src",
            content_seed="tree",
            preserve_on_update=True,
        )
        assert any("preserve_on_update" in e for e in spec.validate())

    def test_preserve_on_volume_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/data"),
            delivery="volume",
            host_path=None,
            content_seed="folder",
            preserve_on_update=True,
        )
        assert any("preserve_on_update" in e for e in spec.validate())

    def test_preserve_on_bind_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            delivery="bind",
            host_path=tmp_path / "src",
            content_seed="tree",
            preserve_on_update=True,
        )
        assert any("preserve_on_update" in e for e in spec.validate())

    def test_preserve_on_detached_folder_ok(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/data"),
            delivery="detached",
            host_path=None,
            content_seed="folder",
            preserve_on_update=True,
        )
        assert not any("preserve_on_update" in e for e in spec.validate())

    def test_preserve_false_always_ok(self, tmp_path: Path):
        # Even on "invalid" combos, False flag produces no preserve error.
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            delivery="bind",
            host_path=tmp_path / "src",
            preserve_on_update=False,
        )
        assert not any("preserve_on_update" in e for e in spec.validate())


class TestPhase3ValidateContentSeedEnum:
    def test_invalid_content_seed_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            host_path=tmp_path / "src",
            content_seed="bogus",  # type: ignore[arg-type]
        )
        assert any("content_seed" in e for e in spec.validate())


class TestPhase3ValidateDeliveryEnum:
    def test_volume_accepted_as_delivery(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/data"),
            delivery="volume",
            host_path=None,
            content_seed="folder",
        )
        assert not any("delivery must be" in e for e in spec.validate())


class TestPhase3Serialization:
    """All combinations round-trip through to_dict/from_dict."""

    def test_legacy_bind_round_trip(self, tmp_path: Path):
        original = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/"],
            delivery="bind",
            host_path=tmp_path / "src",
        )
        restored = MountSpecPath.from_dict(original.to_dict(tmp_path), tmp_path)
        assert restored.delivery == "bind"
        assert restored.host_path == (tmp_path / "src").resolve()
        assert restored.content_seed == "tree"
        assert restored.preserve_on_update is False

    def test_detached_tree_seed_round_trip(self, tmp_path: Path):
        original = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="detached",
            host_path=tmp_path / "src",
            content_seed="tree",
        )
        restored = MountSpecPath.from_dict(original.to_dict(tmp_path), tmp_path)
        assert restored.delivery == "detached"
        assert restored.content_seed == "tree"
        assert restored.host_path == (tmp_path / "src").resolve()

    def test_detached_folder_seed_round_trip(self, tmp_path: Path):
        original = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="detached",
            host_path=tmp_path / "src",
            content_seed="folder",
            preserve_on_update=True,
        )
        restored = MountSpecPath.from_dict(original.to_dict(tmp_path), tmp_path)
        assert restored.content_seed == "folder"
        assert restored.preserve_on_update is True

    def test_container_only_folder_round_trip(self, tmp_path: Path):
        original = MountSpecPath(
            mount_root=Path("/container/data"),
            patterns=[],
            delivery="detached",
            host_path=None,
            content_seed="folder",
        )
        restored = MountSpecPath.from_dict(original.to_dict(tmp_path), tmp_path)
        assert restored.host_path is None
        assert restored.content_seed == "folder"
        assert restored.delivery == "detached"

    def test_volume_round_trip(self, tmp_path: Path):
        original = MountSpecPath(
            mount_root=Path("/container/cache"),
            patterns=[],
            delivery="volume",
            host_path=None,
            content_seed="folder",
        )
        restored = MountSpecPath.from_dict(original.to_dict(tmp_path), tmp_path)
        assert restored.delivery == "volume"
        assert restored.content_seed == "folder"
        assert restored.host_path is None

    def test_legacy_dict_deserializes_with_defaults(self, tmp_path: Path):
        """Phase 1/2 configs on disk have no Phase 3 keys; from_dict fills defaults.

        Legacy bind specs had no host_path key — __post_init__ derives it from
        mount_root so the spec validates cleanly under Phase 3 rules.
        """
        legacy = {
            "mount_root": "src",
            "patterns": ["vendor/"],
            "delivery": "bind",
        }
        spec = MountSpecPath.from_dict(legacy, tmp_path)
        assert spec.host_path == (tmp_path / "src").resolve()
        assert spec.content_seed == "tree"
        assert spec.preserve_on_update is False
        assert spec.delivery == "bind"
        assert spec.validate() == []

    def test_default_fields_omitted_from_dict(self, tmp_path: Path):
        """Legacy Phase 1/2 specs serialize to the same JSON shape they had.

        host_path == mount_root on a bind spec is the implicit default, so it's
        omitted from JSON — keeps existing configs round-tripping unchanged.
        """
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/"],
            delivery="bind",
        )
        data = spec.to_dict(tmp_path)
        assert "host_path" not in data
        assert "content_seed" not in data
        assert "preserve_on_update" not in data

    def test_non_default_fields_present_in_dict(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/data"),
            delivery="volume",
            host_path=None,
            content_seed="folder",
        )
        data = spec.to_dict(tmp_path)
        assert data["content_seed"] == "folder"
        assert data["delivery"] == "volume"


class TestPhase3ValidateContainerOnlyRequiresFolderSeed:
    """host_path=None (container-only) requires content_seed='folder'."""

    def test_container_only_tree_seed_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/src"),
            delivery="detached",
            host_path=None,
            content_seed="tree",
        )
        errors = spec.validate()
        assert any("container-only" in e and "folder" in e for e in errors), (
            f"Expected container-only-requires-folder error, got: {errors}"
        )

    def test_container_only_folder_seed_ok(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=Path("/container/src"),
            delivery="detached",
            host_path=None,
            content_seed="folder",
        )
        assert not any("container-only" in e for e in spec.validate())


class TestPhase3ValidateFolderSeedRejectsPatterns:
    """Folder-seed specs cannot carry mask/reveal patterns."""

    def test_folder_seed_with_mask_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/"],
            delivery="detached",
            host_path=tmp_path / "src",
            content_seed="folder",
        )
        errors = spec.validate()
        assert any("folder-seed" in e and "pattern" in e for e in errors), (
            f"Expected folder-seed-disallows-patterns error, got: {errors}"
        )

    def test_folder_seed_with_reveal_rejected(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/", "!vendor/public/"],
            delivery="detached",
            host_path=tmp_path / "src",
            content_seed="folder",
        )
        errors = spec.validate()
        assert any("folder-seed" in e and "pattern" in e for e in errors)

    def test_folder_seed_empty_patterns_ok(self, tmp_path: Path):
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=[],
            delivery="detached",
            host_path=tmp_path / "src",
            content_seed="folder",
        )
        assert not any("folder-seed" in e for e in spec.validate())

    def test_tree_seed_with_patterns_still_ok(self, tmp_path: Path):
        """Regression: tree-seed + patterns is the baseline, must remain valid."""
        spec = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/", "!vendor/public/"],
            delivery="detached",
            host_path=tmp_path / "src",
            content_seed="tree",
        )
        assert not any("folder-seed" in e for e in spec.validate())
