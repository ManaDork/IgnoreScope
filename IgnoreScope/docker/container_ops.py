"""Docker container operations — subprocess layer.

# NOTE: "containers" in CLI correspond to "scopes" in GUI.

IS:  Low-level Docker subprocess calls:
     - Docker availability checks (is_docker_installed, is_docker_running)
     - Container state queries (container_exists, get_container_info)
     - Image/volume management (build_image, volume_exists, remove_volume)
     - Compose operations (create_container_compose, remove_container_compose)
     - Container file I/O (push/pull/remove via docker cp)
     - Container filesystem inspection (scan_container_directory)
     - Terminal/LLM command generation

IS NOT: Orchestration (→ container_lifecycle.py: create/update/remove flows)
        File operation orchestration (→ file_ops.py: push/pull/remove flows)
        Path computation (→ core/config.py, core/hierarchy.py)
"""

import json as _json
import logging
import os
import subprocess
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

from ..utils.subprocess_helpers import get_subprocess_kwargs


# =============================================================================
# Infrastructure
# =============================================================================

def _get_compose_commands() -> list[list[str]]:
    """Get docker-compose command prefixes for current OS.

    Windows: Docker Desktop required, use 'docker compose' only.
    Linux/macOS: May have standalone 'docker-compose', try both.
    """
    if sys.platform == 'win32':
        # Docker Desktop provides 'docker compose' plugin
        return [['docker', 'compose']]
    else:
        # Linux/macOS: try plugin first, fallback to standalone
        return [['docker', 'compose'], ['docker-compose']]


def _extract_error_message(result: subprocess.CompletedProcess, include_stdout: bool = True) -> str:
    """Extract the most informative error message from a subprocess result.

    Args:
        result: Completed subprocess result.
        include_stdout: If True, fall back to stdout when stderr is empty.

    Returns:
        Error message string, never empty.
    """
    msg = result.stderr.strip()
    if not msg and include_stdout:
        msg = result.stdout.strip()
    return msg or f"Exit code {result.returncode}"


def is_docker_installed() -> bool:
    """Check if Docker CLI is available."""
    return shutil.which('docker') is not None


def is_docker_running() -> tuple[bool, str]:
    """Check if Docker daemon is running.

    Returns:
        Tuple of (is_running, message)
    """
    if not is_docker_installed():
        return False, "Docker is not installed"

    try:
        result = subprocess.run(['docker', 'info'], **get_subprocess_kwargs(timeout=5))
        if result.returncode == 0:
            return True, "Docker is running"
        else:
            # Docker installed but daemon not running
            if 'Cannot connect' in result.stderr or 'error during connect' in result.stderr:
                return False, "Docker Desktop is not running. Please start Docker Desktop."
            return False, f"Docker error: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "Docker command timed out - Docker may be starting"
    except Exception as e:
        return False, f"Error checking Docker: {e}"


# =============================================================================
# Container State
# =============================================================================

def container_exists(container_name: str) -> bool:
    """Check if container exists (running or stopped) via docker inspect.

    Named "containers" in CLI, "scopes" in GUI.

    Args:
        container_name: Name of container

    Returns:
        True if container exists
    """
    return get_container_info(container_name) is not None


def get_container_info(container_name: str) -> Optional[dict]:
    """Get information about a container.

    Named "containers" in CLI, "scopes" in GUI.

    Args:
        container_name: Name of container

    Returns:
        Dict with container info, or None if not found
    """
    try:
        # Use JSON format for reliable parsing (avoid space-splitting issues)
        result = subprocess.run(
            ['docker', 'inspect', '--type', 'container', container_name],
            **get_subprocess_kwargs(timeout=5)
        )

        if result.returncode == 0 and result.stdout.strip():
            data = _json.loads(result.stdout)
            if data and len(data) > 0:
                container = data[0]
                state = container.get('State', {})
                return {
                    'id': container.get('Id', '')[:12],
                    'status': state.get('Status', 'unknown'),
                    'running': state.get('Running', False),
                    'image': container.get('Config', {}).get('Image', ''),
                    'created': container.get('Created', '')
                }
        return None

    except Exception:
        logger.debug("get_container_info failed for '%s'", container_name, exc_info=True)
        return None


