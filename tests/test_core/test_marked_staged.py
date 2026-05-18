"""Tests for the marked-staged queue (IgnoreScope.core.marked_staged).

Pure file-I/O — no Docker. Mirrors test_marked_push.py shape: round-trip,
union/difference, delete-when-empty, absent/corrupt handling. Also covers the
snapshot-path convention and the cleanup-consumed-snapshots helper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from IgnoreScope.core.marked_staged import (
    MARKED_STAGED_FILENAME,
    SNAPSHOTS_DIRNAME,
    StagedEntry,
    add_marked_staged,
    cleanup_consumed_snapshots,
    clear_marked_staged,
    load_marked_staged,
    marked_staged_path,
    snapshot_path_for,
    snapshots_dir,
    remove_marked_staged,
)

SCOPE = "dev"


@pytest.fixture
def project(tmp_path):
    return tmp_path


def _snap(project: Path, target: str) -> Path:
    return snapshot_path_for(project, SCOPE, target)


def _mkentry(project: Path, target: str, *, is_dir: bool = True) -> StagedEntry:
    return StagedEntry(source=_snap(project, target), target=target, is_dir=is_dir)


# ── Locations ──────────────────────────────────────────────────────


def test_path_location(project):
    assert marked_staged_path(project, SCOPE) == project / ".ignore_scope" / SCOPE / MARKED_STAGED_FILENAME


def test_snapshots_dir_location(project):
    assert snapshots_dir(project, SCOPE) == project / ".ignore_scope" / SCOPE / SNAPSHOTS_DIRNAME


def test_snapshot_path_for_lives_under_snapshots_dir(project):
    p = snapshot_path_for(project, SCOPE, "/Projects/foo/bar")
    assert p.parent == snapshots_dir(project, SCOPE)


def test_snapshot_path_for_uniqueness(project):
    # Different container targets → different host dirs.
    a = snapshot_path_for(project, SCOPE, "/Projects/foo")
    b = snapshot_path_for(project, SCOPE, "/Projects/bar")
    assert a != b


def test_snapshot_path_for_is_deterministic(project):
    a1 = snapshot_path_for(project, SCOPE, "/Projects/foo")
    a2 = snapshot_path_for(project, SCOPE, "/Projects/foo")
    assert a1 == a2


# ── Load / write basics ────────────────────────────────────────────


def test_absent_file_is_empty_set(project):
    assert load_marked_staged(project, SCOPE) == set()
    assert not marked_staged_path(project, SCOPE).exists()


def test_add_then_load_round_trip(project):
    e1 = _mkentry(project, "/Projects/foo", is_dir=True)
    e2 = _mkentry(project, "/Projects/bar.cfg", is_dir=False)
    add_marked_staged(project, SCOPE, [e1, e2])
    assert marked_staged_path(project, SCOPE).exists()
    assert load_marked_staged(project, SCOPE) == {e1, e2}


def test_add_is_a_union(project):
    a = _mkentry(project, "/A")
    b = _mkentry(project, "/B")
    c = _mkentry(project, "/C")
    add_marked_staged(project, SCOPE, [a])
    add_marked_staged(project, SCOPE, [b, c])
    add_marked_staged(project, SCOPE, [a])  # idempotent
    assert load_marked_staged(project, SCOPE) == {a, b, c}


def test_add_empty_is_noop(project):
    add_marked_staged(project, SCOPE, [])
    assert not marked_staged_path(project, SCOPE).exists()
    assert load_marked_staged(project, SCOPE) == set()


def test_remove_is_a_difference(project):
    a = _mkentry(project, "/A")
    b = _mkentry(project, "/B")
    c = _mkentry(project, "/C")
    add_marked_staged(project, SCOPE, [a, b, c])
    remove_marked_staged(project, SCOPE, [b])
    assert load_marked_staged(project, SCOPE) == {a, c}


def test_file_deleted_when_emptied_by_remove(project):
    a = _mkentry(project, "/A")
    add_marked_staged(project, SCOPE, [a])
    assert marked_staged_path(project, SCOPE).exists()
    remove_marked_staged(project, SCOPE, [a])
    assert not marked_staged_path(project, SCOPE).exists()
    assert load_marked_staged(project, SCOPE) == set()


def test_clear_deletes_the_file(project):
    add_marked_staged(project, SCOPE, [_mkentry(project, "/A")])
    assert marked_staged_path(project, SCOPE).exists()
    clear_marked_staged(project, SCOPE)
    assert not marked_staged_path(project, SCOPE).exists()


def test_clear_on_absent_file_is_harmless(project):
    clear_marked_staged(project, SCOPE)
    assert not marked_staged_path(project, SCOPE).exists()


def test_serialization_is_relative_posix(project):
    e = _mkentry(project, "/Projects/foo", is_dir=True)
    add_marked_staged(project, SCOPE, [e])
    data = json.loads(marked_staged_path(project, SCOPE).read_text(encoding="utf-8"))
    assert data == {
        "staged": [
            {
                "source": (
                    Path(".ignore_scope") / SCOPE / SNAPSHOTS_DIRNAME
                    / Path(e.source).name
                ).as_posix(),
                "target": "/Projects/foo",
                "is_dir": True,
            }
        ]
    }


def test_corrupt_file_treated_as_empty(project):
    path = marked_staged_path(project, SCOPE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")
    assert load_marked_staged(project, SCOPE) == set()


def test_malformed_entries_skipped(project):
    path = marked_staged_path(project, SCOPE)
    path.parent.mkdir(parents=True, exist_ok=True)
    good = {
        "source": (Path(".ignore_scope") / SCOPE / SNAPSHOTS_DIRNAME / "v_a").as_posix(),
        "target": "/A",
        "is_dir": True,
    }
    bad_missing_key = {"source": "x", "is_dir": False}
    path.write_text(json.dumps({"staged": [good, bad_missing_key]}), encoding="utf-8")
    loaded = load_marked_staged(project, SCOPE)
    assert len(loaded) == 1
    only = next(iter(loaded))
    assert only.target == "/A"


def test_scopes_are_independent(project):
    a = _mkentry(project, "/A")
    add_marked_staged(project, "dev", [a])
    assert load_marked_staged(project, "dev") == {a}
    assert load_marked_staged(project, "prod") == set()


def test_is_dir_round_trips(project):
    e_dir = _mkentry(project, "/dir-target", is_dir=True)
    e_file = _mkentry(project, "/file-target", is_dir=False)
    add_marked_staged(project, SCOPE, [e_dir, e_file])
    loaded = load_marked_staged(project, SCOPE)
    by_target = {x.target: x.is_dir for x in loaded}
    assert by_target == {"/dir-target": True, "/file-target": False}


# ── cleanup_consumed_snapshots ─────────────────────────────────────


def test_cleanup_removes_unconsumed_snapshot_dirs_kept_when_entry_remains(project):
    e = _mkentry(project, "/Projects/keep", is_dir=True)
    add_marked_staged(project, SCOPE, [e])
    # Materialise the snapshot dir on disk.
    e.source.mkdir(parents=True, exist_ok=True)
    (e.source / "file.txt").write_text("content", encoding="utf-8")

    cleanup_consumed_snapshots(project, SCOPE)
    # Entry still queued → snapshot dir survives.
    assert e.source.exists()


def test_cleanup_removes_consumed_snapshot_dirs(project):
    e_keep = _mkentry(project, "/Projects/keep", is_dir=True)
    e_drop = _mkentry(project, "/Projects/drop", is_dir=True)
    add_marked_staged(project, SCOPE, [e_keep, e_drop])
    for e in (e_keep, e_drop):
        e.source.mkdir(parents=True, exist_ok=True)
        (e.source / "file.txt").write_text("c", encoding="utf-8")

    # Simulate the drain having removed e_drop.
    remove_marked_staged(project, SCOPE, [e_drop])

    cleanup_consumed_snapshots(project, SCOPE)

    assert e_keep.source.exists()
    assert not e_drop.source.exists()


def test_cleanup_removes_empty_snapshots_root(project):
    e = _mkentry(project, "/Projects/drop", is_dir=True)
    add_marked_staged(project, SCOPE, [e])
    e.source.mkdir(parents=True, exist_ok=True)

    remove_marked_staged(project, SCOPE, [e])
    cleanup_consumed_snapshots(project, SCOPE)

    assert not snapshots_dir(project, SCOPE).exists()


def test_cleanup_on_absent_snapshots_dir_is_harmless(project):
    # Nothing on disk, nothing queued — must not raise.
    cleanup_consumed_snapshots(project, SCOPE)
    assert not snapshots_dir(project, SCOPE).exists()


def test_cleanup_keeps_dir_when_entry_source_is_nested(project):
    e = _mkentry(project, "/Projects/foo", is_dir=True)
    add_marked_staged(project, SCOPE, [e])
    # Materialise as a nested tree to ensure ancestor-walk recognises the dir as live.
    (e.source / "nested").mkdir(parents=True, exist_ok=True)
    (e.source / "nested" / "file.txt").write_text("x", encoding="utf-8")

    cleanup_consumed_snapshots(project, SCOPE)
    assert e.source.exists()
    assert (e.source / "nested" / "file.txt").exists()
