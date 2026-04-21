"""Tests for MountSpecPath descendant query and virtual derivation methods.

Tests:
  MSP-1: has_exception_descendant()
  MSP-2: get_virtual_paths()
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
        and is never checked for virtual upgrade."""
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
# MSP-2: get_virtual_paths()
# ──────────────────────────────────────────────


class TestGetVirtualPaths:
    """Tests for MountSpecPath.get_virtual_paths()."""

    def _make_spec(self, tmp_path: Path, patterns: list[str]) -> MountSpecPath:
        return MountSpecPath(mount_root=tmp_path, patterns=patterns)

    def test_simple_mask_reveal(self, tmp_path: Path):
        """vendor/ + !vendor/public/ → vendor is virtual."""
        spec = self._make_spec(tmp_path, ["vendor/", "!vendor/public/"])
        result = spec.get_virtual_paths()
        assert result == {tmp_path / "vendor"}

    def test_deep_reveal(self, tmp_path: Path):
        """vendor/ + !vendor/internal/handlers/public/ → vendor, vendor/internal, vendor/internal/handlers are virtual."""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "!vendor/internal/handlers/public/",
        ])
        result = spec.get_virtual_paths()
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
        result = spec.get_virtual_paths()
        # vendor → virtual (covers vendor/public exception)
        # vendor/public/tmp → virtual (covers vendor/public/tmp/logs exception)
        assert tmp_path / "vendor" in result
        assert tmp_path / "vendor" / "public" / "tmp" in result

    def test_no_exceptions(self, tmp_path: Path):
        """Deny-only patterns produce no virtual paths."""
        spec = self._make_spec(tmp_path, ["vendor/", "dist/"])
        assert spec.get_virtual_paths() == set()

    def test_empty_patterns(self, tmp_path: Path):
        """No patterns at all."""
        spec = self._make_spec(tmp_path, [])
        assert spec.get_virtual_paths() == set()

    def test_exception_without_covering_deny(self, tmp_path: Path):
        """Orphan exception (no deny above it) — produces no virtual paths."""
        spec = self._make_spec(tmp_path, ["!vendor/public/"])
        assert spec.get_virtual_paths() == set()

    def test_multiple_independent_exceptions(self, tmp_path: Path):
        """Two separate deny/exception pairs."""
        spec = self._make_spec(tmp_path, [
            "vendor/",
            "!vendor/public/",
            "dist/",
            "!dist/assets/",
        ])
        result = spec.get_virtual_paths()
        assert tmp_path / "vendor" in result
        assert tmp_path / "dist" in result

    def test_exception_immediately_under_deny(self, tmp_path: Path):
        """Exception is immediate child of deny — deny path itself is virtual."""
        spec = self._make_spec(tmp_path, ["src/", "!src/api/"])
        result = spec.get_virtual_paths()
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
        """Detached delivery survives to_dict / from_dict."""
        original = MountSpecPath(
            mount_root=tmp_path / "src",
            patterns=["vendor/"],
            delivery="detached",
        )
        restored = MountSpecPath.from_dict(original.to_dict(tmp_path), tmp_path)
        assert restored.delivery == "detached"
        assert restored.mount_root == original.mount_root
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
        """validate() returns no delivery error for legitimate values."""
        bind = MountSpecPath(mount_root=tmp_path / "src", patterns=[], delivery="bind")
        detached = MountSpecPath(
            mount_root=tmp_path / "src", patterns=[], delivery="detached",
        )
        assert not any("delivery" in e for e in bind.validate())
        assert not any("delivery" in e for e in detached.validate())

    def test_validate_no_overlap_is_delivery_agnostic(self, tmp_path: Path):
        """Overlap check ignores delivery — two specs at the same root still overlap."""
        a = MountSpecPath(mount_root=tmp_path / "src", patterns=[], delivery="bind")
        b = MountSpecPath(
            mount_root=tmp_path / "src", patterns=[], delivery="detached",
        )
        errors = MountSpecPath.validate_no_overlap([a, b])
        assert any("Duplicate mount root" in e for e in errors)
