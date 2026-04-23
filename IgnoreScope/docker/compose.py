"""Docker compose file generation with masked volume layering.

Provides functions for generating docker-compose.yml with proper
mount, masked, and revealed (punch-through) volume configuration.

Also provides extension-enabled Dockerfile generation for containers
that include Claude Code or other extensions.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

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
    container_root: str = DEFAULT_CONTAINER_ROOT,
    volume_entries: list[str] | None = None,
    volume_names: list[str] | None = None,
    ports: list[str] | None = None,
) -> str:
    """Generate docker-compose.yml from pre-computed hierarchy data.

    Compose formats YAML — it never derives volume entries.
    Volume ordering and layering is computed by hierarchy.py.

    Claude auth (``/root/.claude``) flows through the unified extension-synth
    pipeline as a ``vol_*`` entry on ``volume_entries`` / ``volume_names`` —
    no special-case block. The standalone ``{name}-claude-auth`` naming
    scheme was retired in Task 1.7 of ``unify-l4-reclaim-isolation-term``.

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
        container_root: Container root path (default: /workspace)
        volume_entries: L_volume entries for every ``delivery="volume"`` spec
            (user-authored + extension-synthesized, including Claude auth) —
            ``"name:container_path"`` format, survives ``docker compose up/down``
            by design
        volume_names: Named L_volume volumes for the top-level volumes section
            (one-to-one with ``volume_entries``)
        ports: List of port mappings (e.g., ["3900:3900", "8080:8080"])

    Returns:
        docker-compose.yml content as string
    """
    now = datetime.now().strftime("%Y-%m-%d")
    name = project_name or host_project_root.name

    if docker_container_name:
        container_name = docker_container_name
        image_name = docker_image_name or f"{container_name}:latest"
        compose_project_name = sanitize_volume_name(container_name)
    else:
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
    ]

    # Extra mounts (e.g. .llm → .claude, .igs → .ignore_scope)
    if extra_mounts:
        lines.append("      # === Extra mounts ===")
        for mount in extra_mounts:
            comment = f"  # {mount.get('reason', '')}" if isinstance(mount, dict) and mount.get('reason') else ""
            if isinstance(mount, dict):
                volume = mount.get('volume', '')
            else:
                volume = str(mount)
            lines.append(f"      - \"{volume}\"{comment}")

    # Volume layers: L1-L3 + siblings (ordered_volumes) followed by the
    # unified L_volume tier entries (every delivery="volume" spec —
    # user-authored plus extension-synthesized, including Claude auth at
    # /root/.claude).
    if ordered_volumes or volume_entries:
        lines.append("      # === Volume layers (bind mounts, masks, reveals, named volumes) ===")
        for entry in ordered_volumes:
            lines.append(f"      - \"{entry}\"")
        for entry in (volume_entries or []):
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

    # Top-level volumes section — emit iff there is anything to declare.
    # Mask volumes + L_volume tier volumes (delivery="volume" specs, container-owned;
    # both user-authored and extension-synthesized flow through the same list).
    if mask_volume_names or volume_names:
        lines.extend(["", "volumes:"])
        for vol_name in mask_volume_names:
            lines.append(f"  {vol_name}:")
        for vol_name in (volume_names or []):
            lines.append(f"  {vol_name}:")

    lines.append("")

    return '\n'.join(lines)

