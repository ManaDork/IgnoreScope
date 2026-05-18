"""Tests for the marked-push queue (IgnoreScope.core.marked_push).

Pure file-I/O — no Docker, no config object. Covers round-trip, union/difference
mutation, the "delete the file when emptied" invariant, and absent-file handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.marked_push import (
    MARKED_PUSH_FILENAME,
    add_marked_push,
    clear_marked_push,
    load_marked_push,
    marked_push_path,
    remove_marked_push,
)


@pytest.fixture
def project(tmp_path):
    """A project root; the scope dir is created lazily by add_marked_push."""
    return tmp_path


SCOPE = "dev"


def _abs(project: Path, *parts: str) -> Path:
    return project.joinpath(*parts)


def test_path_location(project):
    p = marked_push_path(project, SCOPE)
    assert p == project / ".ignore_scope" / SCOPE / MARKED_PUSH_FILENAME


def test_absent_file_is_empty_set(project):
    assert load_marked_push(project, SCOPE) == set()
    assert not marked_push_path(project, SCOPE).exists()


def test_add_then_load_round_trip(project):
    a = _abs(project, "src", "a.txt")
    b = _abs(project, "b.txt")
    add_marked_push(project, SCOPE, [a, b])

    assert marked_push_path(project, SCOPE).exists()
    assert load_marked_push(project, SCOPE) == {a, b}


def test_add_is_a_union(project):
    a = _abs(project, "a.txt")
    b = _abs(project, "b.txt")
    c = _abs(project, "sub", "c.txt")
    add_marked_push(project, SCOPE, [a])
    add_marked_push(project, SCOPE, [b, c])
    add_marked_push(project, SCOPE, [a])  # idempotent re-add
    assert load_marked_push(project, SCOPE) == {a, b, c}


def test_add_empty_is_noop(project):
    add_marked_push(project, SCOPE, [])
    assert not marked_push_path(project, SCOPE).exists()
    assert load_marked_push(project, SCOPE) == set()


def test_remove_is_a_difference(project):
    a = _abs(project, "a.txt")
    b = _abs(project, "b.txt")
    c = _abs(project, "c.txt")
    add_marked_push(project, SCOPE, [a, b, c])
    remove_marked_push(project, SCOPE, [b])
    assert load_marked_push(project, SCOPE) == {a, c}


def test_remove_absent_path_is_harmless(project):
    a = _abs(project, "a.txt")
    add_marked_push(project, SCOPE, [a])
    remove_marked_push(project, SCOPE, [_abs(project, "never_added.txt")])
    assert load_marked_push(project, SCOPE) == {a}


def test_file_deleted_when_emptied_by_remove(project):
    a = _abs(project, "a.txt")
    b = _abs(project, "b.txt")
    add_marked_push(project, SCOPE, [a, b])
    assert marked_push_path(project, SCOPE).exists()

    remove_marked_push(project, SCOPE, [a, b])
    assert not marked_push_path(project, SCOPE).exists()
    assert load_marked_push(project, SCOPE) == set()


def test_clear_deletes_the_file(project):
    add_marked_push(project, SCOPE, [_abs(project, "a.txt")])
    assert marked_push_path(project, SCOPE).exists()
    clear_marked_push(project, SCOPE)
    assert not marked_push_path(project, SCOPE).exists()


def test_clear_on_absent_file_is_harmless(project):
    clear_marked_push(project, SCOPE)  # must not raise
    assert not marked_push_path(project, SCOPE).exists()


def test_serialization_is_relative_posix(project):
    import json

    a = _abs(project, "src", "deep", "a.txt")
    add_marked_push(project, SCOPE, [a])
    data = json.loads(marked_push_path(project, SCOPE).read_text(encoding="utf-8"))
    assert data == {"marked_push": ["src/deep/a.txt"]}


def test_corrupt_file_treated_as_empty(project):
    path = marked_push_path(project, SCOPE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not valid json", encoding="utf-8")
    assert load_marked_push(project, SCOPE) == set()


def test_scopes_are_independent(project):
    a = _abs(project, "a.txt")
    b = _abs(project, "b.txt")
    add_marked_push(project, "dev", [a])
    add_marked_push(project, "prod", [b])
    assert load_marked_push(project, "dev") == {a}
    assert load_marked_push(project, "prod") == {b}
