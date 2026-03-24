"""CLI command handlers for IgnoreScope.

Implements:
- cmd_create: Setup container with mounts, masked, revealed
- cmd_push: Push files to container
- cmd_pull: Pull files from container
- cmd_remove: Remove container and volumes
"""

from pathlib import Path
from typing import Optional

from ..core.config import ScopeDockerConfig, load_config, save_config, list_containers
from ..docker import (
    resolve_file_subset,
    preflight_push_batch,
    execute_push_batch,
    preflight_pull_batch,
    execute_pull_batch,
    execute_create,
    preflight_remove_container,
    execute_remove_container,
)
from ..container_ext.git_extension import GitInstaller
from ..container_ext.p4_mcp_extension import P4McpInstaller
from ..docker.names import build_docker_name
from ..docker.container_ops import (
    get_container_info,
    container_exists,
    ensure_container_running,
    push_file_to_container,
    ensure_container_directories,
)


def _format_batch_results(
    results: dict, host_project_root: Path,
) -> tuple[list[str], list[str]]:
    """Format per-file results into display lines and error messages.

    Args:
        results: Dict mapping Path -> OpResult.
        host_project_root: Project root for relative path display.

    Returns:
        (result_lines, failed_messages)
    """
    result_lines = []
    failed = []
    for path in sorted(results.keys()):
        r = results[path]
        rel = path.relative_to(host_project_root)
        status = "[OK]" if r.success else "[ERROR]"
        result_lines.append(f"{status} {rel}")
        if not r.success:
            failed.append(r.message)
    return result_lines, failed


def _check_batch_preflight(
    batch, host_project_root: Path, force: bool, op_name: str,
) -> tuple[bool, str | None, list[Path]]:
    """Check batch preflight results, format errors/warnings, assemble paths.

    Args:
        batch: BatchFileResult from preflight.
        host_project_root: Project root for relative path display.
        force: If True, include warned paths in execution list.
        op_name: Operation name for messages (e.g. "Push", "Pull").

    Returns:
        (should_continue, error_msg_or_None, paths_to_execute)
    """
    # Report errors (blocking)
    error_lines = []
    if batch.errors:
        error_lines = [
            f"  [BLOCKED] {p.relative_to(host_project_root)}: {r.message}"
            for p, r in batch.errors.items()
        ]
        if not batch.clean and not batch.warnings:
            return False, "All files blocked:\n" + "\n".join(error_lines), []

    # Report warnings
    if batch.warnings and not force:
        warn_lines = [
            f"  [WARN] {p.relative_to(host_project_root)}: {r.message}"
            for p, r in batch.warnings.items()
        ]
        msg = "\n".join(warn_lines)
        if error_lines:
            msg = "\n".join(error_lines) + "\n" + msg
        return False, f"{op_name} requires confirmation:\n{msg}\nUse --force to override warnings.", []

    # Combine clean + warned (if forced) paths
    paths_to_execute = list(batch.clean)
    if force:
        paths_to_execute.extend(batch.warnings.keys())
    paths_to_execute.sort()

    if not paths_to_execute:
        return False, f"No files eligible for {op_name.lower()}", []

    return True, None, paths_to_execute


def cmd_create(
    host_project_root: Path,
    config: ScopeDockerConfig,
) -> tuple[bool, str]:
    """Create Docker container with configured mounts, masks, and reveals.

    Thin CLI wrapper around CORE execute_create().

    Args:
        host_project_root: Project root directory
        config: ScopeDockerConfig with mounts, masked, revealed

    Returns:
        Tuple of (success, message)
    """
    result = execute_create(host_project_root, config)
    if not result.success and result.details:
        detail_str = "\n".join(f"  * {e}" for e in result.details)
        return False, f"{result.message}:\n{detail_str}"
    return result.success, result.message


def cmd_push(
    host_project_root: Path,
    scope_name: str,
    specific_files: Optional[list[str]] = None,
    force: bool = False,
) -> tuple[bool, str]:
    """Push files to container using CORE preflight/execute pattern.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name
        specific_files: Optional list of relative paths to push (push all if None)
        force: If True, skip warnings (proceed despite confirmable issues)

    Returns:
        Tuple of (success, message)
    """
    # Load config
    try:
        config = load_config(host_project_root, scope_name)
    except Exception as e:
        return False, f"Failed to load config: {e}"

    if not config.pushed_files:
        return True, "No pushed files configured"

    # Determine which files to push
    files_to_push = resolve_file_subset(config.pushed_files, host_project_root, specific_files)
    if not files_to_push:
        return False, "No matching files to push"

    docker_name = build_docker_name(host_project_root, config.scope_name)
    container_root = config.container_root
    host_container_root = config.host_container_root or host_project_root.parent

    # Preflight all files
    batch = preflight_push_batch(
        sorted(files_to_push), docker_name,
        container_root, host_container_root, config.pushed_files,
    )

    should_continue, err_msg, paths_to_execute = _check_batch_preflight(
        batch, host_project_root, force, "Push",
    )
    if not should_continue:
        return False, err_msg

    # Execute
    results = execute_push_batch(
        paths_to_execute, docker_name,
        container_root, host_container_root,
    )

    # Update tracking for successful pushes
    any_success = False
    for path, result in results.items():
        if result.success:
            config.pushed_files.add(path)
            any_success = True

    if any_success:
        save_config(config)

    # Format results
    result_lines, failed = _format_batch_results(results, host_project_root)
    result_msg = "\n".join(result_lines)
    if failed:
        error_msg = "\n".join(f"  Error: {e}" for e in failed)
        return False, f"Push completed with errors:\n{result_msg}\n\n{error_msg}"
    return True, f"Files pushed successfully:\n{result_msg}"


