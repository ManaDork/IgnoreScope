"""Mount-scoped pathspec configuration for container filesystem visibility.

Each MountSpecPath represents a single bind mount with an ordered list of
gitignore-style patterns controlling which subdirectories are masked or
unmasked within that mount.

Pattern syntax (gitignore native):
    "vendor/"            - mask (deny) the vendor directory
    "!vendor/public/"    - unmask (exception) vendor/public
    "vendor/public/tmp/" - re-mask vendor/public/tmp

Pattern order matters: later patterns override earlier ones (last-match-wins).
Non-negated patterns produce Docker named mask volumes.
Negated (!) patterns produce Docker bind mount punch-throughs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from ..utils.paths import is_descendant, to_relative_posix


@dataclass
class MountSpecPath:
    """A single mount root with ordered gitignore-style mask/unmask patterns.

    Attributes:
        mount_root: Absolute path to the bind mount root on the host.
        patterns: Ordered list of gitignore-style patterns, relative to mount_root.
    """

    mount_root: Path = field(default_factory=Path)
    patterns: list[str] = field(default_factory=list)

    # --- Pattern CRUD ---

    def add_pattern(self, pattern: str, index: int | None = None) -> bool:
        """Add a pattern to the list. Returns True if added, False if duplicate.

        Args:
            pattern: Gitignore-style pattern string.
            index: Insert position. None = append at end.
        """
        pattern = pattern.strip()
        if not pattern or pattern in self.patterns:
            return False
        pos = index if index is not None else len(self.patterns)
        self.patterns.insert(pos, pattern)
        self._invalidate_cache()
        return True

    def remove_pattern(self, pattern: str) -> bool:
        """Remove a pattern from the list. Returns True if removed."""
        if pattern not in self.patterns:
            return False
        self.patterns.remove(pattern)
        self._invalidate_cache()
        return True

    def move_pattern(self, from_index: int, to_index: int) -> bool:
        """Move a pattern from one position to another. Returns True if moved."""
        if from_index == to_index:
            return False
        if not (0 <= from_index < len(self.patterns)):
            return False
        if not (0 <= to_index < len(self.patterns)):
            return False
        pattern = self.patterns.pop(from_index)
        self.patterns.insert(to_index, pattern)
        self._invalidate_cache()
        return True

    # --- Query Methods ---

    def get_masked_paths(self) -> set[Path]:
        """Extract absolute paths of all non-negated (mask) patterns."""
        result = set()
        for p in self.patterns:
            if not p.startswith("!"):
                folder = p.rstrip("/")
                if folder:
                    result.add(self.mount_root / folder)
        return result

    def get_revealed_paths(self) -> set[Path]:
        """Extract absolute paths of all negated (unmask/reveal) patterns."""
        result = set()
        for p in self.patterns:
            if p.startswith("!"):
                folder = p[1:].rstrip("/")
                if folder:
                    result.add(self.mount_root / folder)
        return result

    def is_masked(self, path: Path) -> bool:
        """Check if path is masked by patterns (matched by deny, not overridden by exception).

        Uses pathspec for proper gitignore evaluation with last-match-wins.
        """
        rel = self._to_relative(path)
        if rel is None:
            return False
        return self._get_deny_spec().match_file(rel)

    def is_unmasked(self, path: Path) -> bool:
        """Check if path is unmasked (matched by an exception pattern).

        A path is unmasked if the full pattern list (with exceptions) does NOT
        match it, but it would match the deny-only patterns.
        """
        rel = self._to_relative(path)
        if rel is None:
            return False
        matched_by_deny = self._get_deny_spec().match_file(rel)
        matched_by_full = self._get_full_spec().match_file(rel)
        return matched_by_deny and not matched_by_full

    def has_exception_descendant(self, path: Path) -> bool:
        """Check if any exception pattern exists under this path.

        Scans pattern strings directly — no tree walk, no filesystem access.
        Only works for paths within this mount (returns False for paths
        above mount_root).

        Args:
            path: Absolute path to check.

        Returns:
            True if any negated pattern is a descendant of this path.
        """
        rel = self._to_relative(path)
        if rel is None:
            return False
        rel_prefix = rel.rstrip("/")
        for pattern in self.patterns:
            if pattern.startswith("!"):
                exc_folder = pattern[1:].rstrip("/")
                if exc_folder.startswith(rel_prefix + "/"):
                    return True
        return False

    def get_virtual_paths(self) -> set[Path]:
        """Derive virtual paths from pattern structure (inverse pathspec).

        For each exception pattern, walks UP through path components to find
        the nearest covering deny pattern. All intermediate paths between the
        deny and the exception are virtual — their content is masked but their
        directory structure must exist for the container to reach revealed content.

        Used as cross-reference against config-query virtual detection.
        Discrepancies indicate malformed patterns or detection bugs.

        Returns:
            Set of absolute paths that should have virtual visibility.
        """
        virtual: set[Path] = set()
        deny_set = {p.rstrip("/") for p in self.patterns if not p.startswith("!")}
        for pattern in self.patterns:
            if not pattern.startswith("!"):
                continue
            exc = pattern[1:].rstrip("/")
            parts = exc.split("/")
            # Walk UP from exception to find covering deny
            for i in range(len(parts) - 1, 0, -1):
                ancestor = "/".join(parts[:i])
                if ancestor in deny_set:
                    # All intermediates from deny (inclusive) to exception (exclusive)
                    for j in range(i, len(parts)):
                        mid = "/".join(parts[:j])
                        virtual.add(self.mount_root / mid)
                    break
        return virtual

    # --- Validation ---

    def validate(self) -> list[str]:
        """Validate pattern consistency. Returns list of error strings."""
        errors = []

        if not self.mount_root:
            errors.append("mount_root is empty")

        for i, p in enumerate(self.patterns):
            stripped = p.lstrip("!")
            if not stripped:
                errors.append(f"Pattern at index {i} is empty after prefix removal")
                continue

            # Exception pattern without a preceding deny
            if p.startswith("!"):
                exception_folder = stripped.rstrip("/")
                has_parent_deny = False
                for earlier in self.patterns[:i]:
                    if not earlier.startswith("!"):
                        deny_folder = earlier.rstrip("/")
                        deny_path = Path(deny_folder)
                        exc_path = Path(exception_folder)
                        if exc_path == deny_path or is_descendant(exc_path, deny_path):
                            has_parent_deny = True
                            break
                if not has_parent_deny:
                    errors.append(
                        f"Exception pattern '{p}' at index {i} has no preceding "
                        f"deny pattern covering it"
                    )

        return errors

    # --- Mount Overlap Validation (class-level) ---

    @staticmethod
    def validate_no_overlap(specs: list[MountSpecPath]) -> list[str]:
        """Check that no mount roots overlap. Returns error strings.

        Hard block: a mount cannot be a descendant of another mount.
        """
        errors = []
        roots = [(i, s.mount_root) for i, s in enumerate(specs)]
        for i, root_a in roots:
            for j, root_b in roots:
                if i >= j:
                    continue
                if root_a == root_b:
                    errors.append(
                        f"Duplicate mount root: {root_a}"
                    )
                elif is_descendant(root_b, root_a):
                    errors.append(
                        f"Mount '{root_b}' is inside existing mount '{root_a}'"
                    )
                elif is_descendant(root_a, root_b):
                    errors.append(
                        f"Mount '{root_a}' is inside existing mount '{root_b}'"
                    )
        return errors

    # --- Serialization ---

    def to_dict(self, host_project_root: Path) -> dict:
        """Serialize to dict with relative paths.

        Args:
            host_project_root: Base path for relative conversion.
        """
        rel_root = to_relative_posix(self.mount_root, host_project_root)
        return {
            "mount_root": rel_root,
            "patterns": list(self.patterns),
        }

    @classmethod
    def from_dict(cls, data: dict, host_project_root: Path) -> MountSpecPath:
        """Deserialize from dict.

        Args:
            data: Dict with 'mount_root' (relative path) and 'patterns' (list).
            host_project_root: Base path for resolving relative mount_root.
        """
        raw_root = data.get("mount_root", ".")
        mount_root = (host_project_root / raw_root).resolve()
        patterns = list(data.get("patterns", []))
        return cls(mount_root=mount_root, patterns=patterns)

    # --- Internal ---

    _cached_deny_spec: pathspec.PathSpec | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _cached_full_spec: pathspec.PathSpec | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def _invalidate_cache(self) -> None:
        """Clear cached pathspec objects after pattern changes."""
        self._cached_deny_spec = None
        self._cached_full_spec = None

    def _get_deny_spec(self) -> pathspec.PathSpec:
        """Get pathspec for deny-only patterns (negations stripped)."""
        if self._cached_deny_spec is None:
            deny_only = [p for p in self.patterns if not p.startswith("!")]
            self._cached_deny_spec = pathspec.PathSpec.from_lines(
                "gitignore", deny_only
            )
        return self._cached_deny_spec

    def _get_full_spec(self) -> pathspec.PathSpec:
        """Get pathspec for full pattern list (deny + exceptions)."""
        if self._cached_full_spec is None:
            self._cached_full_spec = pathspec.PathSpec.from_lines(
                "gitignore", self.patterns
            )
        return self._cached_full_spec

    def _to_relative(self, path: Path) -> str | None:
        """Convert absolute path to relative string for pathspec matching.

        Appends trailing '/' so directory patterns (e.g. 'vendor/') match
        the directory path itself, not just its children.
        """
        try:
            rel = path.relative_to(self.mount_root)
            result = str(rel).replace("\\", "/")
            if result and not result.endswith("/"):
                result += "/"
            return result
        except ValueError:
            return None
