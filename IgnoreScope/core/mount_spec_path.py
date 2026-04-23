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
from typing import Literal, Optional

import pathspec

from ..utils.paths import is_descendant, to_relative_posix


@dataclass
class MountSpecPath:
    """A single mount root with ordered gitignore-style mask/unmask patterns.

    Attributes:
        mount_root: Absolute path to the mount root. Interpreted as a host path
            when ``host_path`` is set or when ``delivery == "bind"``; interpreted
            as a container-logical path when ``host_path`` is None (container-only
            specs produced by the Scope Config "Make Folder" family).
        patterns: Ordered list of gitignore-style patterns, relative to mount_root.
        delivery: How content reaches the container.
            "bind"     — L1 bind mount (default, host is live-linked).
            "detached" — docker cp snapshot at container create; no host link.
            "volume"   — named Docker volume (L_volume); survives ordinary update.
        host_path: Optional host-side source for content. None => container-only
            (no host read side). Required when ``delivery == "bind"``.
        content_seed: Controls initial container-side content for non-bind specs.
            "tree"   — whole subtree cp-walked from host (Phase 1 behavior).
            "folder" — only the mount root is mkdir'd; content filled via
                pushed_files or inside-container writes.
        preserve_on_update: If True, the update lifecycle cp's this spec's
            container contents to a host tmp staging area across recreate.
            Only valid when ``delivery == "detached"`` and
            ``content_seed == "folder"``; tree-seed specs re-read from host, so
            the flag is meaningless there. ``delivery == "volume"`` survives
            update natively without needing this flag.
        owner: Provenance tag for the spec.
            "user"               — user-authored spec (default).
            "extension:{name}"   — synthesized by an extension at hierarchy-
                                   compute time (e.g. "extension:claude").
            Load-bearing for volume naming, GUI read-only RMB gating, and
            Scope Config header signal derivation. Round-trippable as a flat
            string so the spec stays self-describing (no sibling lookup into
            ExtensionConfig to resolve the extension name).
    """

    mount_root: Path = field(default_factory=Path)
    patterns: list[str] = field(default_factory=list)
    delivery: Literal["bind", "detached", "volume"] = "bind"
    host_path: Optional[Path] = None
    content_seed: Literal["tree", "folder"] = "tree"
    preserve_on_update: bool = False
    owner: str = "user"

    def __post_init__(self) -> None:
        """For bind specs, default host_path to mount_root.

        Phase 2 and earlier treated mount_root as the host path. Phase 3 split
        them conceptually (to support container-only specs) but the bind case
        always has host_path == mount_root by definition — auto-fill keeps the
        Phase 2 construction shape valid.
        """
        if self.delivery == "bind" and self.host_path is None:
            self.host_path = self.mount_root

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

    def get_stencil_paths(self) -> set[Path]:
        """Derive stencil (structural intermediate) paths from pattern structure.

        For each exception pattern, walks UP through path components to find
        the nearest covering deny pattern. All intermediate paths between the
        deny and the exception are stencils — their content is masked but their
        directory structure must exist for the container to reach revealed content.
        These intermediates present as `visibility="virtual"` at runtime.

        Used as cross-reference against config-query stencil detection.
        Discrepancies indicate malformed patterns or detection bugs.

        Returns:
            Set of absolute paths that should have virtual visibility.
        """
        stencils: set[Path] = set()
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
                        stencils.add(self.mount_root / mid)
                    break
        return stencils

    # --- Validation ---

    def validate(self) -> list[str]:
        """Validate pattern + delivery-field cross-constraint consistency."""
        errors = []

        if not self.mount_root:
            errors.append("mount_root is empty")

        if self.delivery not in ("bind", "detached", "volume"):
            errors.append(
                f"delivery must be 'bind', 'detached', or 'volume', "
                f"got {self.delivery!r}"
            )

        if self.content_seed not in ("tree", "folder"):
            errors.append(
                f"content_seed must be 'tree' or 'folder', "
                f"got {self.content_seed!r}"
            )

        # host_path=None is valid only for isolation deliveries (container-only).
        if self.host_path is None and self.delivery == "bind":
            errors.append(
                "host_path is required when delivery='bind' (bind mounts "
                "need a host source)"
            )

        # Container-only specs must be folder-seed — tree-seed needs a host
        # subtree to cp-walk, which container-only specs don't have.
        if self.host_path is None and self.delivery != "bind" and self.content_seed != "folder":
            errors.append(
                "container-only specs (host_path=None) require "
                "content_seed='folder'; no host subtree to cp-walk for tree-seed"
            )

        # Folder-seed specs cannot carry mask/reveal patterns — there's no
        # cp walk to mask/reveal over.
        if self.content_seed == "folder" and self.patterns:
            errors.append(
                f"folder-seed specs disallow mask/reveal patterns; "
                f"got {len(self.patterns)} pattern(s) on content_seed='folder'"
            )

        # delivery='volume' requires folder seeding — no tree-seeding into a
        # named volume at this phase.
        if self.delivery == "volume" and self.content_seed != "folder":
            errors.append(
                "delivery='volume' requires content_seed='folder'; "
                f"got content_seed={self.content_seed!r}"
            )

        # preserve_on_update is only meaningful on detached+folder specs.
        # Tree-seed specs re-read from host on update anyway; volume specs
        # survive update natively.
        if self.preserve_on_update and not (
            self.delivery == "detached" and self.content_seed == "folder"
        ):
            errors.append(
                "preserve_on_update=True is only valid when "
                "delivery='detached' and content_seed='folder'; "
                f"got delivery={self.delivery!r}, "
                f"content_seed={self.content_seed!r}"
            )

        # owner must be "user" or "extension:{name}" (non-empty name).
        if self.owner != "user":
            if not self.owner.startswith("extension:"):
                errors.append(
                    f"owner must be 'user' or 'extension:{{name}}'; "
                    f"got {self.owner!r}"
                )
            elif not self.owner[len("extension:"):]:
                errors.append(
                    "owner='extension:' is missing extension name; "
                    "expected 'extension:{name}'"
                )

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

        Non-default fields (host_path, content_seed, preserve_on_update,
        owner) are emitted only when they differ from defaults, so legacy
        Phase 1/2 specs round-trip to the same JSON they came from.

        Args:
            host_project_root: Base path for relative conversion.
        """
        rel_root = to_relative_posix(self.mount_root, host_project_root)
        result: dict = {
            "mount_root": rel_root,
            "patterns": list(self.patterns),
            "delivery": self.delivery,
        }
        # Omit host_path from JSON when it's the implicit default for bind
        # (host_path == mount_root) — preserves Phase 1/2 JSON shape.
        emit_host_path = self.host_path is not None and not (
            self.delivery == "bind" and self.host_path == self.mount_root
        )
        if emit_host_path:
            result["host_path"] = to_relative_posix(self.host_path, host_project_root)
        if self.content_seed != "tree":
            result["content_seed"] = self.content_seed
        if self.preserve_on_update:
            result["preserve_on_update"] = True
        if self.owner != "user":
            result["owner"] = self.owner
        return result

    @classmethod
    def from_dict(cls, data: dict, host_project_root: Path) -> MountSpecPath:
        """Deserialize from dict.

        Args:
            data: Dict with 'mount_root' (relative path), 'patterns' (list),
                and optional 'delivery' ('bind' default for legacy configs),
                'host_path' (None default — container-only), 'content_seed'
                ('tree' default), 'preserve_on_update' (False default),
                'owner' ('user' default — user-authored spec).
            host_project_root: Base path for resolving relative mount_root.
        """
        raw_root = data.get("mount_root", ".")
        patterns = list(data.get("patterns", []))
        delivery = data.get("delivery", "bind")

        raw_host = data.get("host_path")
        host_path: Optional[Path] = (
            (host_project_root / raw_host).resolve() if raw_host else None
        )

        # Container-only specs (no host_path + non-bind delivery) keep
        # mount_root as the container-side absolute path as-written.
        # Resolving against host_project_root would prepend a host drive
        # letter on Windows and break exact-match lookup.
        if raw_host is None and delivery != "bind":
            mount_root = Path(raw_root)
        else:
            mount_root = (host_project_root / raw_root).resolve()
        content_seed = data.get("content_seed", "tree")
        preserve_on_update = data.get("preserve_on_update", False)
        owner = data.get("owner", "user")

        return cls(
            mount_root=mount_root,
            patterns=patterns,
            delivery=delivery,
            host_path=host_path,
            content_seed=content_seed,
            preserve_on_update=preserve_on_update,
            owner=owner,
        )

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
