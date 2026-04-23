"""CORE container lifecycle orchestrators.

IS:  Create/update/remove container orchestration as CORE functions.
     Pipeline: preflight → hierarchy → compose → build → deploy → reconcile → save.
     Extension reconciliation (verify/re-deploy) after container start.
     Both GUI and CLI consume these — neither owns the orchestration.

IS NOT: Subprocess calls (→ container_ops.py)
        File operations (→ file_ops.py)
        Compose generation (→ compose.py)

Uses OpResult for standardized returns.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath

from ..core.config import (
    CONFIG_FILENAME,
    ScopeDockerConfig,
    load_config,
    save_config,
    get_container_dir,
)
from ..core.mount_spec_path import MountSpecPath
# NOTE: core.hierarchy imported lazily inside functions to avoid circular import.
# Chain: core/hierarchy -> docker/__init__ -> container_lifecycle -> core/hierarchy
from ..core.op_result import OpError, OpResult
from .container_ops import (
    is_docker_running,
    build_image,
    create_container_compose,
    remove_container_compose,
    ensure_container_running,
    ensure_container_directories,
    exec_in_container,
    push_file_to_container,
    push_directory_contents_to_container,
    pull_file_from_container,
    container_exists,
    volume_exists,
    remove_volume,
)

logger = logging.getLogger(__name__)
from .compose import generate_compose_with_masks, generate_dockerfile
from .file_ops import execute_push_batch
from .names import DockerNames, build_docker_name
from ..utils.strings import sanitize_volume_name


_EMPTY_MOUNT_SPECS_WARNING = (
    "Detached init: no mount_specs — container has only extensions + auth. "
    "Add mount_specs or push files manually."
)


def _is_reparse_point(p: Path) -> bool:
    """True for POSIX symlinks OR Windows reparse points (junctions, mount points)."""
    try:
        if p.is_symlink():
            return True
    except OSError:
        return False
    if os.name == "nt":
        try:
            st = os.lstat(p)
            attrs = getattr(st, "st_file_attributes", 0)
            return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except (OSError, AttributeError):
            return False
    return False


def _detached_init(
    docker_name: str,
    config: ScopeDockerConfig,
) -> OpResult:
    """Populate detached mount_specs via docker cp + rm (tree-seed) or mkdir (folder-seed).

    For each ``delivery == "detached"`` spec in ``config.mount_specs``:

    Tree-seed (``content_seed == "tree"``, host_path set):
      1. cp the mount_root into its container path.
      2. cp each reveal pattern (negated) target into its container path.
      3. rm -rf each mask pattern target inside the container.
      4. Symlinks / Windows reparse points get a mkdir stub; traversal stops
         at the link so the target is never cp'd.

    Folder-seed (``content_seed == "folder"``):
      1. mkdir -p the container path. No cp walk. No mask/reveal (validator
         rejects patterns on folder-seed specs).
      2. Works for both host-backed folder-seed (``host_path`` set) and
         container-only (``host_path is None``) — the latter's ``mount_root``
         is interpreted as a container-logical path.

    Caller is responsible for only invoking this when at least one spec has
    ``delivery == "detached"`` (see dispatch site for bind-only skip). An
    empty ``mount_specs`` list returns a no-op success; this should not
    happen in practice but is handled defensively.

    Args:
        docker_name: Resolved Docker container name.
        config: ScopeDockerConfig with mount_specs already validated.

    Returns:
        OpResult with per-spec details aggregated under ``details``.
    """
    from ..core.hierarchy import to_container_path

    if not config.mount_specs:
        return OpResult(
            success=True,
            message="Detached init: no mount_specs",
            details=[_EMPTY_MOUNT_SPECS_WARNING],
        )

    detached_specs = [ms for ms in config.mount_specs if ms.delivery == "detached"]
    if not detached_specs:
        return OpResult(success=True, message="Detached init: no detached specs")

    running_ok, running_msg = ensure_container_running(docker_name)
    if not running_ok:
        return OpResult(
            success=False,
            message=f"Container not running: {running_msg}",
            error=OpError.CONTAINER_NOT_RUNNING,
        )

    cp_pairs: list[tuple[Path, str]] = []
    folder_seed_cpaths: list[str] = []
    rm_container_paths: list[str] = []

    for ms in detached_specs:
        # Resolve this spec's container-side mount_root path. For container-only
        # specs (host_path is None) mount_root is already container-logical;
        # for host-backed specs translate via host_container_root → container_root.
        if ms.host_path is None:
            root_cpath = ms.mount_root.as_posix()
        else:
            root_cpath = to_container_path(
                ms.mount_root, config.container_root, config.host_container_root,
            )

        if ms.content_seed == "folder":
            # Folder-seed: mkdir only. Validator guarantees ms.patterns is empty.
            folder_seed_cpaths.append(root_cpath)
            continue

        # Tree-seed: cp walk with mask/reveal. Validator guarantees host_path
        # is set for tree-seed (container-only is folder-seed only).
        cp_pairs.append((ms.mount_root, root_cpath))
        for pattern in ms.patterns:
            is_exception = pattern.startswith("!")
            folder = pattern.lstrip("!").rstrip("/")
            if folder.endswith("/**"):
                folder = folder[:-3]
            elif folder.endswith("/*"):
                folder = folder[:-2]
            if not folder:
                continue
            abs_path = ms.mount_root / folder
            cpath = to_container_path(abs_path, config.container_root, config.host_container_root)
            if is_exception:
                # Reveal → included in cp walk.
                cp_pairs.append((abs_path, cpath))
            else:
                # Mask → post-cp rm inside the container.
                rm_container_paths.append(cpath)

    # mkdir -p: (a) parents of cp targets so cp can land, (b) full folder-seed
    # container paths (no cp follows).
    mkdir_targets: set[str] = set()
    for _, cpath in cp_pairs:
        parent_dir = str(PurePosixPath(cpath).parent)
        if parent_dir and parent_dir != config.container_root and parent_dir != "/":
            mkdir_targets.add(parent_dir)
    mkdir_targets.update(folder_seed_cpaths)
    if mkdir_targets:
        dir_ok, dir_msg = ensure_container_directories(docker_name, sorted(mkdir_targets))
        if not dir_ok:
            return OpResult(
                success=False,
                message=f"Failed to create container directories: {dir_msg}",
                error=OpError.VALIDATION_FAILED,
            )

    details: list[str] = []
    n_ok = 0
    for host_path, cpath in cp_pairs:
        if _is_reparse_point(host_path):
            ensure_container_directories(docker_name, [cpath])
            details.append(f"skipped symlink (stub created): {host_path} -> {cpath}")
            continue
        ok, msg = push_file_to_container(docker_name, host_path, cpath)
        if ok:
            n_ok += 1
        else:
            details.append(f"cp failed: {host_path} -> {cpath}: {msg}")

    for cpath in folder_seed_cpaths:
        details.append(f"folder-seed: mkdir -p {cpath}")

    # Apply masks by removing their container paths after the cp walk.
    for cpath in rm_container_paths:
        ok, _stdout, stderr = exec_in_container(docker_name, ["rm", "-rf", cpath])
        if ok:
            details.append(f"masked: rm -rf {cpath}")
        else:
            details.append(
                f"mask rm failed: {cpath}: {stderr or 'Unknown error'}"
            )

    return OpResult(
        success=True,
        message=(
            f"Detached init: {n_ok}/{len(cp_pairs)} cp'd, "
            f"{len(folder_seed_cpaths)} folder-seeded"
        ),
        details=details,
    )


_PRESERVE_STAGING_PREFIX = "ignorescope_preserve_"


def _resolve_spec_container_path(
    ms: MountSpecPath, config: ScopeDockerConfig,
) -> str:
    """Resolve the container-side path for a folder-seed spec.

    Mirrors the resolution inside ``_detached_init``: container-only specs
    (``host_path is None``) treat ``mount_root`` as already container-logical;
    host-backed specs translate through host_container_root → container_root.
    """
    from ..core.hierarchy import to_container_path

    if ms.host_path is None:
        return ms.mount_root.as_posix()
    return to_container_path(
        ms.mount_root, config.container_root, config.host_container_root,
    )


def _preserve_detached_folders(
    docker_name: str,
    config: ScopeDockerConfig,
    staging_root: Path,
) -> tuple[OpResult, dict[int, tuple[str, Path]]]:
    """Snapshot container contents of every ``preserve_on_update=True`` spec to host.

    Runs BEFORE ``docker compose down`` so the running container's writable
    layer is still readable. For each spec with ``preserve_on_update=True``:
      - If its container path exists, ``docker cp`` it to ``staging_root/spec_{idx}``.
      - If missing (first-ever update, or content removed), skip with a note —
        the corresponding restore is a no-op.

    Fail-safe: any cp-out failure aborts the update, leaving the old container
    untouched. The caller must NOT proceed to compose-down on ``success=False``.

    Args:
        docker_name: Running Docker container name.
        config: ScopeDockerConfig (new target config; preserve_on_update flags
            determine which specs to snapshot).
        staging_root: Pre-created host tmp directory. Per-spec snapshots land at
            ``staging_root / f"spec_{idx}"`` (which must NOT pre-exist — docker
            cp creates the destination).

    Returns:
        Tuple of (OpResult, snapshots_map). ``snapshots_map`` is keyed by
        mount_specs index and maps to ``(container_path, host_snapshot_dir)``.
        On abort, snapshots_map is empty.
    """
    preserve_specs = [
        (i, ms) for i, ms in enumerate(config.mount_specs) if ms.preserve_on_update
    ]
    if not preserve_specs:
        return OpResult(success=True, message="No preserve specs"), {}

    running_ok, running_msg = ensure_container_running(docker_name)
    if not running_ok:
        return OpResult(
            success=False,
            message=f"Preserve aborted — container not running: {running_msg}",
            error=OpError.CONTAINER_NOT_RUNNING,
        ), {}

    snapshots: dict[int, tuple[str, Path]] = {}
    details: list[str] = []

    for idx, ms in preserve_specs:
        cpath = _resolve_spec_container_path(ms, config)
        snap_dir = staging_root / f"spec_{idx}"

        # test -e: any filesystem entry (file, dir, symlink). Missing path is
        # a normal first-time-preserve case; don't conflate with cp failure.
        exists_ok, _, _ = exec_in_container(docker_name, ["test", "-e", cpath])
        if not exists_ok:
            details.append(f"preserve: {cpath} not present in container (empty snapshot)")
            snapshots[idx] = (cpath, snap_dir)
            continue

        ok, msg = pull_file_from_container(docker_name, cpath, snap_dir)
        if not ok:
            return OpResult(
                success=False,
                message=(
                    f"Preserve aborted — cp-out failed for mount_specs[{idx}] "
                    f"at {cpath}: {msg}"
                ),
                error=OpError.VALIDATION_FAILED,
                details=details,
            ), {}
        snapshots[idx] = (cpath, snap_dir)
        details.append(f"preserved: {cpath} -> {snap_dir}")

    return OpResult(
        success=True,
        message=f"Preserved {len(snapshots)} folder(s)",
        details=details,
    ), snapshots


def _restore_detached_folders(
    docker_name: str,
    snapshots: dict[int, tuple[str, Path]],
) -> list[str]:
    """Push preserved snapshots back into the recreated container.

    Runs AFTER ``_detached_init`` has mkdir'd each folder-seed path, so the
    destination directories exist and ``docker cp src/. cname:dst`` merges the
    snapshot contents in without nesting.

    Non-fatal: each cp-back failure is logged as a warning detail, but the
    outer update continues. Folders that fail to restore are left empty
    (mkdir'd by ``_detached_init``); the user can re-push manually.

    Args:
        docker_name: Recreated container name (running).
        snapshots: Output of ``_preserve_detached_folders`` — spec_idx →
            (container_path, host_snapshot_dir). Empty snapshot dirs (for
            specs whose source didn't exist on preserve) are skipped with a note.

    Returns:
        List of per-spec outcome notes for aggregation into the caller's
        OpResult.details.
    """
    if not snapshots:
        return []

    running_ok, running_msg = ensure_container_running(docker_name)
    if not running_ok:
        return [
            f"restore skipped — container not running: {running_msg} "
            f"({len(snapshots)} snapshot(s) left on disk for inspection)"
        ]

    notes: list[str] = []
    for idx, (cpath, snap_dir) in snapshots.items():
        if not snap_dir.exists():
            notes.append(
                f"restore: mount_specs[{idx}] had empty snapshot for {cpath} (no-op)"
            )
            continue

        ok, msg = push_directory_contents_to_container(
            docker_name, snap_dir, cpath,
        )
        if ok:
            notes.append(f"restored: {snap_dir} -> {cpath}")
        else:
            # Non-fatal: warn loudly but don't halt. The folder exists (mkdir'd
            # by _detached_init), just empty. User can re-push.
            msg_line = (
                f"restore FAILED (non-fatal) for mount_specs[{idx}] "
                f"at {cpath}: {msg}"
            )
            logger.warning(msg_line)
            notes.append(msg_line)
    return notes


def _cleanup_staging(staging_root: Path | None) -> None:
    """Remove the preserve staging directory. Swallow errors — cleanup must
    never mask a real operation failure.
    """
    if staging_root is None:
        return
    try:
        shutil.rmtree(staging_root, ignore_errors=True)
    except Exception:
        logger.debug("Failed to clean staging dir %s", staging_root, exc_info=True)


def reconcile_extensions(
    container_name: str,
    config: ScopeDockerConfig,
) -> OpResult:
    """Reconcile extension state after container start.

    Compares desired state (config.extensions) against actual state
    (binary present in container) and takes corrective action.

    State matrix:
        deploy    + missing → deploy_runtime() → installed
        deploy    + present → installed (already done)
        installed + missing → deploy_runtime() → installed (recreate recovery)
        installed + present → no-op
        remove    + any     → no-op (deferred to Phase 5)
        ""        + any     → no-op (not extension-managed)

    Non-fatal: individual extension failure doesn't block others.
    Caller is responsible for saving config after reconciliation.

    Args:
        container_name: Running Docker container name
        config: ScopeDockerConfig with extensions to reconcile (mutated in-place)

    Returns:
        OpResult with per-extension details
    """
    if not config.extensions:
        return OpResult(success=True, message="No extensions to reconcile")

    from ..container_ext import get_installer, DeployMethod

    details: list[str] = []

    for ext in config.extensions:
        # Skip non-managed and removal-pending entries
        if ext.state not in ("deploy", "installed"):
            continue

        installer = get_installer(ext.installer_class)
        if installer is None:
            details.append(f"{ext.name}: unknown installer '{ext.installer_class}', skipped")
            continue

        # Check if binary is present
        try:
            verify_result = installer.verify(container_name)
            binary_present = verify_result.success
        except Exception as e:
            details.append(f"{ext.name}: verify failed ({e}), skipped")
            continue

        if binary_present:
            # Binary present — ensure state is 'installed'
            if ext.state != "installed":
                ext.state = "installed"
                details.append(f"{ext.name}: present, state → installed")
            else:
                details.append(f"{ext.name}: present, no action")
            continue

        # Binary missing — need to deploy
        action = "deploy" if ext.state == "deploy" else "re-deploy (recreate recovery)"
        try:
            deploy_result = installer.deploy_runtime(
                container_name, method=DeployMethod.FULL,
            )
        except Exception as e:
            details.append(f"{ext.name}: {action} failed ({e})")
            continue

        if deploy_result.success:
            ext.state = "installed"
            version_info = f" v{deploy_result.version}" if deploy_result.version else ""
            details.append(f"{ext.name}: {action} succeeded{version_info}")
        else:
            details.append(f"{ext.name}: {action} failed — {deploy_result.message}")

    return OpResult(
        success=True,
        message=f"Reconciled {len(details)} extension(s)",
        details=details,
    )


def _compute_resource_names(host_project_root: Path, scope_name: str) -> tuple[str, str]:
    """Compute Docker resource name pair.

    Returns:
        (docker_name, image_name)

    Note: Task 1.7 of ``unify-l4-reclaim-isolation-term`` retired the
    ``{docker_name}-claude-auth`` volume name — the auth volume now flows
    through the unified extension-synth pipeline as a ``vol_*`` name.
    """
    docker_name = build_docker_name(host_project_root, scope_name)
    image_name = f"{sanitize_volume_name(docker_name)}:latest"
    return docker_name, image_name


def preflight_create(
    host_project_root: Path,
    config: ScopeDockerConfig,
) -> OpResult:
    """Validate preconditions for container creation.

    Checks:
      1. Project not in ISD install directory
      2. Hierarchy computes without validation errors
      3. Config validates
      4. Docker daemon is running

    Args:
        host_project_root: Project root directory
        config: ScopeDockerConfig to validate

    Returns:
        OpResult with error or success (no warnings for create)
    """
    # Guard: Prevent creating container in IgnoreScope's own directory
    isd_install_dir = Path(__file__).parent.parent.resolve()
    try:
        if host_project_root.resolve().is_relative_to(isd_install_dir):
            return OpResult(
                success=False,
                message=(
                    "Cannot create container in IgnoreScope install directory.\n"
                    "Use --project to specify your target project path."
                ),
                error=OpError.PROJECT_IN_INSTALL_DIR,
            )
    except ValueError:
        pass  # Not relative, which is fine

    # Lazy import to avoid circular: core/hierarchy -> docker/__init__ -> here -> core/hierarchy
    from ..core.hierarchy import compute_container_hierarchy

    # Compute hierarchy (includes validation)
    hierarchy = compute_container_hierarchy(
        container_root=config.container_root,
        mount_specs=config.mount_specs,
        pushed_files=config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=config.host_container_root,
        siblings=config.siblings or None,
        extensions=config.extensions or None,
    )

    if hierarchy.validation_errors:
        return OpResult(
            success=False,
            message="Configuration errors",
            error=OpError.VALIDATION_FAILED,
            details=list(hierarchy.validation_errors),
        )

    # Run LocalMountConfig validation (mount/mask ancestor checks)
    errors = config.validate()
    if errors:
        return OpResult(
            success=False,
            message="Configuration errors",
            error=OpError.VALIDATION_FAILED,
            details=errors,
        )

    # Check Docker
    docker_ok, docker_msg = is_docker_running()
    if not docker_ok:
        return OpResult(
            success=False,
            message=f"Docker not available: {docker_msg}",
            error=OpError.DOCKER_NOT_RUNNING,
        )

    return OpResult(success=True, message="Ready to create container")


def execute_create(
    host_project_root: Path,
    config: ScopeDockerConfig,
) -> OpResult:
    """Create Docker container from configuration.

    Phases 1-6 orchestration:
    validate -> generate compose -> build image -> create container -> save config

    Args:
        host_project_root: Project root directory
        config: ScopeDockerConfig with mount_specs and pushed_files

    Returns:
        OpResult with success/failure
    """
    # Run preflight first
    preflight = preflight_create(host_project_root, config)
    if not preflight.success:
        return preflight

    # Lazy import to avoid circular: core/hierarchy -> docker/__init__ -> here -> core/hierarchy
    from ..core.hierarchy import compute_container_hierarchy

    # Compute hierarchy (already validated in preflight, recompute for data)
    hierarchy = compute_container_hierarchy(
        container_root=config.container_root,
        mount_specs=config.mount_specs,
        pushed_files=config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=config.host_container_root,
        siblings=config.siblings or None,
        extensions=config.extensions or None,
    )

    # Scope name for config dirs; docker name for Docker resources
    scope_name = config.scope_name
    if not scope_name:
        return OpResult(success=False, message="config.scope_name must be set", error=OpError.VALIDATION_FAILED)
    docker_name, image_name = _compute_resource_names(host_project_root, scope_name)

    # Generate docker-compose.yml
    try:
        compose_content = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=host_project_root,
            docker_container_name=docker_name,
            docker_image_name=image_name,
            container_root=config.container_root,
            project_name=host_project_root.name,
            volume_entries=hierarchy.volume_entries,
            volume_names=hierarchy.volume_names,
            ports=config.ports if config.ports else None,
        )
    except Exception as e:
        return OpResult(success=False, message=f"Failed to generate docker-compose.yml: {e}")

    # Create output directory (uses scope_name for config dir path)
    output_dir = get_container_dir(host_project_root, scope_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate and write Dockerfile
    dockerfile_content = generate_dockerfile(
        project_name=host_project_root.name,
        container_root=config.container_root,
    )
    dockerfile = output_dir / "Dockerfile"
    try:
        dockerfile.write_text(dockerfile_content, encoding='utf-8')
    except OSError as e:
        return OpResult(success=False, message=f"Failed to write {dockerfile}: {e}")

    # Write docker-compose.yml
    compose_file = output_dir / "docker-compose.yml"
    try:
        compose_file.write_text(compose_content, encoding='utf-8')
    except OSError as e:
        return OpResult(success=False, message=f"Failed to write {compose_file}: {e}")

    # Build image
    try:
        success, msg = build_image(output_dir, image_name)
        if not success:
            return OpResult(success=False, message=f"Failed to build image: {msg}")
    except Exception as e:
        return OpResult(success=False, message=f"Build error: {e}")

    # Create container
    try:
        success, msg, created_container = create_container_compose(
            output_dir, expected_container_name=docker_name,
        )
        if not success:
            return OpResult(success=False, message=f"Failed to create container: {msg}")
    except Exception as e:
        return OpResult(success=False, message=f"Container creation error: {e}")

    # Detached init: deliver content for any mount_spec with delivery="detached"
    # via docker cp. Bind-only scopes skip this entirely.
    detached_details: list[str] = []
    if any(ms.delivery == "detached" for ms in config.mount_specs):
        init_result = _detached_init(docker_name, config)
        if not init_result.success:
            return init_result
        detached_details = init_result.details or []

    # Pre-create directories for pushed files in mask volumes
    if hierarchy.revealed_parents:
        running_ok, running_msg = ensure_container_running(docker_name)
        if running_ok:
            dir_success, dir_msg = ensure_container_directories(
                docker_name, list(hierarchy.revealed_parents),
            )
            # Non-fatal: dirs are eagerly created here; push ops mkdir on demand as fallback

    # Replay pushed_files into the fresh container FS. Mode-agnostic — runs on
    # every create when pushed_files is non-empty. Uses the canonical
    # single-file push path. Per-file failures surface in details; not fatal.
    replay_details: list[str] = []
    if config.pushed_files:
        running_ok, _ = ensure_container_running(docker_name)
        if running_ok:
            replay_results = execute_push_batch(
                list(config.pushed_files),
                docker_name,
                config.container_root,
                config.host_container_root,
            )
            for host_path, res in replay_results.items():
                if not res.success:
                    replay_details.append(
                        f"pushed_files replay failed: {host_path} — {res.message}"
                    )

    # Reconcile extensions (non-fatal — deploy/verify after container is up)
    reconcile_result = None
    if config.extensions:
        running_ok, _ = ensure_container_running(docker_name)
        if running_ok:
            reconcile_result = reconcile_extensions(docker_name, config)

    # Save config
    config.host_project_root = host_project_root
    try:
        save_config(config)
    except Exception as e:
        return OpResult(success=False, message=f"Failed to save config: {e}")

    result_msg = f"Container created: {docker_name}\nConfig saved to {output_dir / CONFIG_FILENAME}"
    if detached_details:
        result_msg += f"\n{len(detached_details)} detached init note(s)"
    if replay_details:
        result_msg += f"\n{len(replay_details)} pushed_files replay note(s)"
    if reconcile_result and reconcile_result.details:
        result_msg += f"\nReconciled {len(reconcile_result.details)} extension(s)"

    return OpResult(
        success=True,
        message=result_msg,
        details=detached_details + replay_details,
    )


def preflight_update(
    host_project_root: Path,
    config: ScopeDockerConfig,
) -> OpResult:
    """Validate preconditions for container update.

    Checks:
      1. Container exists (error if not — use Create instead)
      2. All preflight_create checks pass

    Args:
        host_project_root: Project root directory
        config: ScopeDockerConfig to validate

    Returns:
        OpResult with error or success
    """
    # Must have an existing container to update
    scope_name = config.scope_name
    if not scope_name:
        return OpResult(success=False, message="config.scope_name must be set", error=OpError.VALIDATION_FAILED)
    docker_name = build_docker_name(host_project_root, scope_name)
    if not container_exists(docker_name):
        return OpResult(
            success=False,
            message=f"Container '{docker_name}' not found. Use Create instead.",
            error=OpError.CONTAINER_NOT_FOUND,
        )

    return preflight_create(host_project_root, config)


def execute_update(
    host_project_root: Path,
    config: ScopeDockerConfig,
) -> OpResult:
    """Update existing container, retaining configured volumes and pruning orphans.

    12-phase orchestration:
      1. Load old config → compute old hierarchy → old volume names
      2. Preflight new config
      3. Compute new hierarchy → new volume names
      4. orphan_volumes = old_masks - new_masks
      5. docker compose down (remove_volumes=False, remove_images=False)
      6. Generate new compose + Dockerfile → write to disk
      7. Build image
      8. docker compose up --no-start (reuses existing named volumes)
      9. Prune orphan volumes (non-fatal)
     10. Pre-create dirs in mask volumes
     11. Reconcile extensions (non-fatal)
     12. Save config

    Args:
        host_project_root: Project root directory
        config: New ScopeDockerConfig to apply

    Returns:
        OpResult with success/failure
    """
    # Lazy import to avoid circular
    from ..core.hierarchy import compute_container_hierarchy

    # ── Phase 1: Load old config → old hierarchy → old mask names ──
    scope_name = config.scope_name
    if not scope_name:
        return OpResult(success=False, message="config.scope_name must be set", error=OpError.VALIDATION_FAILED)

    try:
        old_config = load_config(host_project_root, scope_name)
    except Exception as e:
        return OpResult(success=False, message=f"Failed to load existing config: {e}")

    old_hierarchy = compute_container_hierarchy(
        container_root=old_config.container_root,
        mount_specs=old_config.mount_specs,
        pushed_files=old_config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=old_config.host_container_root,
        siblings=old_config.siblings or None,
        extensions=old_config.extensions or None,
    )
    old_mask_names = set(old_hierarchy.mask_volume_names)

    # ── Phase 2: Preflight new config ──
    preflight = preflight_update(host_project_root, config)
    if not preflight.success:
        return preflight

    # ── Phase 3: Compute new hierarchy → new mask names ──
    new_hierarchy = compute_container_hierarchy(
        container_root=config.container_root,
        mount_specs=config.mount_specs,
        pushed_files=config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=config.host_container_root,
        siblings=config.siblings or None,
        extensions=config.extensions or None,
    )
    new_mask_names = set(new_hierarchy.mask_volume_names)

    # ── Phase 4: Detect orphan volumes (masks only) ──
    # Volume-tier entries (`vol_*`, the unified L_volume tier covering both
    # user-authored `delivery="volume"` specs and extension-synthesized
    # isolation paths) are NEVER orphaned here: they are designed to persist
    # across ordinary recreate so extension auth state and Permanent Folder
    # contents survive updates. Destruction of a `vol_*` volume requires an
    # explicit `docker compose down -v` path, not an update-time diff.
    orphan_volumes = old_mask_names - new_mask_names

    docker_name, image_name = _compute_resource_names(host_project_root, scope_name)
    output_dir = get_container_dir(host_project_root, scope_name)

    # ── Phase 4b: Preserve detached folders (before compose down) ──
    # For every spec with preserve_on_update=True, snapshot its current
    # container contents to a host tmp staging dir so we can restore them
    # into the freshly-mkdir'd folder after recreate. cp-out failure aborts
    # BEFORE compose down — we never take the container down without a safe
    # snapshot (fail-safe).
    has_preserve = any(ms.preserve_on_update for ms in config.mount_specs)
    staging_root: Path | None = None
    preserve_snapshots: dict[int, tuple[str, Path]] = {}
    preserve_details: list[str] = []
    if has_preserve:
        try:
            staging_root = Path(tempfile.mkdtemp(prefix=_PRESERVE_STAGING_PREFIX))
        except OSError as e:
            return OpResult(
                success=False,
                message=f"Preserve aborted — cannot create staging dir: {e}",
                error=OpError.VALIDATION_FAILED,
            )
        preserve_result, preserve_snapshots = _preserve_detached_folders(
            docker_name, config, staging_root,
        )
        if not preserve_result.success:
            _cleanup_staging(staging_root)
            return preserve_result
        preserve_details = preserve_result.details or []

    try:
        # ── Phase 5: docker compose down (retain volumes) ──
        try:
            success, msg, _ = remove_container_compose(
                output_dir, remove_volumes=False, remove_images=False,
            )
            if not success:
                return OpResult(success=False, message=f"Failed to stop container: {msg}")
        except Exception as e:
            return OpResult(success=False, message=f"Compose down error: {e}")

        # ── Phase 6: Generate new compose + Dockerfile → write to disk ──
        try:
            compose_content = generate_compose_with_masks(
                ordered_volumes=new_hierarchy.ordered_volumes,
                mask_volume_names=new_hierarchy.mask_volume_names,
                host_project_root=host_project_root,
                docker_container_name=docker_name,
                docker_image_name=image_name,
                container_root=config.container_root,
                project_name=host_project_root.name,
                volume_entries=new_hierarchy.volume_entries,
                volume_names=new_hierarchy.volume_names,
                ports=config.ports if config.ports else None,
            )
        except Exception as e:
            return OpResult(success=False, message=f"Failed to generate docker-compose.yml: {e}")

        output_dir.mkdir(parents=True, exist_ok=True)

        dockerfile_content = generate_dockerfile(
            project_name=host_project_root.name,
            container_root=config.container_root,
        )
        try:
            (output_dir / "Dockerfile").write_text(dockerfile_content, encoding='utf-8')
        except OSError as e:
            return OpResult(success=False, message=f"Failed to write Dockerfile: {e}")

        try:
            (output_dir / "docker-compose.yml").write_text(compose_content, encoding='utf-8')
        except OSError as e:
            return OpResult(success=False, message=f"Failed to write docker-compose.yml: {e}")

        # ── Phase 7: Build image ──
        try:
            success, msg = build_image(output_dir, image_name)
            if not success:
                return OpResult(success=False, message=f"Failed to build image: {msg}")
        except Exception as e:
            return OpResult(success=False, message=f"Build error: {e}")

        # ── Phase 8: docker compose up --no-start (reuses existing named volumes) ──
        try:
            success, msg, created_container = create_container_compose(
                output_dir, expected_container_name=docker_name,
            )
            if not success:
                return OpResult(success=False, message=f"Failed to create container: {msg}")
        except Exception as e:
            return OpResult(success=False, message=f"Container creation error: {e}")

        # ── Phase 8a: Detached init (docker cp + mask rm) for any detached specs ──
        detached_details: list[str] = []
        if any(ms.delivery == "detached" for ms in config.mount_specs):
            init_result = _detached_init(docker_name, config)
            if not init_result.success:
                return init_result
            detached_details = init_result.details or []

        # ── Phase 8b: Restore preserved folders (non-fatal per-spec) ──
        # Runs after _detached_init has mkdir'd the destination folders.
        restore_details: list[str] = []
        if preserve_snapshots:
            restore_details = _restore_detached_folders(docker_name, preserve_snapshots)

        # ── Phase 9: Prune orphan volumes (non-fatal) ──
        prune_details = []
        for orphan in sorted(orphan_volumes):
            if volume_exists(orphan):
                ok, prune_msg = remove_volume(orphan)
                if ok:
                    prune_details.append(f"Pruned orphan volume: {orphan}")
                else:
                    prune_details.append(f"Failed to prune volume '{orphan}': {prune_msg}")

        # ── Phase 10: Pre-create dirs in mask volumes ──
        if new_hierarchy.revealed_parents:
            running_ok, running_msg = ensure_container_running(docker_name)
            if running_ok:
                ensure_container_directories(
                    docker_name, list(new_hierarchy.revealed_parents),
                )
                # Non-fatal: dirs are eagerly created here; push ops mkdir on demand as fallback

        # ── Phase 10a: Replay pushed_files into recreated container ──
        # Mode-agnostic — runs on every update when pushed_files is non-empty.
        replay_details: list[str] = []
        if config.pushed_files:
            running_ok, _ = ensure_container_running(docker_name)
            if running_ok:
                replay_results = execute_push_batch(
                    list(config.pushed_files),
                    docker_name,
                    config.container_root,
                    config.host_container_root,
                )
                for host_path, res in replay_results.items():
                    if not res.success:
                        replay_details.append(
                            f"pushed_files replay failed: {host_path} — {res.message}"
                        )

        # ── Phase 11: Reconcile extensions (non-fatal) ──
        reconcile_result = None
        if config.extensions:
            running_ok, _ = ensure_container_running(docker_name)
            if running_ok:
                reconcile_result = reconcile_extensions(docker_name, config)

        # ── Phase 12: Save config ──
        config.host_project_root = host_project_root
        try:
            save_config(config)
        except Exception as e:
            return OpResult(success=False, message=f"Failed to save config: {e}")

        result_msg = f"Container updated: {docker_name}"
        if orphan_volumes:
            result_msg += f"\nPruned {len(orphan_volumes)} orphan volume(s)"
        if detached_details:
            result_msg += f"\n{len(detached_details)} detached init note(s)"
        if preserve_snapshots:
            result_msg += f"\nPreserved {len(preserve_snapshots)} folder(s)"
        if replay_details:
            result_msg += f"\n{len(replay_details)} pushed_files replay note(s)"
        if reconcile_result and reconcile_result.details:
            result_msg += f"\nReconciled {len(reconcile_result.details)} extension(s)"
        return OpResult(
            success=True,
            message=result_msg,
            details=(
                prune_details
                + preserve_details
                + detached_details
                + restore_details
                + replay_details
                + (reconcile_result.details if reconcile_result else [])
            ),
        )
    finally:
        _cleanup_staging(staging_root)


def preflight_remove_container(
    host_project_root: Path,
    scope_name: str,
) -> OpResult:
    """Validate preconditions for container removal.

    Checks:
      1. Container exists

    Args:
        host_project_root: Project root directory
        scope_name: Scope name (used to derive Docker container name)

    Returns:
        OpResult with error or success
    """
    if not scope_name:
        return OpResult(success=False, message="scope_name must be set", error=OpError.VALIDATION_FAILED)
    docker_name = build_docker_name(host_project_root, scope_name)

    if not container_exists(docker_name):
        return OpResult(
            success=False,
            message=f"Container not found: {docker_name}",
            error=OpError.CONTAINER_NOT_FOUND,
        )

    return OpResult(success=True, message=f"Container '{docker_name}' exists")


def execute_remove_container(
    host_project_root: Path,
    scope_name: str,
    remove_images: bool = False,
    remove_volumes: bool = True,
) -> OpResult:
    """Remove container and optionally volumes via docker compose down.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name (used to derive Docker container name and config dir)
        remove_images: If True, also remove Docker images
        remove_volumes: If True, also remove all volumes (default True)

    Returns:
        OpResult with success/failure
    """
    if not scope_name:
        return OpResult(success=False, message="scope_name must be set", error=OpError.VALIDATION_FAILED)
    docker_name = build_docker_name(host_project_root, scope_name)

    try:
        output_dir = get_container_dir(host_project_root, scope_name)
        success, msg, removed_vols = remove_container_compose(
            output_dir,
            remove_volumes=remove_volumes,
            remove_images=remove_images,
        )
        if not success:
            return OpResult(success=False, message=f"Failed to remove container: {msg}")
    except Exception as e:
        return OpResult(success=False, message=f"Removal error: {e}")

    result_msg = f"Container removed: {docker_name}"
    if remove_images:
        result_msg += " (including images)"
    return OpResult(success=True, message=result_msg)
