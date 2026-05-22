"""Marked-push drain — perform queued ``docker cp`` operations, promote host pushes to ``pushed_files``.

The single ``docker cp ... → cname:...`` engine. Serves: manual Push (GUI), the
``push-marked`` CLI, the GUI scope-load prompt, and the Create/Update/Recreate
lifecycle.

Two queues, one engine:
  - ``marked_push_scope.json``  (host queue) — live host files; staleness-checked;
    a successful drain **promotes** the path into ``config.pushed_files`` and
    removes it from the queue.
  - ``marked_staged_scope.json`` (staged queue) — host snapshots of container
    paths produced by the preserve flow; no staleness check; a successful drain
    leaves ``config.pushed_files`` **untouched** and removes the entry. The
    drain self-creates the container target (and parent for files), so callers
    do not need to pre-``mkdir``.

Snapshots live under ``.ignore_scope/<scope>/_snapshots/<sanitize(target)>/`` and
are removed by ``core.marked_staged.cleanup_consumed_snapshots`` *after* the
drain — a failed drain keeps the dirs alongside the still-queued entries so the
next drain reattempts from the same snapshots.

Ordering: host entries first (today's behavior), then staged entries.

IS:  drain orchestration (read queues → resolve container state → per-entry cp →
     promote host successes / dequeue) and host-vs-container staleness compare.
IS NOT: subprocess calls (→ ``container_ops.py``), queue persistence
     (→ ``core/marked_push.py``, ``core/marked_staged.py``).

Contract carve-out: the drain is the canonical writer to ``config.pushed_files``
for paths confirmed by ``docker cp``. Extension-deployed paths confirmed via
``exec_in_container`` (see ``container_ext/workflow_setup.py``) may write to
``pushed_files`` directly — both writers preserve the invariant that
``pushed_files`` reflects what's actually in the container.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath
from typing import Callable, Literal, Optional

from ..core.config import ScopeDockerConfig, load_config, save_config
from ..core.marked_push import load_marked_push, remove_marked_push
from ..core.marked_staged import (
    StagedEntry,
    cleanup_consumed_snapshots,
    load_marked_staged,
    remove_marked_staged,
)
from ..core.op_result import OpError, OpResult
from .container_ops import (
    exec_in_container,
    get_container_info,
    ensure_container_running,
    ensure_container_directories,
    push_directory_contents_to_container,
    push_file_to_container,
)
from .file_ops import resolve_container_path
from .names import build_docker_name

logger = logging.getLogger(__name__)

StaleAction = Literal["replace", "skip", "skip_and_unmark"]


def container_file_mtime(
    container_name: str, container_path: str, timeout: int = 10,
) -> Optional[float]:
    """Return a container file's mtime (epoch seconds), or None if absent / stat fails."""
    ok, stdout, _ = exec_in_container(
        container_name, ["stat", "-c", "%Y", container_path], timeout,
    )
    if not ok or not stdout:
        return None
    try:
        return float(stdout.strip())
    except ValueError:
        return None


def _resolve_stale_action(
    on_stale: "Callable[[Path], str] | str | None", host_path: Path,
) -> StaleAction:
    if on_stale is None:
        return "skip"
    action = on_stale(host_path) if callable(on_stale) else on_stale
    if action not in ("replace", "skip", "skip_and_unmark"):
        return "skip"
    return action  # type: ignore[return-value]


