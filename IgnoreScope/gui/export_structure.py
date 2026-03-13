"""Container structure text export.

Generates an indented tree showing effective visibility for each directory,
suitable for diffing against actual container scans.
"""

from pathlib import Path

from ..core.config import get_container_path
from ..utils.paths import is_descendant


def generate_container_structure(
    host_project_root: Path,
    container_root: str,
    mounts: set[Path],
    masked: set[Path],
    revealed: set[Path],
    host_container_root: Path | None = None,
) -> str:
    """Generate a text representation of the container's directory structure.

    Walks mounted directories recursively and annotates each entry with
    its effective visibility: [visible], [mirrored], or [hidden].

    Args:
        host_project_root: Host project root path
        container_root: Container root path (e.g., "/{HCR.name}")
        mounts: Set of mounted paths
        masked: Set of masked paths
        revealed: Set of revealed paths
        host_container_root: Host container root (defaults to host_project_root.parent)

    Returns:
        Indented tree string with visibility annotations
    """
    if host_container_root is None:
        host_container_root = host_project_root.parent
    project_offset = host_project_root.relative_to(host_container_root).as_posix()
    lines = [get_container_path(container_root, project_offset) + "/"]
    _walk_directory(
        host_project_root, mounts, masked, revealed,
        host_project_root, lines, indent=1,
        in_masked=False, in_revealed=False,
    )
    return "\n".join(lines)


def _has_revealed_descendant(path: Path, revealed: set[Path]) -> bool:
    """Check if any revealed path is a descendant of the given path."""
    for rev_path in revealed:
        if rev_path == path:
            continue
        try:
            rev_path.relative_to(path)
            return True
        except ValueError:
            continue
    return False


def _get_effective_visibility(
    path: Path,
    mounts: set[Path],
    revealed: set[Path],
    is_mounted: bool,
    is_masked: bool,
    is_revealed: bool,
) -> str:
    """Determine effective visibility for a path."""
    if not is_mounted:
        return "hidden"
    if not is_masked:
        return "visible"
    if is_revealed:
        return "visible"
    if _has_revealed_descendant(path, revealed):
        return "mirrored"
    return "hidden"


def _walk_directory(
    host_project_root: Path,
    mounts: set[Path],
    masked: set[Path],
    revealed: set[Path],
    current_path: Path,
    lines: list[str],
    indent: int,
    in_masked: bool,
    in_revealed: bool,
) -> None:
    """Recursively walk directories and build output lines."""
    try:
        entries = sorted(
            [e for e in current_path.iterdir()
             if e.is_dir() and not e.name.startswith('.')],
            key=lambda p: p.name.lower()
        )
    except (PermissionError, OSError):
        return

    prefix = "  " * indent

    for entry in entries:
        # Check if this path is mounted (directly or via ancestor)
        is_mounted = entry in mounts or any(
            is_descendant(entry, m, strict=False) for m in mounts
        )

        if not is_mounted:
            continue

        # Check mask/reveal status
        is_masked = entry in masked or (in_masked and entry not in revealed)
        is_revealed_here = entry in revealed or in_revealed

        visibility = _get_effective_visibility(
            entry, mounts, revealed,
            is_mounted, is_masked and not is_revealed_here, is_revealed_here,
        )

        lines.append(f"{prefix}{entry.name}/  [{visibility}]")

        # Recurse
        _walk_directory(
            host_project_root, mounts, masked, revealed,
            entry, lines, indent + 1,
            in_masked=is_masked, in_revealed=is_revealed_here,
        )
