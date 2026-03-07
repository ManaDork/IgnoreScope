"""File operation orchestrators — push/pull/remove flows.

IS:  Path resolution (resolve_container_path, resolve_file_subset, resolve_pull_output)
     Preflight validation (preflight_push, preflight_pull, preflight_remove)
     Execution orchestration (execute_push, execute_pull, execute_remove)
     Batch wrappers (preflight_*_batch, execute_*_batch)

IS NOT: Subprocess calls (→ container_ops.py)
        Container lifecycle (→ container_lifecycle.py)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..core.op_result import OpError, OpWarning, OpResult, BatchFileResult
from .file_filter_ops import FileFilter, passthrough


# =============================================================================
# Path Resolution
# =============================================================================

def resolve_container_path(
    host_path: Path,
    container_root: str,
    host_container_root: Path,
) -> str:
    """Compute container-absolute path from a host path.

    Consolidates the host_path -> container_path conversion that was
    previously duplicated inline in GUI and CLI. Uses the centralized
    container path formula from core/config.py (Rule 5).

    Args:
        host_path: Absolute host file/folder path
        container_root: Container root path (e.g., '/Projects')
        host_container_root: Host ancestor directory (relative_to base)

    Returns:
        Container-absolute POSIX path
    """
    # Lazy import: core/hierarchy -> docker/__init__ -> file_ops -> core/hierarchy
    from ..core.hierarchy import to_container_path
    return to_container_path(host_path, container_root, host_container_root)


def resolve_file_subset(
    pushed_files: set[Path],
    host_project_root: Path,
    specific_files: list[str] | None = None,
) -> set[Path]:
    """Filter pushed files to a specific subset if requested.

    Args:
        pushed_files: Full set of pushed file absolute paths
        host_project_root: Project root for resolving relative paths
        specific_files: Optional list of relative path strings to filter to

    Returns:
        Filtered set of absolute file paths
    """
    if not specific_files:
        return set(pushed_files)
    specific_paths = {host_project_root / f for f in specific_files}
    return {f for f in pushed_files if f in specific_paths}


def resolve_pull_output(
    host_project_root: Path,
    rel_path: Path,
    dev_mode: bool,
    timestamp: str | None = None,
) -> Path:
    """Compute pull destination path based on dev mode.

    In dev mode, files go to ``./Pulled/{timestamp}/{rel_path}`` (safe).
    In production mode, files overwrite at the original location.

    Args:
        host_project_root: Project root directory
        rel_path: Relative path within project (e.g., ``Path("src/config.json")``)
        dev_mode: If True, pull to ./Pulled/ safe directory
        timestamp: Optional timestamp string (defaults to current time ``%Y%m%d_%H%M%S``)

    Returns:
        Absolute destination path for the pulled file
    """
    if dev_mode:
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return host_project_root / "Pulled" / timestamp / rel_path
    return host_project_root / rel_path


# =============================================================================
# Preflight Validation Helpers
# =============================================================================

def _validate_path_under_root(host_path: Path, host_container_root: Path) -> OpResult | None:
    """Check that host_path is under host_container_root.

    Returns:
        OpResult with INVALID_LOCATION error, or None if valid.
    """
    try:
        host_path.relative_to(host_container_root)
    except ValueError:
        return OpResult(
            success=False,
            message=f"{host_path.name} is not under {host_container_root}",
            error=OpError.INVALID_LOCATION,
        )
    return None


def _validate_container_running(container_name: str) -> OpResult | None:
    """Check that the named container is running, starting it if stopped.

    Returns:
        OpResult with CONTAINER_NOT_RUNNING error, or None if running.
    """
    from .container_ops import ensure_container_running

    running_ok, running_msg = ensure_container_running(container_name)
    if not running_ok:
        return OpResult(
            success=False,
            message=f"Container '{container_name}' is not running. {running_msg}",
            error=OpError.CONTAINER_NOT_RUNNING,
        )
    return None


# =============================================================================
# Push: Preflight + Execute
# =============================================================================

def preflight_push(
    host_path: Path,
    container_name: str,
    container_root: str,
    host_container_root: Path,
    pushed_files: set[Path],
) -> OpResult:
    """Validate preconditions before push. Returns warnings/errors without executing.

    Error checks (blocking):
      1. host_path.exists()                    -> HOST_FILE_NOT_FOUND
      2. host_path.relative_to(hcr)            -> INVALID_LOCATION
      3. ensure_container_running(name)         -> CONTAINER_NOT_RUNNING

    Warning checks (confirmable):
      4. path in pushed_files?                  -> FILE_ALREADY_TRACKED

    Args:
        host_path: Host file to push
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        pushed_files: Current set of tracked pushed file paths

    Returns:
        OpResult with error or warnings (success=True if no blocking errors)
    """
    # Error checks
    if not host_path.exists():
        return OpResult(
            success=False,
            message=f"File not found: {host_path.name}",
            error=OpError.HOST_FILE_NOT_FOUND,
        )

    if err := _validate_path_under_root(host_path, host_container_root):
        return err

    if err := _validate_container_running(container_name):
        return err

    # Warning checks
    warnings: list[OpWarning] = []
    if host_path in pushed_files:
        warnings.append(OpWarning.FILE_ALREADY_TRACKED)

    return OpResult(success=True, message="Ready to push", warnings=warnings)


def execute_push(
    host_path: Path,
    container_name: str,
    container_root: str,
    host_container_root: Path,
    file_filter: FileFilter = passthrough,
) -> OpResult:
    """Execute push: resolve path, ensure dirs, docker cp.

    Args:
        host_path: Host file to push
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        file_filter: Optional content filter (default: passthrough)

    Returns:
        OpResult with success/failure
    """
    from pathlib import PurePosixPath
    from .container_ops import push_file_to_container, ensure_container_directories

    container_path = resolve_container_path(host_path, container_root, host_container_root)

    # Compute parent directory (path computation belongs in orchestrator)
    parent_dir = str(PurePosixPath(container_path).parent)
    dirs_to_create = [parent_dir] if parent_dir not in ('/', '.', '') else []

    # Ensure parent directory exists in container
    dir_ok, dir_msg = ensure_container_directories(container_name, dirs_to_create)
    if not dir_ok:
        return OpResult(success=False, message=f"Failed to prepare container: {dir_msg}")

    # Apply file filter (produces temp file or returns original)
    push_source = file_filter(host_path)
    if push_source is None:
        push_source = host_path

    success, msg = push_file_to_container(container_name, push_source, container_path)
    if success:
        return OpResult(success=True, message=f"Pushed {host_path.name}")
    return OpResult(success=False, message=f"Failed to push {host_path.name}: {msg}")


# =============================================================================
# Pull: Preflight + Execute
# =============================================================================

def preflight_pull(
    host_path: Path,
    container_name: str,
    container_root: str,
    host_container_root: Path,
    host_project_root: Path,
    dev_mode: bool,
) -> OpResult:
    """Validate preconditions before pull.

    Error checks (blocking):
      1. host_path.relative_to(hcr)            -> INVALID_LOCATION
      2. ensure_container_running(name)         -> CONTAINER_NOT_RUNNING

    Warning checks (confirmable):
      3. local file exists AND not dev_mode     -> LOCAL_FILE_EXISTS

    Args:
        host_path: Host file path (used for path computation)
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        host_project_root: Project root (for dev_mode output path)
        dev_mode: Whether dev_mode is enabled

    Returns:
        OpResult with error or warnings
    """
    if err := _validate_path_under_root(host_path, host_container_root):
        return err

    if err := _validate_container_running(container_name):
        return err

    warnings: list[OpWarning] = []
    if not dev_mode and host_path.exists():
        warnings.append(OpWarning.LOCAL_FILE_EXISTS)

    return OpResult(success=True, message="Ready to pull", warnings=warnings)


def execute_pull(
    host_path: Path,
    container_name: str,
    container_root: str,
    host_container_root: Path,
    host_project_root: Path,
    dev_mode: bool,
    timestamp: str | None = None,
) -> OpResult:
    """Execute pull: resolve paths, docker cp container->host.

    Args:
        host_path: Original host file path (for path computation)
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        host_project_root: Project root (for output path)
        dev_mode: Whether dev_mode is enabled
        timestamp: Optional shared timestamp for batch pulls

    Returns:
        OpResult with success/failure
    """
    from .container_ops import pull_file_from_container

    container_path = resolve_container_path(host_path, container_root, host_container_root)
    rel_path = host_path.relative_to(host_project_root)
    dest_path = resolve_pull_output(host_project_root, rel_path, dev_mode, timestamp)

    # Ensure host destination directory exists (dev_mode creates novel paths)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    success, msg = pull_file_from_container(container_name, container_path, dest_path)
    if success:
        return OpResult(success=True, message=f"Pulled {host_path.name}")
    return OpResult(success=False, message=f"Failed to pull {host_path.name}: {msg}")


# =============================================================================
# Remove: Preflight + Execute
# =============================================================================

def preflight_remove(
    host_path: Path,
    container_name: str,
    container_root: str,
    host_container_root: Path,
) -> OpResult:
    """Validate preconditions before remove-file.

    Error checks (blocking):
      1. host_path.relative_to(hcr)            -> INVALID_LOCATION
      2. ensure_container_running(name)         -> CONTAINER_NOT_RUNNING

    Warning checks (confirmable):
      3. Always                                 -> DESTRUCTIVE_REMOVE

    Args:
        host_path: Host file path (for path computation)
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory

    Returns:
        OpResult with error or warnings
    """
    if err := _validate_path_under_root(host_path, host_container_root):
        return err

    if err := _validate_container_running(container_name):
        return err

    return OpResult(
        success=True,
        message="Ready to remove",
        warnings=[OpWarning.DESTRUCTIVE_REMOVE],
    )


def execute_remove(
    host_path: Path,
    container_name: str,
    container_root: str,
    host_container_root: Path,
) -> OpResult:
    """Execute remove: resolve path, docker exec rm.

    Args:
        host_path: Host file path (for path computation)
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory

    Returns:
        OpResult with success/failure
    """
    from .container_ops import remove_file_from_container

    container_path = resolve_container_path(host_path, container_root, host_container_root)

    success, msg = remove_file_from_container(container_name, container_path)
    if success:
        return OpResult(success=True, message=f"Removed {host_path.name}")
    return OpResult(success=False, message=f"Failed to remove {host_path.name}: {msg}")


# =============================================================================
# Batch Wrappers
# =============================================================================

def preflight_push_batch(
    host_paths: list[Path],
    container_name: str,
    container_root: str,
    host_container_root: Path,
    pushed_files: set[Path],
) -> BatchFileResult:
    """Validate ALL files before executing any.

    Returns categorized results so caller can:
    - Show all errors at once (GUI: summary dialog, CLI: error list)
    - Show all warnings at once (GUI: "N files need confirmation", CLI: --force)
    - Execute only clean + confirmed files

    Args:
        host_paths: List of host file paths to check
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        pushed_files: Current set of tracked pushed file paths

    Returns:
        BatchFileResult with errors, warnings, clean categorization
    """
    result = BatchFileResult()

    for path in host_paths:
        r = preflight_push(path, container_name, container_root, host_container_root, pushed_files)
        if r.error:
            result.errors[path] = r
        elif r.warnings:
            result.warnings[path] = r
        else:
            result.clean.append(path)

    return result


def execute_push_batch(
    host_paths: list[Path],
    container_name: str,
    container_root: str,
    host_container_root: Path,
    file_filter: FileFilter = passthrough,
) -> dict[Path, OpResult]:
    """Execute push for multiple files. Returns per-file results.

    Args:
        host_paths: List of host file paths to push
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        file_filter: Optional content filter (default: passthrough)

    Returns:
        Dict mapping each path to its OpResult
    """
    results: dict[Path, OpResult] = {}
    for path in host_paths:
        results[path] = execute_push(
            path, container_name, container_root, host_container_root, file_filter
        )
    return results


def preflight_pull_batch(
    host_paths: list[Path],
    container_name: str,
    container_root: str,
    host_container_root: Path,
    host_project_root: Path,
    dev_mode: bool,
) -> BatchFileResult:
    """Validate ALL files before pulling any.

    Args:
        host_paths: List of host file paths to check
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        host_project_root: Project root (for dev_mode output path)
        dev_mode: Whether dev_mode is enabled

    Returns:
        BatchFileResult with errors, warnings, clean categorization
    """
    result = BatchFileResult()

    for path in host_paths:
        r = preflight_pull(
            path, container_name, container_root,
            host_container_root, host_project_root, dev_mode,
        )
        if r.error:
            result.errors[path] = r
        elif r.warnings:
            result.warnings[path] = r
        else:
            result.clean.append(path)

    return result


def execute_pull_batch(
    host_paths: list[Path],
    container_name: str,
    container_root: str,
    host_container_root: Path,
    host_project_root: Path,
    dev_mode: bool,
    timestamp: str | None = None,
) -> dict[Path, OpResult]:
    """Execute pull for multiple files. Returns per-file results.

    Uses a single timestamp for consistent dev-mode output directory.

    Args:
        host_paths: List of host file paths to pull
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory
        host_project_root: Project root (for output path)
        dev_mode: Whether dev_mode is enabled
        timestamp: Optional shared timestamp (auto-generated if None)

    Returns:
        Dict mapping each path to its OpResult
    """
    if dev_mode and timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results: dict[Path, OpResult] = {}
    for path in host_paths:
        results[path] = execute_pull(
            path, container_name, container_root,
            host_container_root, host_project_root, dev_mode, timestamp,
        )
    return results


def preflight_remove_batch(
    host_paths: list[Path],
    container_name: str,
    container_root: str,
    host_container_root: Path,
) -> BatchFileResult:
    """Validate ALL files before removing any.

    Args:
        host_paths: List of host file paths to check
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory

    Returns:
        BatchFileResult with errors, warnings, clean categorization
    """
    result = BatchFileResult()

    for path in host_paths:
        r = preflight_remove(path, container_name, container_root, host_container_root)
        if r.error:
            result.errors[path] = r
        elif r.warnings:
            result.warnings[path] = r
        else:
            result.clean.append(path)

    return result


def execute_remove_batch(
    host_paths: list[Path],
    container_name: str,
    container_root: str,
    host_container_root: Path,
) -> dict[Path, OpResult]:
    """Execute remove for multiple files. Returns per-file results.

    Args:
        host_paths: List of host file paths to remove
        container_name: Docker container name
        container_root: Container root path
        host_container_root: Host ancestor directory

    Returns:
        Dict mapping each path to its OpResult
    """
    results: dict[Path, OpResult] = {}
    for path in host_paths:
        results[path] = execute_remove(
            path, container_name, container_root, host_container_root,
        )
    return results
