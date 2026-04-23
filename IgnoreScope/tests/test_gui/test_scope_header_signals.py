"""Tests for ScopeHeaderSignals + resolve_scope_header_signals (Phase 3 Task 3.1).

Pure-unit coverage of the 3-signal aggregate:
  - Truth-table: 6 valid states (8-row product minus 2 impossible rows)
  - Invariant: fully_virtual AND has_mounts is never produced
  - Empty-scope fallback: both structural signals False
  - Unified mount_specs input: user + synthesized extension specs contribute
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.mount_spec_path import MountSpecPath
from IgnoreScope.gui.style_engine import (
    ScopeHeaderSignals,
    resolve_scope_header_signals,
)


def _spec(name: str, delivery: str, owner: str = "user") -> MountSpecPath:
    """Construct a MountSpecPath with minimal validator-friendly fields."""
    if delivery == "bind":
        host_path = Path(f"/fake/{name}")
    else:
        host_path = None
    content_seed = "folder" if delivery == "volume" else "tree"
    return MountSpecPath(
        mount_root=Path(f"/fake/{name}"),
        delivery=delivery,
        host_path=host_path,
        content_seed=content_seed,
        owner=owner,
    )


# ──────────────────────────────────────────────
# Empty scope — empty / inactive quadrant
# ──────────────────────────────────────────────


class TestEmptyScope:
    def test_empty_container_off(self):
        signals = resolve_scope_header_signals(False, [])
        assert signals == ScopeHeaderSignals(
            container_running=False, fully_virtual=False, has_mounts=False,
        )

    def test_empty_container_running(self):
        signals = resolve_scope_header_signals(True, [])
        assert signals == ScopeHeaderSignals(
            container_running=True, fully_virtual=False, has_mounts=False,
        )


# ──────────────────────────────────────────────
# Truth table — 6 valid states
# ──────────────────────────────────────────────


class TestTruthTable:
    """All 6 valid rows from the ScopeHeaderSignals truth table."""

    def test_row1_off_empty(self):
        # Container off, no specs → empty / inactive
        assert resolve_scope_header_signals(False, []) == ScopeHeaderSignals(
            False, False, False,
        )

    def test_row2_off_has_bind(self):
        specs = [_spec("a", "bind")]
        assert resolve_scope_header_signals(False, specs) == ScopeHeaderSignals(
            container_running=False, fully_virtual=False, has_mounts=True,
        )

    def test_row3_off_fully_virtual(self):
        specs = [_spec("a", "detached")]
        assert resolve_scope_header_signals(False, specs) == ScopeHeaderSignals(
            container_running=False, fully_virtual=True, has_mounts=False,
        )

    def test_row4_running_empty(self):
        assert resolve_scope_header_signals(True, []) == ScopeHeaderSignals(
            container_running=True, fully_virtual=False, has_mounts=False,
        )

    def test_row5_running_has_bind(self):
        specs = [_spec("a", "bind")]
        assert resolve_scope_header_signals(True, specs) == ScopeHeaderSignals(
            container_running=True, fully_virtual=False, has_mounts=True,
        )

    def test_row6_running_fully_virtual(self):
        specs = [_spec("a", "detached")]
        assert resolve_scope_header_signals(True, specs) == ScopeHeaderSignals(
            container_running=True, fully_virtual=True, has_mounts=False,
        )


# ──────────────────────────────────────────────
# Invariant — mutual exclusion of fully_virtual and has_mounts
# ──────────────────────────────────────────────


class TestInvariant:
    @pytest.mark.parametrize("container_running", [False, True])
    def test_mixed_bind_and_detached_not_fully_virtual(
        self, container_running: bool,
    ):
        specs = [_spec("a", "bind"), _spec("b", "detached")]
        signals = resolve_scope_header_signals(container_running, specs)
        assert signals.fully_virtual is False
        assert signals.has_mounts is True
        # Invariant: never both True.
        assert not (signals.fully_virtual and signals.has_mounts)

    @pytest.mark.parametrize("container_running", [False, True])
    def test_mixed_bind_and_volume_not_fully_virtual(
        self, container_running: bool,
    ):
        specs = [_spec("a", "bind"), _spec("b", "volume")]
        signals = resolve_scope_header_signals(container_running, specs)
        assert signals.fully_virtual is False
        assert signals.has_mounts is True
        assert not (signals.fully_virtual and signals.has_mounts)


# ──────────────────────────────────────────────
# fully_virtual semantics — all non-bind, len > 0
# ──────────────────────────────────────────────


class TestFullyVirtualSemantics:
    def test_all_detached_is_fully_virtual(self):
        specs = [_spec("a", "detached"), _spec("b", "detached")]
        signals = resolve_scope_header_signals(False, specs)
        assert signals.fully_virtual is True
        assert signals.has_mounts is False

    def test_all_volume_is_fully_virtual(self):
        specs = [_spec("a", "volume"), _spec("b", "volume")]
        signals = resolve_scope_header_signals(False, specs)
        assert signals.fully_virtual is True
        assert signals.has_mounts is False

    def test_mixed_detached_volume_is_fully_virtual(self):
        # Both are delivery != "bind" → fully_virtual
        specs = [_spec("a", "detached"), _spec("b", "volume")]
        signals = resolve_scope_header_signals(False, specs)
        assert signals.fully_virtual is True
        assert signals.has_mounts is False

    def test_empty_list_is_not_fully_virtual(self):
        # fully_virtual requires 1+ specs
        signals = resolve_scope_header_signals(False, [])
        assert signals.fully_virtual is False


# ──────────────────────────────────────────────
# has_mounts semantics — any bind spec
# ──────────────────────────────────────────────


class TestHasMountsSemantics:
    def test_single_bind_has_mounts(self):
        signals = resolve_scope_header_signals(False, [_spec("a", "bind")])
        assert signals.has_mounts is True

    def test_bind_plus_any_other_has_mounts(self):
        specs = [_spec("a", "bind"), _spec("b", "detached"), _spec("c", "volume")]
        signals = resolve_scope_header_signals(False, specs)
        assert signals.has_mounts is True
        assert signals.fully_virtual is False

    def test_no_bind_no_mounts(self):
        specs = [_spec("a", "detached"), _spec("b", "volume")]
        signals = resolve_scope_header_signals(False, specs)
        assert signals.has_mounts is False


# ──────────────────────────────────────────────
# Unified mount_specs input — extension + user mix
# ──────────────────────────────────────────────


class TestUnifiedInput:
    """Caller passes user specs + extension-synthesized specs as one list."""

    def test_user_bind_plus_extension_volume(self):
        specs = [
            _spec("user_src", "bind", owner="user"),
            _spec("claude_auth", "volume", owner="extension:claude"),
        ]
        signals = resolve_scope_header_signals(True, specs)
        # Has bind from user → not fully_virtual, has_mounts True
        assert signals.has_mounts is True
        assert signals.fully_virtual is False

    def test_user_detached_plus_extension_volume_is_fully_virtual(self):
        specs = [
            _spec("user_vm", "detached", owner="user"),
            _spec("claude_auth", "volume", owner="extension:claude"),
        ]
        signals = resolve_scope_header_signals(True, specs)
        assert signals.fully_virtual is True
        assert signals.has_mounts is False


# ──────────────────────────────────────────────
# Dataclass shape — frozen + fields
# ──────────────────────────────────────────────


class TestDataclassShape:
    def test_is_frozen(self):
        signals = ScopeHeaderSignals(False, False, False)
        with pytest.raises((AttributeError, Exception)):
            signals.container_running = True  # type: ignore[misc]

    def test_fields_present(self):
        signals = ScopeHeaderSignals(
            container_running=True, fully_virtual=True, has_mounts=False,
        )
        assert signals.container_running is True
        assert signals.fully_virtual is True
        assert signals.has_mounts is False
