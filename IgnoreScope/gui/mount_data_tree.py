"""Runtime State Host for mount/mask/reveal configuration.

MountDataTree: Single shared data model backing both LocalHostView and ScopeView.
Stores raw configuration sets (mounts, masked, revealed, pushed_files) and
delegates all state computation to CORE via apply_node_states_from_scope().
Exposes frozen NodeState instances to views via get_node_state().

Two-layer pattern:
  Mutable layer: _mounts, _masked, _revealed, _pushed_files (user selections)
  Computed layer: _states dict[Path, NodeState] (CORE output, rebuilt on mutation)

Replaces: archive mount_data_tree.py (~660 lines) with CORE-wired version.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional

logger = logging.getLogger(__name__)

from PyQt6.QtCore import QObject, pyqtSignal

from ..core.node_state import (
    NodeState,
    apply_node_states_from_scope,
)
from ..utils.paths import is_descendant


# ── Enums & Data Classes ─────────────────────────────────────────────

class NodeSource(Enum):
    """Where a tree node originates."""
    PROJECT = "project"
    SIBLING = "sibling"
    STENCIL = "stencil"


# Windows reserved device names that can crash on property access
WINDOWS_RESERVED_NAMES = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
})


def _is_windows_reserved_name(name: str) -> bool:
    """Check if filename is a Windows reserved device name."""
    base_name = name.upper().split('.')[0]
    return base_name in WINDOWS_RESERVED_NAMES


@dataclass
class MountDataNode:
    """Unified tree node for all panels.

    Covers project files, sibling files, and stencil entries
    (synthetic nodes — UX "virtual" — not on disk).
    """
    # Class-level filter flag — set by MountDataTree before triggering loads
    show_hidden: ClassVar[bool] = False

    path: Path
    parent: Optional[MountDataNode] = None
    children: list[MountDataNode] = field(default_factory=list)
    children_loaded: bool = False
    is_file: bool = False
    is_stencil_node: bool = False
    stencil_tier: str = "mirrored"        # "mirrored" | "volume" | "auth"
    source: NodeSource = NodeSource.PROJECT
    container_path: str = ""              # Sibling root container target path

    @property
    def name(self) -> str:
        return self.path.name or str(self.path)

    @property
    def row(self) -> int:
        if self.parent is not None:
            try:
                return self.parent.children.index(self)
            except ValueError:
                return 0
        return 0

    def load_children(self, folders_only: bool = False) -> None:
        """Load children from filesystem (lazy loading)."""
        if self.children_loaded or self.is_file or self.is_stencil_node:
            return

        self.children = []
        try:
            # os.scandir caches is_file from FindNextFileW on Windows —
            # no separate stat() syscall per entry (3-5x faster on large dirs).
            filtered: list[tuple[Path, bool]] = []
            with os.scandir(self.path) as scan_it:
                for dir_entry in scan_it:
                    if not MountDataNode.show_hidden and dir_entry.name.startswith('.'):
                        continue
                    if _is_windows_reserved_name(dir_entry.name):
                        continue
                    try:
                        is_file = dir_entry.is_file()
                    except OSError:
                        continue
                    if folders_only and is_file:
                        continue
                    filtered.append((Path(dir_entry.path), is_file))

            # Sort: folders first, then alphabetical
            filtered.sort(key=lambda pair: (pair[1], pair[0].name.lower()))

            for entry_path, is_file in filtered:
                child = MountDataNode(
                    path=entry_path,
                    parent=self,
                    is_file=is_file,
                    source=self.source,
                )
                self.children.append(child)
        except PermissionError:
            logger.debug("Permission denied reading directory: %s", self.path)

        self.children_loaded = True


# ── Default NodeState (all False, visibility="hidden") ────────────────

_DEFAULT_NODE_STATE = NodeState()


# ── MountDataTree ─────────────────────────────────────────────────────

class MountDataTree(QObject):
    """Runtime State Host shared by LocalHostView and ScopeView.

    Two-layer pattern:
      Mutable layer: _mounts, _masked, _revealed, _pushed_files (raw user selections)
      Computed layer: _states dict[Path, NodeState] (frozen CORE output, rebuilt on mutation)

    Toggle operations mutate raw sets -> call _recompute_states() -> emit stateChanged.
    Views read computed state via get_node_state(path).
    """

    stateChanged = pyqtSignal()
    structureChanged = pyqtSignal()
    aboutToMutate = pyqtSignal()  # Emitted before mount_specs mutations (undo snapshot)
    mountSpecsChanged = pyqtSignal()  # Emitted after any mount_specs mutation

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._root_node: Optional[MountDataNode] = None
        self._host_project_root: Optional[Path] = None
        self._current_scope: str = ""

        # Mount specifications (primary mutable state)
        self._mount_specs: list = []  # list[MountSpecPath]
        self._pushed_files: set[Path] = set()
        self._container_files: set[Path] = set()
        self._mirrored: bool = True
        self._container_root: str = ""

        # Computed state (CORE output)
        self._states: dict[Path, NodeState] = {}

        # Sibling and stencil subtrees
        self._sibling_nodes: list[MountDataNode] = []
        self._stencil_nodes: list[MountDataNode] = []

        # Extension configs (not GUI widgets — carried forward through build_config)
        self._extensions: list = []

        # Display filter
        self._show_hidden: bool = False

        # Batch mode (defers stateChanged)
        self._batch_mode: bool = False
        self._batch_changed: bool = False

    # ── Display Filters ──────────────────────────────────────────

    @property
    def show_hidden(self) -> bool:
        return self._show_hidden

    @show_hidden.setter
    def show_hidden(self, value: bool) -> None:
        if self._show_hidden != value:
            self._show_hidden = value
            MountDataNode.show_hidden = value
            self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        """Rebuild tree with current filter settings."""
        if self._root_node:
            self._root_node.children_loaded = False
            self._root_node.children = []
            self._root_node.load_children()  # Reload now — Qt won't re-fetch expanded nodes
            self.structureChanged.emit()

    # ── Batch Mode ────────────────────────────────────────────────

    def begin_batch(self) -> None:
        """Begin batch mode — suppresses stateChanged until end_batch()."""
        self._batch_mode = True
        self._batch_changed = False

    def end_batch(self, *, emit: bool = True) -> None:
        """End batch mode. Emits deferred stateChanged unless emit=False."""
        self._batch_mode = False
        if self._batch_changed and emit:
            self._batch_changed = False
            self.stateChanged.emit()
        self._batch_changed = False

    def _emit_state_changed(self) -> None:
        """Emit stateChanged respecting batch mode."""
        if self._batch_mode:
            self._batch_changed = True
        else:
            self.stateChanged.emit()

    # ── State Recomputation (CORE Wiring) ─────────────────────────

    def _recompute_states(self) -> None:
        """Rebuild _states from mount_specs via CORE apply_node_states_from_scope().

        Path inclusion: compute_mirrored_intermediate_paths() adds structural
        paths (above-mount and within-mount intermediates) to the path set.
        These paths must exist in all_paths for CORE to evaluate them.

        Stencil detection: handled by CORE config-native queries (no tree walk).
        The hierarchy call is for path INCLUSION only, not stencil detection.

        Extension isolation paths flow through the same pipeline as user specs:
        ``ExtensionConfig.synthesize_mount_specs()`` is merged into the
        ``LocalMountConfig`` mount_specs (Task 1.9 unified-synth payoff on the
        GUI side). CORE's ``compute_node_state`` derives
        ``container_only=True`` from each synthesized spec's ``host_path=None``
        and routes visibility to ``"virtual"`` without any GUI direct-write.
        """
        from ..core.local_mount_config import LocalMountConfig

        synthesized_specs: list = []
        for ext in self._extensions:
            synthesized_specs.extend(ext.synthesize_mount_specs())

        config = LocalMountConfig(
            mount_specs=list(self._mount_specs) + synthesized_specs,
            pushed_files=self._pushed_files,
            mirrored=self._mirrored,
        )

        # Path inclusion: structural intermediates not in lazy-loaded tree
        if self._mirrored and self._host_project_root:
            from ..core.hierarchy import compute_mirrored_intermediate_paths
            mirrored_intermediates = compute_mirrored_intermediate_paths(
                config.masked, config.revealed, config.mounts,
                ceiling=self._host_project_root.parent,
            )
        else:
            mirrored_intermediates = set()

        all_paths = self._collect_all_paths(mirrored_intermediates)
        # Extension-synth mount_roots must be present in all_paths so CORE
        # computes a state for each (they never appear in the host tree walk).
        for spec in synthesized_specs:
            all_paths.add(spec.mount_root)
        self._states = apply_node_states_from_scope(config, all_paths)

        self._emit_state_changed()

    def _collect_all_paths(self, mirrored_intermediates: set[Path] | None = None) -> set[Path]:
        """Collect all paths that need state computation.

        Includes loaded tree nodes + all config set paths (config paths
        may reference nodes not yet lazy-loaded in the tree) + pre-computed
        mirrored intermediate host paths.

        Args:
            mirrored_intermediates: Pre-computed mirrored intermediate paths
                from _recompute_states(). None treated as empty.
        """
        paths: set[Path] = set()
        # Walk loaded tree nodes (root walk covers siblings — they're
        # appended to root_node.children in load_config)
        if self._root_node:
            self._collect_loaded_paths(self._root_node, paths)
        # Union with all config paths from mount_specs
        for ms in self._mount_specs:
            paths.add(ms.mount_root)
            paths.update(ms.get_masked_paths())
            paths.update(ms.get_revealed_paths())
        paths.update(self._pushed_files)
        # Include ancestor folders of pushed files up to their respective roots
        # (project root for project files, sibling root for sibling files)
        # so Stage 3 can set has_pushed_descendant=True on them
        all_roots: list[Path] = []
        if self._host_project_root:
            all_roots.append(self._host_project_root)
        all_roots.extend(sib.path for sib in self._sibling_nodes)

        for pf in self._pushed_files:
            # Find which root this pushed file belongs to
            root = None
            for r in all_roots:
                if is_descendant(pf, r, strict=False):
                    root = r
                    break
            if root is None:
                continue
            current = pf.parent
            while current != root and is_descendant(current, root):
                paths.add(current)
                current = current.parent
        # Include pre-computed mirrored intermediate host paths
        if mirrored_intermediates:
            paths.update(mirrored_intermediates)
        return paths

    def _collect_loaded_paths(self, node: MountDataNode, out: set[Path]) -> None:
        """Recursively collect paths from loaded tree nodes."""
        out.add(node.path)
        if node.children_loaded:
            for child in node.children:
                self._collect_loaded_paths(child, out)

    def request_recompute(self) -> None:
        """Public trigger for state recomputation after lazy-load expansion."""
        self._recompute_states()

    # ── Project Root ──────────────────────────────────────────────

    @property
    def host_project_root(self) -> Optional[Path]:
        return self._host_project_root

    @property
    def current_scope(self) -> str:
        return self._current_scope

    @current_scope.setter
    def current_scope(self, value: str) -> None:
        self._current_scope = value

    @property
    def root_node(self) -> Optional[MountDataNode]:
        return self._root_node

    def unified_mount_specs(self) -> list:
        """Return the unified mount_specs list: user specs + extension-synthesized.

        Matches the list ``compute_container_hierarchy(extensions=...)`` consumes
        (Phase 1 unification). Each call synthesizes fresh — cheap (small lists).
        Used by the Scope Config Tree header's 3-signal resolver (Phase 3).
        """
        unified = list(self._mount_specs)
        for ext in self._extensions:
            unified.extend(ext.synthesize_mount_specs())
        return unified

    def set_host_project_root(self, host_project_root: Path) -> None:
        """Phase 2: SCAN — raw filesystem tree, no states.

        Loads the directory tree from the host filesystem. Does NOT
        compute NodeState — that happens in load_config() (Phase 3→4).
        Views see _DEFAULT_NODE_STATE (all hidden) via get_node_state().
        """
        self._host_project_root = host_project_root.resolve()
        self._root_node = MountDataNode(path=self._host_project_root)
        self._root_node.load_children(folders_only=False)
        self._container_root = ""
        self._mount_specs.clear()
        self._pushed_files.clear()
        self._container_files.clear()
        self._sibling_nodes.clear()
        self._stencil_nodes.clear()
        self._states.clear()

    # ── State Access ──────────────────────────────────────────────

    def get_node_state(self, path: Path) -> NodeState:
        """Get CORE-computed frozen NodeState for a path.

        Returns default (all False, hidden) if path has no computed state.
        """
        return self._states.get(path, _DEFAULT_NODE_STATE)

    # ── Raw Set Accessors (read-only views) ───────────────────────

    @property
    def mounts(self) -> frozenset[Path]:
        """Active bind mount paths (for config save, external queries)."""
        return frozenset(ms.mount_root for ms in self._mount_specs)

    @property
    def masked(self) -> frozenset[Path]:
        """Active mask volume paths."""
        result: set[Path] = set()
        for ms in self._mount_specs:
            result.update(ms.get_masked_paths())
        return frozenset(result)

    @property
    def revealed(self) -> frozenset[Path]:
        """Active punch-through paths."""
        result: set[Path] = set()
        for ms in self._mount_specs:
            result.update(ms.get_revealed_paths())
        return frozenset(result)

    @property
    def pushed_files(self) -> frozenset[Path]:
        """Files currently pushed to container."""
        return frozenset(self._pushed_files)

    @property
    def mirrored(self) -> bool:
        """Whether Stage 2 mirrored detection is enabled."""
        return self._mirrored

    @mirrored.setter
    def mirrored(self, value: bool) -> None:
        if self._mirrored != value:
            self._mirrored = value
            self._recompute_states()

    @property
    def container_root(self) -> str:
        return self._container_root

    @container_root.setter
    def container_root(self, value: str) -> None:
        value = value.strip() if value else ""
        if value != self._container_root:
            self._container_root = value
            self._emit_state_changed()

    # ── Checkbox Predicates ───────────────────────────────────────

    def can_check_mounted(self, path: Path) -> bool:
        """Mount checkbox is disabled if any ancestor is already mounted."""
        for ms in self._mount_specs:
            if is_descendant(path, ms.mount_root):
                return False
        return True

    def can_mount(self, path: Path) -> bool:
        """Mount is valid only if path has no overlap with existing mounts (either direction)."""
        for ms in self._mount_specs:
            if is_descendant(path, ms.mount_root) or is_descendant(ms.mount_root, path):
                return False
        return True

    def can_push(self, path: Path) -> bool:
        """Push enabled when file is not already pushed."""
        return not self.is_pushed(path)

    # ── Mount Toggle ───────────────────────────────────────────────

    def toggle_mounted(self, path: Path, checked: bool) -> None:
        """Toggle bind mount for a path.

        Add: creates new MountSpecPath with delivery="bind".
        Remove: deletes entire MountSpecPath (all patterns lost).
        """
        self._toggle_mount_with_delivery(path, checked, delivery="bind")

    def toggle_detached_mount(self, path: Path, checked: bool) -> None:
        """Toggle detached-delivery mount for a path (UX: "Virtual Mount").

        Add: creates new MountSpecPath with delivery="detached".
        Remove: deletes entire MountSpecPath (all patterns lost).
        """
        self._toggle_mount_with_delivery(path, checked, delivery="detached")

    def toggle_detached_folder_mount(self, path: Path, checked: bool) -> None:
        """Toggle host-backed folder-seed detached mount (UX: "Virtual Folder").

        Add: creates new MountSpecPath with delivery="detached",
        content_seed="folder", host_path=path — container side is mkdir'd,
        no cp walk. Remove: deletes entire MountSpecPath.
        """
        self._toggle_mount_with_delivery(
            path, checked, delivery="detached", content_seed="folder",
        )

    def _toggle_mount_with_delivery(
        self, path: Path, checked: bool, delivery: str,
        content_seed: str = "tree",
    ) -> None:
        """Shared toggle body for bind / detached / virtual-folder deliveries."""
        self.aboutToMutate.emit()
        from ..core.mount_spec_path import MountSpecPath
        if checked:
            for ms in self._mount_specs:
                if is_descendant(path, ms.mount_root) or is_descendant(ms.mount_root, path):
                    return
            self._mount_specs.append(
                MountSpecPath(
                    mount_root=path,
                    delivery=delivery,
                    host_path=path,
                    content_seed=content_seed,
                ),
            )
        else:
            self._mount_specs = [
                ms for ms in self._mount_specs
                if ms.mount_root != path
            ]
        self._recompute_states()
        self.mountSpecsChanged.emit()

    def convert_delivery(self, path: Path, target: str) -> bool:
        """Flip delivery on the matching spec. Returns True if flipped."""
        self.aboutToMutate.emit()
        for ms in self._mount_specs:
            if ms.mount_root == path and ms.delivery != target:
                ms.delivery = target
                self._recompute_states()
                self.mountSpecsChanged.emit()
                return True
        return False

    def remove_but_keep_children(self, path: Path) -> bool:
        """Delegate to LocalMountConfig.remove_but_keep_children semantics.

        Replace the matching spec with N child specs (inheriting delivery).
        Returns True if replaced, False if no match / no children / not a dir.
        """
        from ..core.mount_spec_path import MountSpecPath

        parent = None
        for ms in self._mount_specs:
            if ms.mount_root == path:
                parent = ms
                break
        if parent is None or not path.is_dir():
            return False
        try:
            children = sorted(c for c in path.iterdir() if c.is_dir())
        except OSError:
            return False
        if not children:
            return False

        self.aboutToMutate.emit()
        new_specs: list[MountSpecPath] = []
        for child in children:
            child_rel = str(child.relative_to(parent.mount_root)).replace("\\", "/") + "/"
            child_patterns: list[str] = []
            for pat in parent.patterns:
                stripped = pat.lstrip("!")
                if stripped.startswith(child_rel):
                    prefix = "!" if pat.startswith("!") else ""
                    suffix = stripped[len(child_rel):]
                    if suffix:
                        child_patterns.append(f"{prefix}{suffix}")
            new_specs.append(
                MountSpecPath(
                    mount_root=child,
                    patterns=child_patterns,
                    delivery=parent.delivery,
                ),
            )
        idx = self._mount_specs.index(parent)
        self._mount_specs.pop(idx)
        for offset, ns in enumerate(new_specs):
            self._mount_specs.insert(idx + offset, ns)
        self._recompute_states()
        self.mountSpecsChanged.emit()
        return True

    # ── Pattern Operations (RMB actions) ───────────────────────────

    def _apply_pattern_operation(self, path: Path, prefix: str, add: bool) -> bool:
        """Shared body for add/remove mask/reveal operations."""
        self.aboutToMutate.emit()
        ms = self._find_owning_spec(path)
        if ms is None:
            return False
        rel = str(path.relative_to(ms.mount_root)).replace("\\", "/")
        operation = ms.add_pattern if add else ms.remove_pattern
        if not operation(f"{prefix}{rel}/"):
            return False
        self._recompute_states()
        self.mountSpecsChanged.emit()
        return True

    def add_mask(self, path: Path) -> bool:
        """Add mask pattern (vendor/) via RMB and recompute."""
        return self._apply_pattern_operation(path, "", add=True)

    def remove_mask(self, path: Path) -> bool:
        """Remove mask pattern (vendor/) and recompute."""
        return self._apply_pattern_operation(path, "", add=False)

    def add_reveal(self, path: Path) -> bool:
        """Add reveal pattern (!vendor/) via RMB and recompute."""
        return self._apply_pattern_operation(path, "!", add=True)

    def remove_reveal(self, path: Path) -> bool:
        """Remove reveal pattern (!vendor/) and recompute."""
        return self._apply_pattern_operation(path, "!", add=False)

    # ── Stencil spec operations (Scope Config RMB gestures) ──────

    def add_stencil_folder(
        self, container_path: Path, *, preserve_on_update: bool = False,
    ) -> bool:
        """Add a container-only detached-folder spec.

        UX: "Make Folder" (preserve_on_update=False) /
            "Make Permanent Folder → No Recreate" (preserve_on_update=True).

        Creates a MountSpecPath with ``delivery="detached"``,
        ``content_seed="folder"``, and ``host_path=None``.
        """
        return self._add_stencil_spec(
            container_path,
            delivery="detached",
            content_seed="folder",
            preserve_on_update=preserve_on_update,
        )

    def add_stencil_volume(self, container_path: Path) -> bool:
        """Add a container-only named-volume spec.

        UX: "Make Permanent Folder → Volume Mount". Creates a MountSpecPath
        with ``delivery="volume"``, ``content_seed="folder"``, and
        ``host_path=None``. A Docker named volume is emitted in compose.
        """
        return self._add_stencil_spec(
            container_path,
            delivery="volume",
            content_seed="folder",
            preserve_on_update=False,
        )

    def _add_stencil_spec(
        self,
        container_path: Path,
        *,
        delivery: str,
        content_seed: str,
        preserve_on_update: bool,
    ) -> bool:
        from ..core.mount_spec_path import MountSpecPath

        if any(ms.mount_root == container_path for ms in self._mount_specs):
            return False
        for ms in self._mount_specs:
            if is_descendant(container_path, ms.mount_root) or is_descendant(
                ms.mount_root, container_path,
            ):
                return False
        self.aboutToMutate.emit()
        self._mount_specs.append(
            MountSpecPath(
                mount_root=container_path,
                delivery=delivery,
                host_path=None,
                content_seed=content_seed,
                preserve_on_update=preserve_on_update,
            ),
        )
        self._recompute_states()
        self.mountSpecsChanged.emit()
        return True

    def mark_permanent(self, path: Path) -> bool:
        """Flip preserve_on_update False→True on detached-folder spec at ``path``.

        No-op (returns False) if the spec doesn't exist, is already permanent,
        or isn't ``delivery="detached"`` + ``content_seed="folder"``.
        """
        for ms in self._mount_specs:
            if ms.mount_root != path:
                continue
            if ms.preserve_on_update:
                return False
            if ms.delivery != "detached" or ms.content_seed != "folder":
                return False
            self.aboutToMutate.emit()
            ms.preserve_on_update = True
            self._recompute_states()
            self.mountSpecsChanged.emit()
            return True
        return False

    def unmark_permanent(self, path: Path) -> bool:
        """Flip preserve_on_update True→False on the spec at ``path``."""
        for ms in self._mount_specs:
            if ms.mount_root != path:
                continue
            if not ms.preserve_on_update:
                return False
            self.aboutToMutate.emit()
            ms.preserve_on_update = False
            self._recompute_states()
            self.mountSpecsChanged.emit()
            return True
        return False

    def remove_spec_at(self, path: Path) -> bool:
        """Remove the MountSpecPath whose mount_root equals ``path`` (any delivery)."""
        for i, ms in enumerate(self._mount_specs):
            if ms.mount_root == path:
                self.aboutToMutate.emit()
                self._mount_specs.pop(i)
                self._recompute_states()
                self.mountSpecsChanged.emit()
                return True
        return False

    def get_spec_at(self, path: Path):
        """Return the MountSpecPath whose mount_root equals ``path``, or None."""
        for ms in self._mount_specs:
            if ms.mount_root == path:
                return ms
        return None

    def get_any_spec_at(self, path: Path):
        """Return any MountSpecPath at ``path`` — user-authored or extension-synthesized.

        Used by owner-keyed routing (Task 1.10 RMB guard). ``get_spec_at``
        stays user-authored-only because its consumers (e.g.
        ``_add_scope_config_gestures``) must not surface gestures on
        extension-synthesized specs.
        """
        spec = self.get_spec_at(path)
        if spec is not None:
            return spec
        for ext in self._extensions:
            for synth in ext.synthesize_mount_specs():
                if synth.mount_root == path:
                    return synth
        return None

    def restore_mount_specs(self, specs_data: list[dict]) -> None:
        """Restore mount_specs from serialized dicts (undo/redo).

        Replaces current mount_specs and recomputes without emitting aboutToMutate.
        """
        from ..core.mount_spec_path import MountSpecPath
        host_root = self._host_project_root or Path()
        self._mount_specs = [
            MountSpecPath.from_dict(d, host_root) for d in specs_data
        ]
        self._recompute_states()
        self.mountSpecsChanged.emit()

    def _find_owning_spec(self, path: Path):
        """Find the MountSpecPath whose root contains this path."""
        for ms in self._mount_specs:
            if path == ms.mount_root or is_descendant(path, ms.mount_root):
                return ms
        return None

    def is_in_raw_set(self, field_name: str, path: Path) -> bool:
        """Check membership — used for checkbox state and RMB context.

        Args:
            field_name: One of 'mounted', 'detached_mounted', 'pushed'
            path: Path to check
        """
        if field_name == 'mounted':
            return any(
                ms.mount_root == path and ms.delivery == "bind"
                for ms in self._mount_specs
            )
        elif field_name == 'detached_mounted':
            return any(
                ms.mount_root == path and ms.delivery == "detached"
                for ms in self._mount_specs
            )
        elif field_name == 'pushed':
            return path in self._pushed_files
        return False

    # ── File Tracking ─────────────────────────────────────────────

    def is_pushed(self, path: Path) -> bool:
        """Check if file is currently pushed to the container."""
        return path in self._pushed_files

    def is_container_file(self, path: Path) -> bool:
        """Check if file was created inside the container."""
        return path in self._container_files

    def add_pushed(self, path: Path) -> None:
        """Mark file as pushed (after instant push), recompute."""
        self._pushed_files.add(path)
        self._recompute_states()

    def remove_pushed(self, path: Path) -> None:
        """Unmark file as pushed (after instant remove), recompute."""
        self._pushed_files.discard(path)
        self._recompute_states()

    def get_file_tracking_data(self) -> dict:
        """Get current file tracking data."""
        return {
            'pushed_files': self._pushed_files.copy(),
            'container_files': self._container_files.copy(),
        }

    # ── Config Persistence ────────────────────────────────────────

    def _filter_specs_by_root(self, root: Path) -> list:
        """Filter mount_specs to those whose mount_root is under a specific root."""
        return [
            ms for ms in self._mount_specs
            if is_descendant(ms.mount_root, root, strict=False)
        ]

    def get_config_data(self) -> dict:
        """Get config data for project root (excludes siblings).

        Returns dict with mount_specs and pushed_files filtered to project root.
        """
        if not self._host_project_root:
            return {'mount_specs': [], 'pushed_files': set()}
        return {
            'mount_specs': self._filter_specs_by_root(self._host_project_root),
            'pushed_files': {
                p for p in self._pushed_files
                if is_descendant(p, self._host_project_root, strict=False)
            },
        }

    def get_sibling_configs(self) -> list:
        """Extract per-sibling SiblingMount configs from mount_specs."""
        from ..core.config import SiblingMount
        result = []
        for sib_root in self._sibling_nodes:
            sib_specs = self._filter_specs_by_root(sib_root.path)
            sib_pushed = {
                p for p in self._pushed_files
                if is_descendant(p, sib_root.path, strict=False)
            }
            result.append(SiblingMount(
                host_path=sib_root.path,
                container_path=sib_root.container_path,
                mount_specs=sib_specs,
                pushed_files=sib_pushed,
            ))
        return result


    def load_config(self, config) -> None:
        """Phase 3→4: Load mount_specs + compute states once.

        Copies mount_specs from config (preserving pattern ordering),
        loads sibling subtrees, merges sibling specs, then recomputes
        NodeState via CORE in a single pass.
        """
        # Remove old sibling nodes from root_node.children
        if self._root_node:
            self._root_node.children = [
                c for c in self._root_node.children if c.source != NodeSource.SIBLING
            ]
        self._sibling_nodes.clear()

        # Project mount_specs (preserves pattern ordering)
        self._mount_specs = list(getattr(config, 'mount_specs', []))
        self._pushed_files = (
            config.pushed_files.copy()
            if hasattr(config, 'pushed_files') and config.pushed_files
            else set()
        )
        self._container_files = (
            config.container_files.copy()
            if hasattr(config, 'container_files') and config.container_files
            else set()
        )
        self._mirrored = getattr(config, 'mirrored', True)
        self._container_root = getattr(config, 'container_root', '') or ''
        self._extensions = list(config.extensions) if getattr(config, 'extensions', None) else []
        self.show_hidden = getattr(config, 'show_hidden', False)

        # Sibling subtrees — append to root_node, merge specs
        for sibling in getattr(config, 'siblings', []):
            sib_root = MountDataNode(
                path=sibling.host_path,
                source=NodeSource.SIBLING,
                parent=self._root_node,
                container_path=sibling.container_path,
            )
            sib_root.load_children(folders_only=False)
            if self._root_node:
                self._root_node.children.append(sib_root)
            self._sibling_nodes.append(sib_root)
            # Merge sibling mount_specs into unified list
            self._mount_specs.extend(sibling.mount_specs)
            self._pushed_files.update(sibling.pushed_files)

        # Extension isolation paths — emit synthetic stencil nodes driven off
        # the unified ExtensionConfig.synthesize_mount_specs() pipeline.
        self._rebuild_extension_stencil_nodes()

        self._recompute_states()
        self.mountSpecsChanged.emit()

    def _rebuild_extension_stencil_nodes(self) -> None:
        """Emit synthetic stencil tree nodes for each extension-synthesized spec.

        Task 1.9 unified-synth payoff: iterates
        ``ExtensionConfig.synthesize_mount_specs()`` — the same entrypoint the
        Docker/compose side consumes via ``compute_container_hierarchy`` — and
        builds one ``MountDataNode`` per synthesized spec's ``mount_root``.
        Tree nodes are tagged ``stencil_tier="auth"`` so the existing
        ``FOLDER_STENCIL_AUTH`` style keeps firing via ``resolve_tree_state``.
        Read-only in the GUI — no RMB gestures, container_lifecycle owns them.
        """
        # Drop any prior auth-tier stencil nodes from root_node.children (rebuild idempotency)
        if self._root_node:
            self._root_node.children = [
                c for c in self._root_node.children
                if not (c.is_stencil_node and c.stencil_tier == "auth")
            ]
        self._stencil_nodes.clear()

        if not self._root_node:
            return

        for ext in self._extensions:
            for spec in ext.synthesize_mount_specs():
                # Container paths are POSIX — Path() normalizes to host separators
                # on Windows, so restore POSIX form for the container_path tag.
                container_path = spec.mount_root.as_posix()
                node = MountDataNode(
                    path=spec.mount_root,
                    parent=self._root_node,
                    is_stencil_node=True,
                    stencil_tier="auth",
                    source=NodeSource.STENCIL,
                    container_path=container_path,
                )
                node.children_loaded = True  # synthetic — never lazy-load
                self._stencil_nodes.append(node)
                self._root_node.children.append(node)

    def build_config(
        self,
        scope_name: str,
        dev_mode: bool,
    ) -> 'ScopeDockerConfig':
        """Build a ScopeDockerConfig from current UI state.

        Siblings are extracted from tree via get_sibling_configs()
        rather than passed as a parameter.
        """
        from ..core.config import ScopeDockerConfig

        tree_data = self.get_config_data()
        tracking_data = self.get_file_tracking_data()
        siblings = self.get_sibling_configs()

        return ScopeDockerConfig(
            mount_specs=tree_data['mount_specs'],
            pushed_files=tree_data['pushed_files'],
            container_files=tracking_data['container_files'],
            scope_name=scope_name,
            host_project_root=self._host_project_root,
            dev_mode=dev_mode,
            mirrored=self._mirrored,
            container_root=self._container_root,
            siblings=siblings,
            extensions=list(self._extensions),
            show_hidden=self._show_hidden,
        )

    # ── Clear ─────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all state — used when switching projects."""
        self._host_project_root = None
        self._root_node = None
        self._current_scope = ""
        self._container_root = ""
        self._mount_specs.clear()
        self._pushed_files.clear()
        self._container_files.clear()
        self._extensions.clear()
        self._show_hidden = False
        MountDataNode.show_hidden = False
        self._states.clear()
        self._sibling_nodes.clear()
        self._stencil_nodes.clear()
        self.structureChanged.emit()  # Sync menu checkbox on project switch
        self.mountSpecsChanged.emit()