def drain_marked_push(
    host_project_root: Path,
    scope_name: str,
    *,
    config: Optional[ScopeDockerConfig] = None,
    on_stale: "Callable[[Path], str] | str | None" = None,
    progress: "Callable[[int, int], None] | None" = None,
) -> OpResult:
    """Drain the marked-push and marked-staged queues into the container.

    Reads both ``marked_push_scope.json`` (host queue) and
    ``marked_staged_scope.json`` (staged queue) and performs the deferred
    ``docker cp``s. Host successes promote into ``config.pushed_files``;
    staged successes do not touch ``pushed_files``.

    Container state handling (applies to both queues):
      - missing  → no-op success; queues intact (the next Create Container drains them).
      - stopped  → start it; on failure → failure (queues intact).
      - running  → proceed.

    Per host entry (sorted), with ``progress(current, total)`` callbacks:
      - host file missing on disk → noted, left queued.
      - container copy newer-or-equal to host (host is stale) → ``on_stale(host_path)``:
          ``"replace"``         → cp.
          ``"skip"``            → noted, left queued (re-prompts next drain).
          ``"skip_and_unmark"`` → removed from queue AND from ``pushed_files``.
      - otherwise → ensure parent dir, cp:
          success → added to ``pushed_files``, removed from queue.
          failure → noted, left queued.

    Per staged entry (sorted by target), processed *after* the host queue:
      - source snapshot missing on disk → dropped (the entry can never restore);
        noted.
      - ``is_dir=True`` → ensure the container target dir, then
        ``docker cp source/. cname:target`` (merge contents). Success removes
        the entry; ``pushed_files`` is unchanged.
      - ``is_dir=False`` → ensure the container parent dir, then
        ``docker cp source cname:target`` (replace file). Success removes
        the entry; ``pushed_files`` is unchanged.
      - failure → noted, left queued (so the next drain — manual ``push-marked``
        or scope-load prompt — reattempts from the persistent snapshot).

    Staged-snapshot cleanup runs inline at the end of every drain through the
    ``drain_with_user_feedback`` wrapper (the canonical entry point). Direct
    callers of ``drain_marked_push`` are responsible for invoking
    ``core.marked_staged.cleanup_consumed_snapshots`` themselves — but in the
    standard pipeline the wrapper owns this.

    Args:
        host_project_root: Project root directory.
        scope_name: Scope name.
        config: Optional in-flight config to mutate (lifecycle path). When given,
            its ``pushed_files`` set is updated but the caller owns ``save_config``.
            When None, config is loaded here and saved if it became dirty.
        on_stale: Resolution for host-stale files — a ``(host_path) -> action``
            callback, a fixed action string, or None (defaults to ``"skip"``).
            Only applies to host entries; staged entries are not staleness-checked.
        progress: Optional ``(current, total)`` callback invoked before each entry
            (host and staged combined, host first).

    Returns:
        OpResult — ``success`` is False only on a fatal precondition (a stopped
        container that won't start); per-entry cp failures are not fatal.
        ``details`` carries per-entry notes.
    """
    marked = sorted(load_marked_push(host_project_root, scope_name))
    staged = sorted(
        load_marked_staged(host_project_root, scope_name),
        key=lambda e: (e.target, e.source.as_posix()),
    )
    if not marked and not staged:
        return OpResult(success=True, message="No files queued for push")

    owns_config = config is None
    if owns_config:
        try:
            config = load_config(host_project_root, scope_name)
        except Exception as e:
            return OpResult(
                success=False,
                message=f"Failed to load config: {e}",
                error=OpError.CONFIG_LOAD_FAILED,
            )

    docker_name = build_docker_name(host_project_root, config.scope_name or scope_name)
    container_root = config.container_root
    host_container_root = config.host_container_root or host_project_root.parent

    info = get_container_info(docker_name)
    queued_n = len(marked) + len(staged)
    if info is None:
        return OpResult(
            success=True,
            message=f"Container not created — {queued_n} file(s) still queued",
        )
    if not info.get("running", False):
        ok, msg = ensure_container_running(docker_name)
        if not ok:
            return OpResult(
                success=False,
                message=f"Container '{docker_name}' could not be started: {msg}",
                error=OpError.CONTAINER_NOT_RUNNING,
            )

    total = queued_n
    notes: list[str] = []
    n_pushed = 0
    dirty = False
    step = 0

    # Host queue first: live files, staleness-checked, promotes into pushed_files.
    for host_path in marked:
        step += 1
        if progress is not None:
            progress(step, total)

        if not host_path.exists():
            notes.append(f"host file missing, left queued: {host_path}")
            continue

        cpath = resolve_container_path(host_path, container_root, host_container_root)

        container_mtime = container_file_mtime(docker_name, cpath)
        if container_mtime is not None and container_mtime >= host_path.stat().st_mtime:
            action = _resolve_stale_action(on_stale, host_path)
            if action == "skip":
                notes.append(f"skipped (host older), left queued: {host_path}")
                continue
            if action == "skip_and_unmark":
                remove_marked_push(host_project_root, scope_name, [host_path])
                if host_path in config.pushed_files:
                    config.pushed_files.discard(host_path)
                    dirty = True
                notes.append(f"skipped and unmarked: {host_path}")
                continue
            # action == "replace" → fall through to cp.

        parent_dir = str(PurePosixPath(cpath).parent)
        if parent_dir not in ("/", ".", ""):
            dir_ok, dir_msg = ensure_container_directories(docker_name, [parent_dir])
            if not dir_ok:
                notes.append(f"cp failed (mkdir parent): {host_path} — {dir_msg}")
                continue

        ok, msg = push_file_to_container(docker_name, host_path, cpath)
        if ok:
            remove_marked_push(host_project_root, scope_name, [host_path])
            if host_path not in config.pushed_files:
                config.pushed_files.add(host_path)
                dirty = True
            n_pushed += 1
        else:
            notes.append(f"cp failed, left queued: {host_path} — {msg}")

    # Staged queue: host snapshots produced by preserve. No staleness, no
    # pushed_files mutation. The drain self-mkdir's the target (or its parent
    # for a file entry) so callers do not need to pre-mkdir.
    for entry in staged:
        step += 1
        if progress is not None:
            progress(step, total)

        if not entry.source.exists():
            # The on-disk snapshot is gone — there's nothing to restore. Drop
            # the entry so the queue doesn't permanently fail.
            remove_marked_staged(host_project_root, scope_name, [entry])
            notes.append(f"staged snapshot missing, dropped: {entry.target}")
            continue

        if entry.is_dir:
            dir_ok, dir_msg = ensure_container_directories(docker_name, [entry.target])
            if not dir_ok:
                notes.append(
                    f"staged restore failed (mkdir target): {entry.target} — {dir_msg}",
                )
                continue
            ok, msg = push_directory_contents_to_container(
                docker_name, entry.source, entry.target,
            )
        else:
            parent_dir = str(PurePosixPath(entry.target).parent)
            if parent_dir not in ("/", ".", ""):
                dir_ok, dir_msg = ensure_container_directories(docker_name, [parent_dir])
                if not dir_ok:
                    notes.append(
                        f"staged restore failed (mkdir parent): {entry.target} — {dir_msg}",
                    )
                    continue
            ok, msg = push_file_to_container(docker_name, entry.source, entry.target)

        if ok:
            remove_marked_staged(host_project_root, scope_name, [entry])
            n_pushed += 1
        else:
            notes.append(f"staged restore failed, left queued: {entry.target} — {msg}")

    if owns_config and dirty:
        try:
            save_config(config)
        except Exception as e:
            notes.append(f"warning: failed to save config: {e}")

    remaining = (
        len(load_marked_push(host_project_root, scope_name))
        + len(load_marked_staged(host_project_root, scope_name))
    )
    summary = f"Drained {n_pushed} file(s)"
    if remaining:
        summary += f", {remaining} still queued"
    return OpResult(success=True, message=summary, details=notes)