def ensure_container_running(container_name: str) -> Tuple[bool, str]:
    """Ensure container is running, start if stopped.

    Args:
        container_name: Name of container

    Returns:
        Tuple of (success, message)
    """
    info = get_container_info(container_name)

    if not info:
        return False, f"Container not found: {container_name}"

    if info.get('running', False):
        return True, f"Container already running: {container_name}"

    # Container exists but is not running, try to start it
    return start_container(container_name)


# =============================================================================
# Container Lifecycle
# =============================================================================

def _run_docker_simple(
    cmd: list[str],
    success_msg: str,
    error_prefix: str,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Run a simple docker command with standard error handling.

    Args:
        cmd: Docker command and arguments.
        success_msg: Message returned on success.
        error_prefix: Prefix for error messages.
        timeout: Command timeout in seconds.

    Returns:
        Tuple of (success, message).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, success_msg
        return False, f"{error_prefix}: {_extract_error_message(result, include_stdout=False)}"
    except subprocess.TimeoutExpired:
        return False, f"{error_prefix} timed out"
    except Exception as e:
        return False, f"{error_prefix}: {e}"


def start_container(container_name: str) -> tuple[bool, str]:
    """Start a stopped container.

    Args:
        container_name: Name of container to start

    Returns:
        Tuple of (success, message)
    """
    return _run_docker_simple(
        ['docker', 'start', container_name],
        f"Container '{container_name}' started",
        "Failed to start container",
    )


def stop_container(container_name: str, timeout: int = 10) -> tuple[bool, str]:
    """Stop a running container.

    Args:
        container_name: Name of container to stop
        timeout: Seconds to wait before killing

    Returns:
        Tuple of (success, message)
    """
    return _run_docker_simple(
        ['docker', 'stop', '-t', str(timeout), container_name],
        f"Container '{container_name}' stopped",
        "Failed to stop container",
        timeout=timeout + 30,
    )


def create_container_compose(
    compose_dir: Path,
    service_name: str = "claude",
    expected_container_name: Optional[str] = None
) -> tuple[bool, str, Optional[str]]:
    """Create a Docker container using docker-compose.

    Uses docker-compose.yml which defines named volumes properly.
    This ensures the auth volume is created and mounted correctly.

    Args:
        compose_dir: Directory containing docker-compose.yml
        service_name: Service name in docker-compose.yml (default: "claude")
        expected_container_name: Expected container name (used as fallback if detection fails)

    Returns:
        Tuple of (success, message, container_name or None)
    """
    compose_file = compose_dir / 'docker-compose.yml'
    if not compose_file.exists():
        return False, f"docker-compose.yml not found at {compose_dir}", None

    try:
        for cmd_prefix in _get_compose_commands():
            result = subprocess.run(
                cmd_prefix + ['-f', str(compose_file), 'up', '--no-start', service_name],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(compose_dir),
                timeout=60
            )

            # Check if command itself was not found (try next prefix)
            stderr_lower = result.stderr.lower()
            cmd_not_found = (
                'not found' in stderr_lower or
                'not recognized' in stderr_lower or
                'is not recognized' in stderr_lower
            )
            if cmd_not_found:
                continue

            if result.returncode == 0:
                # Get the container name from docker-compose
                name_result = subprocess.run(
                    cmd_prefix + ['-f', str(compose_file), 'ps', '-a', '--format', 'json'],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=str(compose_dir),
                    timeout=10
                )

                container_name = None
                if name_result.returncode == 0 and name_result.stdout.strip():
                    try:
                        for line in name_result.stdout.strip().split('\n'):
                            if line.strip():
                                data = _json.loads(line)
                                if data.get('Service') == service_name:
                                    container_name = data.get('Name')
                                    break
                    except _json.JSONDecodeError:
                        logger.debug("Failed to parse compose ps JSON output", exc_info=True)

                # Fallback: use expected name or construct from compose dir
                if not container_name:
                    if expected_container_name:
                        container_name = expected_container_name
                    else:
                        project_name = compose_dir.name.lower().replace(' ', '_')
                        container_name = f"{project_name}-{service_name}-1"

                return True, f"Container created via docker-compose", container_name

            # Command found but failed - report the actual error
            error_msg = _extract_error_message(result)
            return False, f"docker compose up --no-start failed: {error_msg}", None

        cmds_tried = [' '.join(c) for c in _get_compose_commands()]
        return False, f"docker-compose not available (tried: {', '.join(cmds_tried)})", None

    except subprocess.TimeoutExpired:
        return False, "Container creation timed out", None
    except Exception as e:
        return False, f"Error creating container: {e}", None


def remove_container_compose(
    compose_dir: Path,
    remove_volumes: bool = True,
    remove_images: bool = False,
) -> tuple[bool, str, list[str]]:
    """Remove container and optionally volumes/images using docker compose down.

    Args:
        compose_dir: Directory containing docker-compose.yml
        remove_volumes: If True, also remove all volumes (including mask volumes)
        remove_images: If True, also remove images

    Returns:
        Tuple of (success, message, list of removed volume names)
    """
    compose_file = compose_dir / 'docker-compose.yml'
    if not compose_file.exists():
        return False, f"docker-compose.yml not found at {compose_dir}", []

    try:
        for cmd_prefix in _get_compose_commands():
            cmd = cmd_prefix + ['-f', str(compose_file), 'down']

            if remove_volumes:
                cmd.append('-v')
            if remove_images:
                cmd.append('--rmi')
                cmd.append('all')

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=60
            )

            if result.returncode == 0:
                removed_volumes = []
                for line in result.stderr.split('\n'):
                    if 'volume' in line.lower() and 'remov' in line.lower():
                        parts = line.split()
                        if parts:
                            vol_name = parts[-1].strip()
                            if vol_name:
                                removed_volumes.append(vol_name)

                msg = "Container removed via docker compose down"
                if remove_volumes:
                    msg += f" (including {len(removed_volumes)} volume(s))"
                return True, msg, removed_volumes

            if 'not found' in result.stderr.lower() or result.returncode == 127:
                continue

            error_msg = _extract_error_message(result)
            return False, f"docker compose down failed: {error_msg}", []

        cmds_tried = [' '.join(c) for c in _get_compose_commands()]
        return False, f"docker compose not available (tried: {', '.join(cmds_tried)})", []

    except subprocess.TimeoutExpired:
        return False, "Container removal timed out", []
    except Exception as e:
        return False, f"Error removing container: {e}", []


