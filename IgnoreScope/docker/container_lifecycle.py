"""CORE container lifecycle orchestrators.

IS:  Create/update/remove container orchestration as CORE functions.
     Phases 1→6 pipeline: preflight → hierarchy → compose → build → deploy → save.
     Both GUI and CLI consume these — neither owns the orchestration.

IS NOT: Subprocess calls (→ container_ops.py)
        File operations (→ file_ops.py)
        Compose generation (→ compose.py)

Uses OpResult for standardized returns.
"""

from __future__ import annotations

from pathlib import Path

from ..core.config import (
    CONFIG_FILENAME,
    ScopeDockerConfig,
    load_config,
    save_config,
    get_container_dir,
)
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
    container_exists,
    volume_exists,
    remove_volume,
)
from .compose import generate_compose_with_masks, generate_dockerfile
from .names import DockerNames, build_docker_name, sanitize_volume_name


def _compute_resource_names(host_project_root: Path, scope_name: str) -> tuple[str, str, str]:
    """Compute Docker resource name triple.

    Returns:
        (docker_name, image_name, volume_name)
    """
    docker_name = build_docker_name(host_project_root, scope_name)
    image_name = f"{sanitize_volume_name(docker_name)}:latest"
    volume_name = f"{docker_name}-claude-auth"
    return docker_name, image_name, volume_name


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
        mounts=config.mounts,
        masked=config.masked,
        revealed=config.revealed,
        pushed_files=config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=config.host_container_root,
        siblings=config.siblings or None,
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
        config: ScopeDockerConfig with mounts, masked, revealed

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
        mounts=config.mounts,
        masked=config.masked,
        revealed=config.revealed,
        pushed_files=config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=config.host_container_root,
        siblings=config.siblings or None,
    )

    # Scope name for config dirs; docker name for Docker resources
    scope_name = config.scope_name
    if not scope_name:
        return OpResult(success=False, message="config.scope_name must be set", error=OpError.VALIDATION_FAILED)
    docker_name, image_name, volume_name = _compute_resource_names(host_project_root, scope_name)

    # Generate docker-compose.yml
    try:
        compose_content = generate_compose_with_masks(
            ordered_volumes=hierarchy.ordered_volumes,
            mask_volume_names=hierarchy.mask_volume_names,
            host_project_root=host_project_root,
            docker_container_name=docker_name,
            docker_image_name=image_name,
            docker_volume_name=volume_name,
            container_root=config.container_root,
            project_name=host_project_root.name,
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

    # Pre-create directories for pushed files in mask volumes
    if hierarchy.revealed_parents:
        running_ok, running_msg = ensure_container_running(docker_name)
        if running_ok:
            dir_success, dir_msg = ensure_container_directories(
                docker_name, list(hierarchy.revealed_parents),
            )
            # Non-fatal: dirs are eagerly created here; push ops mkdir on demand as fallback

    # Save config
    config.host_project_root = host_project_root
    try:
        save_config(config)
    except Exception as e:
        return OpResult(success=False, message=f"Failed to save config: {e}")

    return OpResult(
        success=True,
        message=f"Container created: {docker_name}\nConfig saved to {output_dir / CONFIG_FILENAME}",
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

    11-phase orchestration:
      1. Load old config → compute old hierarchy → old mask_volume_names
      2. Preflight new config
      3. Compute new hierarchy → new mask_volume_names
      4. orphan_volumes = set(old_mask_names) - set(new_mask_names)
      5. docker compose down (remove_volumes=False, remove_images=False)
      6. Generate new compose + Dockerfile → write to disk
      7. Build image
      8. docker compose up --no-start (reuses existing named volumes)
      9. Prune orphan volumes (non-fatal)
     10. Pre-create dirs in mask volumes
     11. Save config

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
        mounts=old_config.mounts,
        masked=old_config.masked,
        revealed=old_config.revealed,
        pushed_files=old_config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=old_config.host_container_root,
        siblings=old_config.siblings or None,
    )
    old_mask_names = set(old_hierarchy.mask_volume_names)

    # ── Phase 2: Preflight new config ──
    preflight = preflight_update(host_project_root, config)
    if not preflight.success:
        return preflight

    # ── Phase 3: Compute new hierarchy → new mask names ──
    new_hierarchy = compute_container_hierarchy(
        container_root=config.container_root,
        mounts=config.mounts,
        masked=config.masked,
        revealed=config.revealed,
        pushed_files=config.pushed_files,
        host_project_root=host_project_root,
        host_container_root=config.host_container_root,
        siblings=config.siblings or None,
    )
    new_mask_names = set(new_hierarchy.mask_volume_names)

    # ── Phase 4: Detect orphan volumes ──
    orphan_volumes = old_mask_names - new_mask_names

    docker_name, image_name, volume_name = _compute_resource_names(host_project_root, scope_name)
    output_dir = get_container_dir(host_project_root, scope_name)

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
            docker_volume_name=volume_name,
            container_root=config.container_root,
            project_name=host_project_root.name,
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

    # ── Phase 11: Save config ──
    config.host_project_root = host_project_root
    try:
        save_config(config)
    except Exception as e:
        return OpResult(success=False, message=f"Failed to save config: {e}")

    result_msg = f"Container updated: {docker_name}"
    if orphan_volumes:
        result_msg += f"\nPruned {len(orphan_volumes)} orphan volume(s)"
    return OpResult(
        success=True,
        message=result_msg,
        details=prune_details,
    )


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
