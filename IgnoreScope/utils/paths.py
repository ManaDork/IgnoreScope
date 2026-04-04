"""Path helper utilities for consistent path conversion across IgnoreScope.

Provides unified functions for:
- Relative path conversion with posix-style output
- Path containment validation
- Directory pattern formatting

Future: Consider using stdlib pathlib methods instead of custom helpers
"""

import os
from pathlib import Path
from typing import Optional


def to_relative_posix(path: Path, root: Path, fallback_absolute: bool = True) -> str:
    """Convert path to relative posix-style string.

    Args:
        path: Path to convert
        root: Root directory to make relative to
        fallback_absolute: If True, return absolute path when not relative.
                          If False, return empty string.

    Returns:
        Relative posix path string, or absolute/empty on failure

    Examples:
        >>> to_relative_posix(Path('C:/project/src/main.py'), Path('C:/project'))
        'src/main.py'
        >>> to_relative_posix(Path('D:/other/file.py'), Path('C:/project'))
        'D:/other/file.py'  # fallback to absolute
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        if fallback_absolute:
            return path.as_posix()
        return ''


def to_relative_posix_or_name(path: Path, root: Path) -> str:
    """Convert path to relative posix string, fallback to just the name.

    Useful for UI display where showing filename is better than absolute path.

    Args:
        path: Path to convert
        root: Root directory to make relative to

    Returns:
        Relative posix path string, or just the path name

    Examples:
        >>> to_relative_posix_or_name(Path('C:/project/src/main.py'), Path('C:/project'))
        'src/main.py'
        >>> to_relative_posix_or_name(Path('D:/other/file.py'), Path('C:/project'))
        'file.py'  # fallback to name
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def to_dir_pattern(rel_path: str) -> str:
    """Add trailing slash for directory pattern matching.

    Args:
        rel_path: Relative path string (already posix-style)

    Returns:
        Path with trailing '/' for gitignore-style matching

    Examples:
        >>> to_dir_pattern('src/components')
        'src/components/'
        >>> to_dir_pattern('src/components/')
        'src/components/'  # already has trailing slash
    """
    if rel_path and not rel_path.endswith('/'):
        return rel_path + '/'
    return rel_path


def is_descendant(path: Path, ancestor: Path, strict: bool = True) -> bool:
    """Check if path is a descendant of ancestor.

    Args:
        path: Path to check
        ancestor: Potential ancestor path
        strict: If True, path must be different from ancestor.
                If False, path == ancestor returns True.

    Returns:
        True if path is under ancestor

    Examples:
        >>> is_descendant(Path('C:/project/src'), Path('C:/project'))
        True
        >>> is_descendant(Path('C:/project'), Path('C:/project'))
        False  # strict=True
        >>> is_descendant(Path('C:/project'), Path('C:/project'), strict=False)
        True
    """
    path_str = str(path)
    ancestor_str = str(ancestor)
    if strict:
        return (
            len(path_str) > len(ancestor_str)
            and path_str.startswith(ancestor_str + os.sep)
        )
    return path_str == ancestor_str or path_str.startswith(
        ancestor_str + os.sep
    )


def is_ancestor(path: Path, descendant: Path, strict: bool = True) -> bool:
    """Check if path is an ancestor of descendant.

    Args:
        path: Potential ancestor path
        descendant: Path to check
        strict: If True, paths must be different.
                If False, path == descendant returns True.

    Returns:
        True if path contains descendant

    Examples:
        >>> is_ancestor(Path('C:/project'), Path('C:/project/src'))
        True
        >>> is_ancestor(Path('C:/project'), Path('C:/project'))
        False  # strict=True
    """
    return is_descendant(descendant, path, strict)


def relative_to_safe(path: Path, root: Path) -> Optional[Path]:
    """Get relative path or None if not relative.

    Useful when you need the Path object, not just a string.

    Args:
        path: Path to convert
        root: Root directory to make relative to

    Returns:
        Relative Path object, or None if not relative

    Examples:
        >>> relative_to_safe(Path('C:/project/src'), Path('C:/project'))
        PosixPath('src')
        >>> relative_to_safe(Path('D:/other'), Path('C:/project'))
        None
    """
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def to_absolute_paths(paths: list, base_root: Path) -> set[Path]:
    """Convert list of path strings to absolute Path set.

    Resolves relative paths against base_root. Absolute paths pass through.
    Replaces 3 identical nested to_absolute() functions that were cloned
    in local_mount_config.py, config.py (SiblingMount), and config.py (ScopeDockerConfig).

    Args:
        paths: List of path strings (relative POSIX or absolute)
        base_root: Base directory for resolving relative paths

    Returns:
        Set of absolute Path objects
    """
    result = set()
    for p in paths:
        path = Path(p)
        if path.is_absolute():
            result.add(path)
        else:
            result.add(base_root / path)
    return result


def normalize_posix(path_str: str) -> str:
    """Normalize path string to posix-style (forward slashes).

    Args:
        path_str: Path string that may have backslashes

    Returns:
        Path string with forward slashes

    Examples:
        >>> normalize_posix('src\\\\components\\\\App.tsx')
        'src/components/App.tsx'
        >>> normalize_posix('src/components/App.tsx')
        'src/components/App.tsx'
    """
    return path_str.replace('\\', '/')
