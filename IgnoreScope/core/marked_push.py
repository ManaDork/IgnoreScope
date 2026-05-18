"""Marked-push queue — transient pending-push records.

The marked-push queue holds host paths the user has asked to push but which
have not yet been confirmed present in the container. It is **config-first**:
"Push" enqueues here immediately, regardless of container state; a separate
drain routine (``docker/marked_push_drain.py``) performs the actual ``docker cp``
and, on success, promotes the path into ``pushed_files`` (the "confirmed in
container" set) and removes it from this queue.

File: ``{host_project_root}/.ignore_scope/{scope_name}/marked_push_scope.json``
(sibling of ``scope_docker_desktop.json``).

Schema: ``{"marked_push": ["rel/posix/path", ...]}`` — relative-POSIX paths,
the same convention used to serialize ``pushed_files``. An emptied queue file
is deleted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from .config import get_container_dir
from ..utils.paths import to_absolute_paths, to_relative_posix

logger = logging.getLogger(__name__)

MARKED_PUSH_FILENAME = "marked_push_scope.json"


def marked_push_path(host_project_root: Path, scope_name: str) -> Path:
    """Path to a scope's marked-push queue file (may not exist)."""
    return get_container_dir(host_project_root, scope_name) / MARKED_PUSH_FILENAME


def load_marked_push(host_project_root: Path, scope_name: str) -> set[Path]:
    """Load queued push paths as absolute Paths. Empty set if the file is absent or unreadable."""
    path = marked_push_path(host_project_root, scope_name)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Unreadable marked-push queue %s — treating as empty: %s", path, e)
        return set()
    return to_absolute_paths(data.get("marked_push", []), host_project_root)


def _write_marked_push(host_project_root: Path, scope_name: str, paths: set[Path]) -> None:
    """Persist the queue (relative-POSIX), or delete the file when the queue is empty."""
    path = marked_push_path(host_project_root, scope_name)
    if not paths:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    rel = sorted(to_relative_posix(p, host_project_root) for p in paths)
    path.write_text(json.dumps({"marked_push": rel}, indent=2), encoding="utf-8")


def add_marked_push(host_project_root: Path, scope_name: str, paths: Iterable[Path]) -> None:
    """Add paths to the queue (set union). Creates the file if needed; no-op on empty input."""
    new = {Path(p) for p in paths}
    if not new:
        return
    _write_marked_push(host_project_root, scope_name, load_marked_push(host_project_root, scope_name) | new)


def remove_marked_push(host_project_root: Path, scope_name: str, paths: Iterable[Path]) -> None:
    """Remove paths from the queue (set difference). Deletes the file once it becomes empty."""
    drop = {Path(p) for p in paths}
    if not drop:
        return
    _write_marked_push(host_project_root, scope_name, load_marked_push(host_project_root, scope_name) - drop)


def clear_marked_push(host_project_root: Path, scope_name: str) -> None:
    """Empty the queue and delete the file."""
    _write_marked_push(host_project_root, scope_name, set())