def cmd_pull(
    host_project_root: Path,
    scope_name: str,
    specific_files: Optional[list[str]] = None,
    force: bool = False,
) -> tuple[bool, str]:
    """Pull files from container using CORE preflight/execute pattern.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name
        specific_files: Optional list of relative paths to pull (pull all if None)
        force: If True, skip warnings (overwrite without confirmation)

    Returns:
        Tuple of (success, message)
    """
    # Load config
    try:
        config = load_config(host_project_root, scope_name)
    except Exception as e:
        return False, f"Failed to load config: {e}"

    if not config.pushed_files:
        return True, "No pushed files configured"

    # Determine which files to pull
    files_to_pull = resolve_file_subset(config.pushed_files, host_project_root, specific_files)
    if not files_to_pull:
        return False, "No matching files to pull"

    docker_name = build_docker_name(host_project_root, config.scope_name)
    container_root = config.container_root
    host_container_root = config.host_container_root or host_project_root.parent

    # Preflight all files
    batch = preflight_pull_batch(
        sorted(files_to_pull), docker_name,
        container_root, host_container_root,
        host_project_root, config.dev_mode,
    )

    should_continue, err_msg, paths_to_execute = _check_batch_preflight(
        batch, host_project_root, force, "Pull",
    )
    if not should_continue:
        return False, err_msg

    # Execute
    mode_msg = "Safe mode (./Pulled/)" if config.dev_mode else "Production mode (overwriting originals)"
    results = execute_pull_batch(
        paths_to_execute, docker_name,
        container_root, host_container_root,
        host_project_root, config.dev_mode,
    )

    # Format results
    result_lines, failed = _format_batch_results(results, host_project_root)
    result_msg = "\n".join(result_lines)
    if failed:
        error_msg = "\n".join(f"  Error: {e}" for e in failed)
        return False, f"Pull completed with errors:\n{result_msg}\n\n{error_msg}"
    return True, f"Files pulled successfully ({mode_msg}):\n{result_msg}"


def cmd_install_git(
    host_project_root: Path,
    scope_name: str,
    distro: str = "auto",
    configure: bool = False,
    name: str = "",
    email: str = "",
    project_dir: str = "",
    scope_dir: str = "",
) -> tuple[bool, str]:
    """Install Git into a running container.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name
        distro: "debian", "alpine", or "auto" for detection
        configure: If True, also configure git identity
        name: Git user.name (required if configure=True)
        email: Git user.email (required if configure=True)
        project_dir: Container project root — if provided, deploy .gitignore
        scope_dir: Container scope dir — if provided with project_dir, deploy config

    Returns:
        Tuple of (success, message)
    """
    docker_name = build_docker_name(host_project_root, scope_name)
    installer = GitInstaller()
    result = installer.deploy(docker_name, distro=distro)
    if not result.success:
        return False, result.message
    msg = f"Git installed (v{result.version})" if result.version else result.message
    if configure and name and email:
        ok, cfg_msg = installer.configure_identity(docker_name, name, email)
        msg += f"\nConfigured: {name} <{email}>" if ok else f"\nWarning: {cfg_msg}"

    # Optional config deploy
    if project_dir:
        context = {"scope_name": scope_name}
        config_results = installer.deploy_config(
            docker_name, context, project_dir, scope_dir or project_dir,
        )
        for r in config_results:
            if r.success:
                msg += f"\n{r.message}"
            else:
                msg += f"\nConfig warning: {r.message}"

    return True, msg