def drain_with_user_feedback(
    host_project_root: Path,
    scope_name: str,
    *,
    config: Optional[ScopeDockerConfig] = None,
    progress_cb: "Callable[[int, int], None] | None" = None,
    on_stale_cb: "Callable[[Path], str] | str | None" = None,
) -> OpResult:
    """Single drain entry-point shared by lifecycle, GUI, and CLI.

    Wraps ``drain_marked_push`` and runs ``cleanup_consumed_snapshots`` at the
    end of every drain (success or no-op). All callers route through this
    function so feedback (progress, stale resolution) flows uniformly and
    snapshot cleanup happens in exactly one place.

    Caller ``on_stale_cb`` contract:
      - Lifecycle (``execute_create``, ``execute_update``): ``"replace"`` —
        orchestrator owns the canonical state; the freshly (re)created
        container has nothing to be stale against.
      - GUI drain (``drain_marked_push_now``): callable prompt
        (``_confirm_stale``) — user decides per file.
      - CLI ``cmd_push`` with ``--force``: ``"replace"``; without flag:
        ``"skip"``.
      - None (default): treated as ``"skip"`` by ``drain_marked_push``.

    Args:
        host_project_root: Project root directory.
        scope_name: Scope name.
        config: Optional in-flight config to mutate (lifecycle path); caller
            owns ``save_config``. When ``None``, the drain loads + saves.
        progress_cb: Optional ``(current, total)`` callback invoked before
            each entry (host and staged combined, host first). ``None`` =
            silent.
        on_stale_cb: Resolution for host-stale files — callable, fixed action
            string, or ``None``. See contract above.

    Returns:
        OpResult from the underlying drain. Cleanup is best-effort and never
        raises; cleanup failures do not affect the returned result.
    """
    result = drain_marked_push(
        host_project_root, scope_name,
        config=config, on_stale=on_stale_cb, progress=progress_cb,
    )
    cleanup_consumed_snapshots(host_project_root, scope_name)
    return result