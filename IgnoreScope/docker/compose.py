"""Docker compose file generation with masked volume layering.

Provides functions for generating docker-compose.yml with proper
mount, masked, and revealed (punch-through) volume configuration.

Also provides extension-enabled Dockerfile generation for containers
that include Claude Code or other extensions.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.constants import CONTAINER_CLAUDE_AUTH
from ..core.config import DEFAULT_CONTAINER_ROOT
from ..utils.strings import sanitize_volume_name

if TYPE_CHECKING:
    from ..container_ext.install_extension import ExtensionInstaller


def generate_dockerfile(
    project_name: str = "",
    container_root: str = DEFAULT_CONTAINER_ROOT,
) -> str:
    """Generate a minimal Dockerfile for IgnoreScope containers.

    Creates a Python-based container with:
      - Python 3.11 slim base
      - Working directory at container_root/project_name
      - Infinite sleep to keep container running

    Args:
        project_name: Optional project name (used in comments and workdir)
        container_root: Container root path (default: /workspace)

    Returns:
        Dockerfile content as string
    """
    now = datetime.now().strftime("%Y-%m-%d")
    name = project_name or "IgnoreScope"
    workdir = f"{container_root}/{project_name}" if project_name else container_root

    return f"""\
# IgnoreScope Container
# Project: {name}
# Generated: {now}
#
# Minimal container for file push/pull via docker cp.
# Uses infinite sleep to keep container running.

FROM python:3.11-slim

LABEL maintainer="IgnoreScope"
LABEL description="Container for selective file visibility via docker cp"

ENV PATH="/root/.local/bin:$PATH"

WORKDIR {workdir}

# Keep container running indefinitely
CMD ["sleep", "infinity"]
"""


def generate_compose_with_masks(
    ordered_volumes: list[str],
    mask_volume_names: list[str],
    host_project_root: Path,
    service_name: str = "claude",
    project_name: str = "",
    image: str = "",
    extra_mounts: list | None = None,
    docker_container_name: str = "",
    docker_image_name: str = "",
    docker_volume_name: str = "",
    container_root: str = DEFAULT_CONTAINER_ROOT,
    isolation_volume_entries: list[str] | None = None,
    isolation_volume_names: list[str] | None = None,
    stencil_volume_entries: list[str] | None = None,
    stencil_volume_names: list[str] | None = None,
    ports: list[str] | None = None,
) -> str:
    """Generate docker-compose.yml from pre-computed hierarchy data.

    Compose formats YAML — it never derives volume entries.
    Volume ordering and layering is computed by hierarchy.py.

    Args:
        ordered_volumes: Pre-computed volume entries from ContainerHierarchy
        mask_volume_names: Named mask volumes for the volumes declaration section
        host_project_root: Project root path
        service_name: Name for the Docker service
        project_name: Optional project name (used in comments and container paths)
        image: Optional image name (default: claude-{project_name}:latest)
        extra_mounts: Additional mount objects prepended before base mounts
        docker_container_name: Explicit container name (overrides auto-derived)
        docker_image_name: Explicit image name (overrides auto-derived)
        docker_volume_name: Explicit volume name (overrides auto-derived)
        container_root: Container root path (default: /workspace)
        isolation_volume_entries: Layer 4 volume entries ("name:container_path"); always emitted
        isolation_volume_names: Named isolation volumes (Layer 4) for the volumes section
        stencil_volume_entries: L_volume entries for delivery="volume" specs ("name:container_path")
        stencil_volume_names: Named stencil volumes for the volumes declaration section
        ports: List of port mappings (e.g., ["3900:3900", "8080:8080"])

    Returns:
        docker-compose.yml content as string
    """
    now = datetime.now().strftime("%Y-%m-%d")
    name = project_name or host_project_root.name

    # Use explicit names if provided, otherwise fall back to legacy naming
    if docker_container_name:
        container_name = docker_container_name
        image_name = docker_image_name or f"{container_name}:latest"
        volume_name = docker_volume_name or f"{container_name}-claude-auth"
        compose_project_name = sanitize_volume_name(container_name)
    else:
        volume_name = f"{sanitize_volume_name(name)}-claude-auth"
        container_name = f"claude-{sanitize_volume_name(name)}"
        image_name = image or f"{container_name}:latest"
        compose_project_name = sanitize_volume_name(name)

    path_prefix = f"{container_root}/{project_name}" if project_name else container_root

    lines = [
        "# IgnoreScope Configuration (Masked Volumes)",
        f"# Project: {name}",
        f"# Generated: {now}",
        "# Source: ContainerHierarchy with masked volume layering",
        "",
        f"name: {compose_project_name}",
        "",
        "services:",
        f"  {service_name}:",
        f"    container_name: {container_name}",
        f"    image: {image_name}",
        "    build: .",
        "    volumes:",
        "      # === Auth volume (named - persists across rebuilds) ===",
        f"      - \"{volume_name}:{CONTAINER_CLAUDE_AUTH}\"",
    ]

    # Extra mounts (e.g. .llm → .claude, .igs → .ignore_scope)
    if extra_mounts:
        lines.append("")
        lines.append("      # === Extra mounts ===")
        for mount in extra_mounts:
            comment = f"  # {mount.get('reason', '')}" if isinstance(mount, dict) and mount.get('reason') else ""
            if isinstance(mount, dict):
                volume = mount.get('volume', '')
            else:
                volume = str(mount)
            lines.append(f"      - \"{volume}\"{comment}")

    # Volume layers: L1-L3 + siblings (ordered_volumes, skipped by caller in Isolation mode)
    # followed by L_volume stencil entries (delivery="volume" specs)
    # followed by L4 isolation entries (always emitted regardless of mode).
    if ordered_volumes or stencil_volume_entries or isolation_volume_entries:
        lines.append("")
        lines.append("      # === Volume layers (bind mounts, masks, reveals, stencil volumes, isolation) ===")
        for entry in ordered_volumes:
            lines.append(f"      - \"{entry}\"")
        for entry in (stencil_volume_entries or []):
            lines.append(f"      - \"{entry}\"")
        for entry in (isolation_volume_entries or []):
            lines.append(f"      - \"{entry}\"")

    lines.extend([
        "",
        f"    working_dir: {path_prefix}",
        "    stdin_open: true",
        "    tty: true",
    ])

    # Add ports if specified
    if ports:
        lines.append("    ports:")
        for port in ports:
            lines.append(f"      - \"{port}\"")

    lines.extend([
        "",
        "volumes:",
        f"  {volume_name}:",
        "    name: " + volume_name,
    ])

    # Declare mask volumes (nocopy — populated by docker cp at runtime)
    for vol_name in mask_volume_names:
        lines.append(f"  {vol_name}:")

    # Declare stencil volumes (L_volume — delivery="volume" specs, container-owned)
    for vol_name in (stencil_volume_names or []):
        lines.append(f"  {vol_name}:")

    # Declare isolation volumes (Layer 4 — persistent, container-owned)
    for vol_name in (isolation_volume_names or []):
        lines.append(f"  {vol_name}:")

    lines.append("")

    return '\n'.join(lines)

