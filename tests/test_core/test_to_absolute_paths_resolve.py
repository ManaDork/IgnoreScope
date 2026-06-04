"""Regression tests for ``IgnoreScope.utils.paths.to_absolute_paths``.

Phase B.5's path-case fragility fix (F.4 of ``feature/rmb-remove-marked-pushed``):
``to_absolute_paths`` now ``.resolve()``s each reconstructed path so
downstream callers — notably ``apply_node_states_from_scope`` Stage 4's
case-sensitive ``path in states`` check on Windows — see canonical case
regardless of any drift in the JSON entries.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from IgnoreScope.utils.paths import to_absolute_paths


def test_relative_paths_are_resolved_against_base_root(tmp_path: Path):
    """Standard case: relative-POSIX entries are joined + resolved."""
    src = tmp_path / "src"
    src.mkdir()
    target = src / "a.txt"
    target.write_text("x", encoding="utf-8")

    result = to_absolute_paths(["src/a.txt"], tmp_path)

    assert len(result) == 1
    assert next(iter(result)) == target.resolve()


def test_absolute_paths_pass_through_resolved(tmp_path: Path):
    """Absolute entries are still resolved (no base_root join)."""
    target = tmp_path / "f.txt"
    target.write_text("x", encoding="utf-8")

    result = to_absolute_paths([str(target)], tmp_path)

    assert len(result) == 1
    assert next(iter(result)) == target.resolve()


def test_resolve_normalizes_case_on_case_insensitive_fs(tmp_path: Path):
    """On Windows the FS is case-insensitive but ``Path.__eq__`` is case-
    sensitive. ``to_absolute_paths`` resolves to the disk's canonical case
    so consumers using ``path in states`` survive case drift in the JSON.

    This is the regression that motivated the F.4 fix: a queue entry
    with non-canonical casing was being reconstructed without resolution,
    and Stage 4's ``path in states`` check silently missed it.
    """
    if sys.platform != "win32":
        pytest.skip("case-insensitive FS behavior is Windows-specific")

    # Create disk artifact with one casing.
    real_dir = tmp_path / "MixedCase"
    real_dir.mkdir()
    real_file = real_dir / "Target.TXT"
    real_file.write_text("x", encoding="utf-8")

    # Queue entry uses a different casing (simulates JSON drift).
    drifted_relative = "mixedcase/target.txt"
    result = to_absolute_paths([drifted_relative], tmp_path)

    canonical = real_file.resolve()
    assert canonical in result, (
        f"resolved set should contain the canonical-cased path; "
        f"got {result}, expected to contain {canonical}"
    )


def test_resolve_falls_back_on_nonexistent_paths(tmp_path: Path):
    """``Path.resolve`` on a nonexistent path returns the absolute path
    unchanged (no error). The set still gets a populated entry.
    """
    result = to_absolute_paths(["does_not_exist.txt"], tmp_path)

    assert len(result) == 1
    p = next(iter(result))
    assert p.is_absolute()
    assert p.name == "does_not_exist.txt"


def test_empty_input_returns_empty_set(tmp_path: Path):
    assert to_absolute_paths([], tmp_path) == set()


def test_round_trip_through_marked_push(tmp_path: Path):
    """End-to-end: ``add_marked_push`` writes a relative entry; ``load_marked_push``
    reconstructs through ``to_absolute_paths``; the resulting path is
    equal-by-Path to the original target. This pins the downstream
    invariant Stage 4 relies on.
    """
    src = tmp_path / "src"
    src.mkdir()
    target = src / "a.txt"
    target.write_text("x", encoding="utf-8")

    from IgnoreScope.core.marked_push import add_marked_push, load_marked_push

    add_marked_push(tmp_path, "dev", [target])
    reconstructed = load_marked_push(tmp_path, "dev")

    assert target.resolve() in reconstructed, (
        f"round-trip through marked_push should preserve path equality; "
        f"target={target}, target.resolve()={target.resolve()}, got {reconstructed}"
    )