# =============================================================================
# Image & Volume
# =============================================================================

def image_exists(image_name: str) -> bool:
    """Check if an image with the given name exists.

    Args:
        image_name: Name of image to check (with or without tag)

    Returns:
        True if image exists
    """
    try:
        result = subprocess.run(
            ['docker', 'images', '-q', image_name],
            **get_subprocess_kwargs(timeout=5)
        )
        return bool(result.stdout.strip())
    except Exception:
        logger.debug("image_exists check failed for '%s'", image_name, exc_info=True)
        return False


def build_image(
    dockerfile_dir: Path,
    image_name: str,
    on_progress: Optional[Callable[[str], None]] = None
) -> tuple[bool, str]:
    """Build Docker image from Dockerfile.

    Args:
        dockerfile_dir: Directory containing Dockerfile
        image_name: Name:tag for the image (e.g., "claude-myproject:latest")
        on_progress: Callback for build progress lines

    Returns:
        Tuple of (success, message)
    """
    dockerfile_path = dockerfile_dir / 'Dockerfile'
    if not dockerfile_path.exists():
        return False, f"Dockerfile not found at {dockerfile_path}"

    try:
        process = subprocess.Popen(
            ['docker', 'build', '-t', image_name, '.'],
            cwd=str(dockerfile_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )

        output_lines = []
        for line in iter(process.stdout.readline, ''):
            line = line.rstrip()
            if line:
                output_lines.append(line)
                if on_progress:
                    on_progress(line)

        process.wait()

        if process.returncode == 0:
            return True, f"Image '{image_name}' built successfully"
        else:
            # Include tail of build output so the caller has diagnostics
            tail = output_lines[-20:] if output_lines else ["(no output captured)"]
            detail = "\n".join(tail)
            return False, f"Build failed:\n{detail}"

    except Exception as e:
        return False, f"Build error: {e}"


def volume_exists(volume_name: str) -> bool:
    """Check if a Docker volume exists.

    Args:
        volume_name: Name of volume to check

    Returns:
        True if volume exists
    """
    try:
        result = subprocess.run(
            ['docker', 'volume', 'inspect', volume_name],
            **get_subprocess_kwargs(timeout=5)
        )
        return result.returncode == 0
    except Exception:
        logger.debug("volume_exists check failed for '%s'", volume_name, exc_info=True)
        return False


def remove_volume(volume_name: str, timeout: int = 30) -> tuple[bool, str]:
    """Remove a Docker volume.

    Args:
        volume_name: Name of volume to remove
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, message)
    """
    try:
        result = subprocess.run(
            ['docker', 'volume', 'rm', volume_name],
            **get_subprocess_kwargs(timeout=timeout)
        )
        if result.returncode == 0:
            return True, f"Volume '{volume_name}' removed"
        else:
            error = _extract_error_message(result, include_stdout=False)
            return False, f"Failed to remove volume '{volume_name}': {error}"
    except subprocess.TimeoutExpired:
        return False, f"Volume removal timed out for '{volume_name}'"
    except Exception as e:
        return False, f"Error removing volume '{volume_name}': {e}"


# =============================================================================
# Container Exec
# =============================================================================

def exec_in_container(
    container_name: str,
    command: list[str],
    timeout: int = 30,
) -> tuple[bool, str, str]:
    """Execute command in running container via docker exec (non-interactive).

    Args:
        container_name: Name of target container
        command: Command and arguments to execute
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ['docker', 'exec', container_name] + command,
            **get_subprocess_kwargs(timeout),
        )
        return (
            result.returncode == 0,
            result.stdout.strip() if result.stdout else "",
            result.stderr.strip() if result.stderr else "",
        )
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


# =============================================================================
# File Operations (docker cp)
# =============================================================================

def push_file_to_container(
    container_name: str,
    host_file: Path,
    container_path: str,
    timeout: int = 30
) -> Tuple[bool, str]:
    """Push file from host to container using docker cp.

    Args:
        container_name: Name of target container
        host_file: Path to file on host
        container_path: Path in container (e.g., '/workspace/src/config.ini')
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, message)
    """
    if not host_file.exists():
        return False, f"File not found: {host_file}"

    if not host_file.is_file() and not host_file.is_dir():
        return False, f"Not a file or directory: {host_file}"

    try:
        result = subprocess.run(
            ['docker', 'cp', str(host_file), f'{container_name}:{container_path}'],
            **get_subprocess_kwargs(timeout)
        )

        if result.returncode == 0:
            return True, f"Pushed: {host_file.name}"
        else:
            error = _extract_error_message(result, include_stdout=False)
            return False, error

    except subprocess.TimeoutExpired:
        return False, f"Timeout pushing {host_file.name}"
    except Exception as e:
        return False, f"Error pushing {host_file.name}: {e}"


def pull_file_from_container(
    container_name: str,
    container_path: str,
    host_file: Path,
    timeout: int = 30
) -> Tuple[bool, str]:
    """Pull file from container to host using docker cp.

    Args:
        container_name: Name of source container
        container_path: Path in container (e.g., '/workspace/src/config.ini')
        host_file: Path to write on host
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, message)
    """
    try:
        result = subprocess.run(
            ['docker', 'cp', f'{container_name}:{container_path}', str(host_file)],
            **get_subprocess_kwargs(timeout)
        )

        if result.returncode == 0:
            return True, f"Pulled: {host_file.name}"
        else:
            error = _extract_error_message(result, include_stdout=False)
            return False, error

    except subprocess.TimeoutExpired:
        return False, f"Timeout pulling {container_path}"
    except Exception as e:
        return False, f"Error pulling {container_path}: {e}"


def push_directory_contents_to_container(
    container_name: str,
    host_dir: Path,
    container_path: str,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """Copy CONTENTS of host_dir into container_path using ``docker cp host_dir/. ...``.

    The ``/.`` suffix is the canonical docker-cp pattern for copying a
    directory's contents into an existing destination (rather than nesting
    the source directory under it). Required by the Virtual Mount preserve
    flow, which restores staged content into a freshly-mkdir'd container
    path.

    Args:
        container_name: Name of target container
        host_dir: Host directory whose contents are copied
        container_path: Destination path in container (must exist)
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, message)
    """
    if not host_dir.is_dir():
        return False, f"Not a directory: {host_dir}"

    src_spec = os.path.join(str(host_dir), ".")
    try:
        result = subprocess.run(
            ['docker', 'cp', src_spec, f'{container_name}:{container_path}'],
            **get_subprocess_kwargs(timeout),
        )
        if result.returncode == 0:
            return True, f"Pushed contents: {host_dir}"
        error = _extract_error_message(result, include_stdout=False)
        return False, error
    except subprocess.TimeoutExpired:
        return False, f"Timeout pushing contents of {host_dir}"
    except Exception as e:
        return False, f"Error pushing contents of {host_dir}: {e}"


def ensure_container_directories(
    container_name: str,
    directory_paths: list[str],
    timeout: int = 10,
) -> Tuple[bool, str]:
    """Create directories inside container via mkdir -p.

    Receives pre-computed directory paths. Path computation
    belongs in the orchestration layer (file_ops.py, hierarchy.py).

    Args:
        container_name: Name of target container
        directory_paths: Pre-computed container directory paths to create
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, message)
    """
    if not directory_paths:
        return True, "No directories to create"

    success, _, stderr = exec_in_container(
        container_name, ['mkdir', '-p'] + sorted(set(directory_paths)), timeout,
    )

    if success:
        return True, f"Created {len(directory_paths)} directories"
    else:
        return False, f"Failed to create directories: {stderr or 'Unknown error'}"


def scan_container_directory(
    container_name: str,
    container_path: str,
    recursive: bool = True,
    timeout: int = 30
) -> Tuple[bool, list[str]]:
    """Scan a container directory for files.

    Args:
        container_name: Name of target container
        container_path: Path in container to scan
        recursive: If True, scan subdirectories recursively
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, list of file paths relative to container_path)
    """
    if recursive:
        command = ['find', container_path, '-type', 'f', '-printf', '%P\\n']
    else:
        command = ['sh', '-c', f'ls -p "{container_path}" | grep -v /']

    success, stdout, stderr = exec_in_container(container_name, command, timeout)

    if success:
        if not stdout:
            return True, []
        files = [f.strip() for f in stdout.split('\n') if f.strip()]
        return True, files
    else:
        if "No such file or directory" in stderr:
            logger.warning(
                "scan_container_directory: path '%s' does not exist in container '%s'",
                container_path, container_name,
            )
            return True, []
        return False, []


def remove_file_from_container(
    container_name: str,
    container_path: str,
    timeout: int = 30
) -> Tuple[bool, str]:
    """Remove a file from inside the container.

    Args:
        container_name: Name of target container
        container_path: Path in container to remove
        timeout: Command timeout in seconds

    Returns:
        Tuple of (success, message)
    """
    success, _, stderr = exec_in_container(
        container_name, ['rm', '-f', container_path], timeout
    )

    if success:
        return True, f"Removed: {container_path}"
    else:
        return False, stderr or f"Failed to remove {container_path}"


def file_exists_in_container(
    container_name: str,
    container_path: str,
    timeout: int = 10
) -> bool:
    """Check if a file exists inside the container.

    Args:
        container_name: Name of target container
        container_path: Path in container to check

    Returns:
        True if file exists
    """
    success, _, _ = exec_in_container(
        container_name, ['test', '-f', container_path], timeout
    )
    return success


# =============================================================================
# Terminal Command Construction
# =============================================================================

def get_terminal_command(container_name: str) -> str:
    """Build docker exec command string for an interactive bash session.

    Args:
        container_name: Name of target container

    Returns:
        Full docker command string (e.g., 'docker exec -it mycontainer /bin/bash')
    """
    return f"docker exec -it {container_name} /bin/bash"


def get_llm_command(
    container_name: str,
    work_dir: str,
    binary_name: str = "claude",
) -> str:
    """Build docker exec command string for launching an LLM CLI in container.

    Args:
        container_name: Name of target container
        work_dir: Working directory inside the container
        binary_name: LLM binary to invoke (default: "claude")

    Returns:
        Full docker command string
    """
    return f"docker exec -it -w {work_dir} {container_name} {binary_name}"
