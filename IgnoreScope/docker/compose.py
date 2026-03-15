"""Docker compose file generation with masked volume layering.

Provides functions for generating docker-compose.yml with proper
mount, masked, and revealed (punch-through) volume configuration.

Also provides LLM-enabled Dockerfile generation for containers
that include Claude Code or other LLMs.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.constants import CONTAINER_CLAUDE_AUTH
from ..core.config import DEFAULT_CONTAINER_ROOT
from .names import sanitize_volume_name

if TYPE_CHECKING:
    from ..llm.deployer import LLMDeployer


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

WORKDIR {workdir}

# Keep container running indefinitely
CMD ["sleep", "infinity"]
"""


def generate_dockerfile_with_llm(
    deployer: 'LLMDeployer',
    project_name: str = "",
    container_root: str = DEFAULT_CONTAINER_ROOT,
    use_entrypoint: bool = True,
) -> tuple[str, str | None]:
    """Generate Dockerfile with LLM installation.

    SHELVED — not called from production code. execute_create() always calls
    generate_dockerfile() (basic), never this function. No config flag exists
    to toggle it. Kept for future reference.

    Creates a container with:
    - Python 3.11 slim base
    - System packages for LLM
    - LLM installation (e.g., Claude Code)
    - Optional entrypoint for auto-launch

    Args:
        deployer: LLMDeployer instance for the target LLM
        project_name: Optional project name (used in comments and workdir)
        container_root: Container root path (default: /workspace)
        use_entrypoint: If True, also generate entrypoint script

    Returns:
        Tuple of (dockerfile_content, entrypoint_content or None)
    """
    now = datetime.now().strftime("%Y-%m-%d")
    name = project_name or "IgnoreScope"
    snippets = deployer.get_dockerfile_snippets()
    workdir = f"{container_root}/{project_name}" if project_name else container_root

    dockerfile = f"""\
# IgnoreScope Container with {deployer.name}
# Project: {name}
# Generated: {now}
#
# Container with {deployer.name} for interactive LLM sessions.
# Includes masked volume support for selective file visibility.

FROM python:3.11-slim

LABEL maintainer="IgnoreScope"
LABEL description="Container with {deployer.name} for selective file visibility"
LABEL llm="{deployer.binary_name}"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    {snippets.get('packages', 'git curl ca-certificates')} \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR {workdir}

{snippets.get('install', '')}
{snippets.get('env', '')}
"""

    # Add entrypoint if requested
    entrypoint_content = None
    if use_entrypoint:
        entrypoint_content = deployer.get_entrypoint_script(workdir)
        dockerfile += f"""
# Custom entrypoint for {deployer.name} auto-launch
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
"""
    else:
        dockerfile += """
# Keep container running indefinitely
CMD ["sleep", "infinity"]
"""

    return dockerfile, entrypoint_content


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
        f"      - \"{volume_name}:/root/.claude\"",
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

    # Volume layers (pre-computed by hierarchy.py: Layer 1 mounts → Layer 2 masks → Layer 3 reveals → siblings)
    if ordered_volumes:
        lines.append("")
        lines.append("      # === Volume layers (bind mounts, masks, reveals) ===")
        for entry in ordered_volumes:
            lines.append(f"      - \"{entry}\"")

    lines.extend([
        "",
        f"    working_dir: {path_prefix}",
        "    stdin_open: true",
        "    tty: true",
        "",
        "volumes:",
        f"  {volume_name}:",
        "    name: " + volume_name,
    ])

    # Declare mask volumes (nocopy — populated by docker cp at runtime)
    for vol_name in mask_volume_names:
        lines.append(f"  {vol_name}:")

    lines.append("")

    return '\n'.join(lines)

