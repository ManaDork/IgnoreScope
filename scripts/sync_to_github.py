"""Sync publishable source files from Perforce project to GitHub mirror directory.

Usage:
    python scripts/sync_to_github.py
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pathspec

# Resolve paths relative to this script's location (no hardcoded user paths)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MIRROR_ROOT = PROJECT_ROOT.parent.parent / "GitHubPublishing" / "IgnoreScopeDocker"

# Directories / files to include (relative to project root)
INCLUDE_DIRS = ["IgnoreScope", "tests"]
INCLUDE_FILES = ["pyproject.toml", "uv.lock", ".gitignore", "LICENSE", "README.md", "USAGE.md"]

# Patterns always excluded (never copied to the mirror)
ALWAYS_EXCLUDE = {
    ".claude",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "Icons",
    "__pycache__",
    ".mcp.json",
    "scripts",
    "debug_output_visible_lite.txt",
    ".git",
}


def load_gitignore_spec(project_root: Path) -> pathspec.PathSpec | None:
    """Load .gitignore patterns from project root if present."""
    gitignore = project_root / ".gitignore"
    if gitignore.is_file():
        return pathspec.PathSpec.from_lines("gitwildmatch", gitignore.read_text().splitlines())
    return None


def should_exclude(rel_path: Path, spec: pathspec.PathSpec | None) -> bool:
    """Check if a relative path should be excluded from sync."""
    parts = rel_path.parts

    # Check against always-excluded names
    for part in parts:
        if part in ALWAYS_EXCLUDE:
            return True

    # Skip .pyc files and egg-info dirs
    if rel_path.suffix == ".pyc":
        return True
    for part in parts:
        if part.endswith(".egg-info"):
            return True

    # Check against .gitignore patterns
    if spec and spec.match_file(str(rel_path.as_posix())):
        return True

    return False


def collect_source_files(project_root: Path, spec: pathspec.PathSpec | None) -> dict[str, Path]:
    """Collect all files to sync, keyed by their relative path string."""
    files: dict[str, Path] = {}

    # Collect included directories
    for dir_name in INCLUDE_DIRS:
        dir_path = project_root / dir_name
        if not dir_path.is_dir():
            continue
        for file_path in dir_path.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(project_root)
            if not should_exclude(rel, spec):
                files[str(rel.as_posix())] = file_path

    # Collect included top-level files
    for file_name in INCLUDE_FILES:
        file_path = project_root / file_name
        if file_path.is_file():
            rel = file_path.relative_to(project_root)
            if not should_exclude(rel, spec):
                files[str(rel.as_posix())] = file_path

    return files


def collect_mirror_files(mirror_root: Path) -> dict[str, Path]:
    """Collect all existing files in the mirror (excluding .git and .github)."""
    files: dict[str, Path] = {}
    if not mirror_root.is_dir():
        return files

    for file_path in mirror_root.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(mirror_root)
        # Preserve .git/ and .github/ — managed separately
        if rel.parts[0] in (".git", ".github"):
            continue
        files[str(rel.as_posix())] = file_path

    return files


def sync(project_root: Path, mirror_root: Path) -> None:
    """Perform a clean sync from project to mirror."""
    spec = load_gitignore_spec(project_root)
    source_files = collect_source_files(project_root, spec)
    mirror_files = collect_mirror_files(mirror_root)

    copied = []
    deleted = []

    # Copy new and updated files
    for rel_posix, src_path in sorted(source_files.items()):
        dst_path = mirror_root / rel_posix
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Only copy if source is newer or file doesn't exist in mirror
        if not dst_path.exists() or src_path.stat().st_mtime > dst_path.stat().st_mtime:
            # Clear read-only flag on destination (P4 marks unedited files read-only)
            if dst_path.exists():
                dst_path.chmod(stat.S_IWRITE | stat.S_IREAD)
            shutil.copy2(src_path, dst_path)
            # Ensure the copy is writable in the mirror
            dst_path.chmod(stat.S_IWRITE | stat.S_IREAD)
            copied.append(rel_posix)

    # Delete files from mirror that no longer exist in source
    for rel_posix, dst_path in sorted(mirror_files.items()):
        if rel_posix not in source_files:
            dst_path.unlink()
            deleted.append(rel_posix)

    # Clean up empty directories in mirror (excluding .git/.github)
    for dirpath, dirnames, filenames in os.walk(mirror_root, topdown=False):
        dir_p = Path(dirpath)
        if dir_p == mirror_root:
            continue
        rel = dir_p.relative_to(mirror_root)
        if rel.parts[0] in (".git", ".github"):
            continue
        if not any(dir_p.iterdir()):
            dir_p.rmdir()

    # Summary
    print(f"Sync complete: {project_root} -> {mirror_root}")
    print(f"  Copied:  {len(copied)} file(s)")
    for f in copied:
        print(f"    + {f}")
    print(f"  Deleted: {len(deleted)} file(s)")
    for f in deleted:
        print(f"    - {f}")
    print(f"  Total in mirror: {len(source_files)} file(s)")


def main() -> None:
    if not PROJECT_ROOT.is_dir():
        print(f"ERROR: Project root not found: {PROJECT_ROOT}")
        raise SystemExit(1)

    MIRROR_ROOT.mkdir(parents=True, exist_ok=True)
    sync(PROJECT_ROOT, MIRROR_ROOT)


if __name__ == "__main__":
    main()
