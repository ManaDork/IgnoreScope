"""Marked-staged queue — deferred ``docker cp`` of a host-side snapshot into a container.

Sibling to ``core.marked_push``. The two files together feed a single drain engine
(``docker/marked_push_drain.py``) which is the lone code path for ``docker cp ... → cname:...``.

The split:
  - ``marked_push_scope.json``  — host-source queue (live host files; staleness-checked;
    drained promote into ``pushed_files``).
  - ``marked_staged_scope.json`` — staged-source queue (host snapshots taken from a
    container path before a recreate; drained do **not** touch ``pushed_files``).

File: ``{host_project_root}/.ignore_scope/{scope_name}/marked_staged_scope.json``.

Schema::

    {"staged": [{"source": "rel/posix", "target": "/container/abs", "is_dir": bool}, ...]}

``source`` is relative-POSIX, anchored at ``host_project_root`` — by convention it
points under ``.ignore_scope/<scope>/_snapshots/<sanitize(target)>/``. ``target`` is
the container-absolute path the entry restores into. ``is_dir`` picks the cp shape:
True → ``docker cp source/. cname:target`` (merge contents into an existing dir);
False → ``docker cp source cname:target`` (replace a file).

An emptied queue file is deleted (same invariant as ``marked_push_scope.json``).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import get_container_dir
from ..utils.strings import sanitize_volume_name

logger = logging.getLogger(__name__)

MARKED_STAGED_FILENAME = "marked_staged_scope.json"
SNAPSHOTS_DIRNAME = "_snapshots"


@dataclass(frozen=True)
class StagedEntry:
    """A deferred staged-source restore.

    Frozen so the dataclass is hashable, enabling set-union/-difference mutation
    matching ``marked_push.py``'s queue semantics.
    """

    source: Path   # absolute on disk; serialized relative to host_project_root
    target: str    # container-absolute path
    is_dir: bool   # True -> merge dir contents; False -> replace file


def marked_staged_path(host_project_root: Path, scope_name: str) -> Path:
    """Path to a scope's marked-staged queue file (may not exist)."""
    return get_container_dir(host_project_root, scope_name) / MARKED_STAGED_FILENAME


def snapshots_dir(host_project_root: Path, scope_name: str) -> Path:
    """Path to a scope's persistent staged-source snapshots directory."""
    return get_container_dir(host_project_root, scope_name) / SNAPSHOTS_DIRNAME


def snapshot_path_for(host_project_root: Path, scope_name: str, container_target: str) -> Path:
    """Conventional host-side snapshot directory for a given container target.

    Targets are unique within a scope (the mount-spec validator rejects overlapping
    container paths), so ``sanitize_volume_name(container_target)`` is a stable
    one-to-one host-side name.
    """
    return snapshots_dir(host_project_root, scope_name) / sanitize_volume_name(container_target)


def load_marked_staged(host_project_root: Path, scope_name: str) -> set[StagedEntry]:
    """Load queued staged entries. Empty set if the file is absent or unreadable."""
    path = marked_staged_path(host_project_root, scope_name)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Unreadable marked-staged queue %s — treating as empty: %s", path, e)
        return set()
    entries: set[StagedEntry] = set()
    for raw in data.get("staged", []):
        try:
            source_rel = raw["source"]
            target = raw["target"]
            is_dir = bool(raw["is_dir"])
        except (KeyError, TypeError) as e:
            logger.warning("Skipping malformed staged entry in %s: %s", path, e)
            continue
        source_path = Path(source_rel)
        if not source_path.is_absolute():
            source_path = host_project_root / source_path
        entries.add(StagedEntry(source=source_path, target=str(target), is_dir=is_dir))
    return entries


def _write_marked_staged(
    host_project_root: Path, scope_name: str, entries: set[StagedEntry],
) -> None:
    """Persist the queue, or delete the file when the queue is empty."""
    path = marked_staged_path(host_project_root, scope_name)
    if not entries:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = []
    for e in sorted(entries, key=lambda x: (x.target, x.source.as_posix())):
        try:
            source_rel = e.source.relative_to(host_project_root).as_posix()
        except ValueError:
            # Source escapes the project root — keep the absolute form (POSIX).
            logger.warning(
                "marked_staged: source %s escapes project root %s; storing absolute path",
                e.source, host_project_root,
            )
            source_rel = e.source.as_posix()
        serialized.append({"source": source_rel, "target": e.target, "is_dir": e.is_dir})
    path.write_text(json.dumps({"staged": serialized}, indent=2), encoding="utf-8")


def add_marked_staged(
    host_project_root: Path, scope_name: str, entries: Iterable[StagedEntry],
) -> None:
    """Add entries to the queue (set union). Creates the file if needed; no-op on empty input."""
    new = set(entries)
    if not new:
        return
    _write_marked_staged(
        host_project_root, scope_name,
        load_marked_staged(host_project_root, scope_name) | new,
    )


def remove_marked_staged(
    host_project_root: Path, scope_name: str, entries: Iterable[StagedEntry],
) -> None:
    """Remove entries from the queue (set difference). Deletes the file once empty."""
    drop = set(entries)
    if not drop:
        return
    _write_marked_staged(
        host_project_root, scope_name,
        load_marked_staged(host_project_root, scope_name) - drop,
    )


def clear_marked_staged(host_project_root: Path, scope_name: str) -> None:
    """Empty the queue and delete the file."""
    _write_marked_staged(host_project_root, scope_name, set())


def cleanup_consumed_snapshots(host_project_root: Path, scope_name: str) -> None:
    """Remove on-disk snapshot dirs whose staged entries have been drained.

    For each subdirectory under ``_snapshots/``, rmtree it iff no remaining
    ``StagedEntry.source`` is under it. Remove an empty ``_snapshots/`` itself.

    Best-effort: never raises. Canonical caller is
    ``docker.marked_push_drain.drain_with_user_feedback``, which invokes this
    after every drain — so lifecycle, GUI, and CLI drain paths all clean
    uniformly. A failed drain leaves the dirs alongside the still-queued
    staged entries (so the next drain reattempts from the same snapshots);
    only consumed-entry dirs are removed.
    """
    snaps_root = snapshots_dir(host_project_root, scope_name)
    if not snaps_root.exists():
        return
    try:
        remaining = load_marked_staged(host_project_root, scope_name)
        live_dirs: set[Path] = set()
        for e in remaining:
            # Walk upward from each entry source so any ancestor under snaps_root counts.
            p = e.source
            while True:
                try:
                    p.relative_to(snaps_root)
                except ValueError:
                    break
                live_dirs.add(p)
                if p == snaps_root:
                    break
                p = p.parent

        for child in list(snaps_root.iterdir()):
            if child in live_dirs:
                continue
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            except Exception:
                logger.debug("Failed to remove staged snapshot %s", child, exc_info=True)

        # Remove the snapshots root itself if it's now empty.
        try:
            next(snaps_root.iterdir())
        except StopIteration:
            try:
                snaps_root.rmdir()
            except OSError:
                logger.debug("Failed to rmdir empty %s", snaps_root, exc_info=True)
    except Exception:
        logger.debug("cleanup_consumed_snapshots swallowed error for %s", snaps_root, exc_info=True)