def cmd_install_p4_mcp(
    host_project_root: Path,
    scope_name: str,
    devenv_mount: str = "/devenv",
    project_dir: str = "",
    scope_dir: str = "",
    p4port: str = "",
    p4user: str = "",
    p4client: str = "",
) -> tuple[bool, str]:
    """Install P4 MCP Server into a running container.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name
        devenv_mount: Container path where devenv is mounted
        project_dir: Container project root — if provided, deploy P4 configs
        scope_dir: Container scope dir — if provided with project_dir, deploy config
        p4port: Perforce P4PORT value (required for config deploy)
        p4user: Perforce P4USER value (required for config deploy)
        p4client: Perforce P4CLIENT workspace (required for config deploy)

    Returns:
        Tuple of (success, message)
    """
    docker_name = build_docker_name(host_project_root, scope_name)
    installer = P4McpInstaller(devenv_mount=devenv_mount)
    result = installer.deploy(docker_name)
    if not result.success:
        return False, result.message
    msg = f"P4 MCP Server installed (v{result.version})" if result.version else result.message

    # Optional config deploy
    if project_dir and p4port and p4user and p4client:
        context = {"p4port": p4port, "p4user": p4user, "p4client": p4client}
        config_results = installer.deploy_config(
            docker_name, context, project_dir, scope_dir or project_dir,
        )
        for r in config_results:
            if r.success:
                msg += f"\n{r.message}"
            else:
                msg += f"\nConfig warning: {r.message}"

    return True, msg


def cmd_remove(
    host_project_root: Path,
    scope_name: str,
    confirm: bool = False,
    remove_images: bool = False,
) -> tuple[bool, str]:
    """Remove container and volumes.

    Thin CLI wrapper around CORE preflight_remove_container/execute_remove_container.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name
        confirm: If True, skip confirmation prompt
        remove_images: If True, also remove Docker images

    Returns:
        Tuple of (success, message)
    """
    # Preflight
    preflight = preflight_remove_container(host_project_root, scope_name)
    if not preflight.success:
        return False, preflight.message

    # CLI-specific confirmation prompt
    docker_name = build_docker_name(host_project_root, scope_name)
    if not confirm:
        print(f"\nWill remove:")
        print(f"  * Container: {docker_name}")
        print(f"  * Volumes: Associated volumes")
        response = input("\nContinue? (y/N): ").strip().lower()
        if response != 'y':
            return True, "Cancelled"

    # Execute
    result = execute_remove_container(host_project_root, scope_name, remove_images)
    return result.success, result.message


def cmd_list(
    host_project_root: Path,
) -> tuple[bool, str]:
    """List all containers for a project with their Docker status.

    Args:
        host_project_root: Project root directory

    Returns:
        Tuple of (success, formatted_output)
    """
    containers = list_containers(host_project_root)
    if not containers:
        return True, f"No containers configured for: {host_project_root}"

    lines = [f"Containers for: {host_project_root}"]
    for scope_name in containers:
        docker_name = build_docker_name(host_project_root, scope_name)
        info = get_container_info(docker_name)
        if info is None:
            status = "not created"
        elif info.get("running"):
            status = "running"
        else:
            status = info.get("status", "stopped")
        lines.append(f"  {scope_name:<20} [{status}]")

    return True, "\n".join(lines)


def cmd_status(
    host_project_root: Path,
    scope_name: str,
) -> tuple[bool, str]:
    """Show detailed status of a single container.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name

    Returns:
        Tuple of (success, formatted_output)
    """
    docker_name = build_docker_name(host_project_root, scope_name)
    info = get_container_info(docker_name)
    if info is None:
        return True, f"Container '{scope_name}' ({docker_name}): not created"

    lines = [
        f"Container: {scope_name} ({docker_name})",
        f"  Status:  {info.get('status', 'unknown')}",
        f"  Running: {info.get('running', False)}",
        f"  Image:   {info.get('image', 'unknown')}",
        f"  Created: {info.get('created', 'unknown')}",
        f"  ID:      {info.get('id', 'unknown')[:12]}",
    ]
    return True, "\n".join(lines)


def cmd_cp(
    host_project_root: Path,
    scope_name: str,
    source: str,
    dest: str = "",
) -> tuple[bool, str]:
    """Copy a file or directory from host to container via docker cp.

    Raw utility — no config loading, no tracking, no preflight batch.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name
        source: Host path to file or directory
        dest: Container destination path (optional — auto-resolves if omitted)

    Returns:
        Tuple of (success, message)
    """
    source_path = Path(source).resolve()
    if not source_path.exists():
        return False, f"Source not found: {source_path}"

    docker_name = build_docker_name(host_project_root, scope_name)

    # Auto-start if stopped
    ok, msg = ensure_container_running(docker_name)
    if not ok:
        return False, f"Container not available: {msg}"

    # Resolve destination
    if dest:
        container_path = dest
    else:
        # Default: place in container root with source name
        container_path = f"/{source_path.name}"

    # Ensure parent directory exists
    from pathlib import PurePosixPath
    parent_dir = str(PurePosixPath(container_path).parent)
    if parent_dir not in ('/', '.', ''):
        ensure_container_directories(docker_name, [parent_dir])

    # Transfer via docker cp
    ok, msg = push_file_to_container(docker_name, source_path, container_path)
    if ok:
        kind = "Directory" if source_path.is_dir() else "File"
        return True, f"{kind} copied: {source_path.name} → {container_path}"
    return False, msg
