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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
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
    VIRTUAL = "virtual"


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

    Covers project files, sibling files, and virtual entries.
    """
    # Class-level filter flag — set by MountDataTree before triggering loads
    show_hidden: ClassVar[bool] = False

    path: Path
    parent: Optional[MountDataNode] = None
    children: list[MountDataNode] = field(default_factory=list)
    children_loaded: bool = False
    is_file: bool = False
    is_virtual: bool = False
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
        if self.children_loaded or self.is_file or self.is_virtual:
            return

        self.children = []
        try:
            entries = list(self.path.iterdir())

            # Filter BEFORE sort — is_file() can crash on Windows device names
            filtered: list[tuple[Path, bool]] = []
            for entry in entries:
                if not MountDataNode.show_hidden and entry.name.startswith('.'):
                    continue
                if _is_windows_reserved_name(entry.name):
                    continue
                try:
                    is_file = entry.is_file()
                except OSError:
                    continue
                if folders_only and is_file:
                    continue
                filtered.append((entry, is_file))

            # Sort: folders first, then alphabetical
            filtered.sort(key=lambda pair: (pair[1], pair[0].name.lower()))

            for entry, is_file in filtered:
                child = MountDataNode(
                    path=entry,
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

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._root_node: Optional[MountDataNode] = None
        self._host_project_root: Optional[Path] = None
        self._current_scope: str = ""

        # Raw config sets (mutable layer)
        self._mounts: set[Path] = set()
        self._masked: set[Path] = set()
        self._revealed: set[Path] = set()
        self._pushed_files: set[Path] = set()
        self._container_files: set[Path] = set()
        self._mirrored: bool = True
        self._container_root: str = ""

        # Computed state (CORE output)
        self._states: dict[Path, NodeState] = {}

        # Sibling and virtual subtrees
        self._sibling_nodes: list[MountDataNode] = []
        self._virtual_nodes: list[MountDataNode] = []

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
        """Rebuild _states from raw sets via CORE apply_node_states_from_scope().

        Computes mirrored intermediates once (with GUI ceiling), then passes
        them to both _collect_all_paths (for tree node inclusion) and to CORE
        via config namespace (for Stage 2b hidden→mirrored upgrade).
        """
        # Compute mirrored intermediates once for both path collection and Stage 2b
        if self._mirrored and self._host_project_root:
            from ..core.hierarchy import compute_mirrored_intermediate_paths
            ceiling = self._host_project_root.parent
            mirrored_intermediates = compute_mirrored_intermediate_paths(
                self._masked, self._revealed, self._mounts,
                ceiling=ceiling,
            )
        else:
            mirrored_intermediates = set()

        all_paths = self._collect_all_paths(mirrored_intermediates)
        config_ns = SimpleNamespace(
            mounts=self._mounts,
            masked=self._masked,
            revealed=self._revealed,
            pushed_files=self._pushed_files,
            mirrored=self._mirrored,
        )
        self._states = apply_node_states_from_scope(config_ns, all_paths)
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
        # Union with all config set paths
        paths.update(self._mounts)
        paths.update(self._masked)
        paths.update(self._revealed)
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
        self._mounts.clear()
        self._masked.clear()
        self._revealed.clear()
        self._pushed_files.clear()
        self._container_files.clear()
        self._sibling_nodes.clear()
        self._virtual_nodes.clear()
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
        return frozenset(self._mounts)

    @property
    def masked(self) -> frozenset[Path]:
        """Active mask volume paths."""
        return frozenset(self._masked)

    @property
    def revealed(self) -> frozenset[Path]:
        """Active punch-through paths."""
        return frozenset(self._revealed)

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
        """Mount checkbox is disabled if any ancestor is already in _mounts.

        Raw set check — does NOT consult CORE state.
        """
        for m in self._mounts:
            if is_descendant(path, m):
                return False
        return True

    def can_check_masked(self, path: Path) -> bool:
        """Mask checkbox enabled when CORE says path is mounted."""
        return self._states.get(path, _DEFAULT_NODE_STATE).mounted

    def can_check_revealed(self, path: Path) -> bool:
        """Reveal checkbox enabled when CORE says path is masked."""
        return self._states.get(path, _DEFAULT_NODE_STATE).masked

    def can_push(self, path: Path) -> bool:
        """Push enabled when file is not already pushed."""
        return not self.is_pushed(path)

    # ── Toggle Operations ─────────────────────────────────────────

    def toggle_mounted(self, path: Path, checked: bool) -> None:
        """Toggle mount for a path.

        Cascade on uncheck: removes path + descendants from masked and revealed.
        """
        if checked:
            self._mounts.add(path)
        else:
            self._mounts.discard(path)
            # WIRING POINT (Logic Phase — config_manager.py):
            # Call detect_orphan_creating_removals(self._pushed_files,
            #     self._mounts | {path}, self._masked, {path})
            # BEFORE cascade. Show confirmation dialog if result is non-empty.
            # Cascade: remove path + descendants from masked and revealed
            self._masked = {
                p for p in self._masked
                if not is_descendant(p, path, strict=False)
            }
            self._revealed = {
                p for p in self._revealed
                if not is_descendant(p, path, strict=False)
            }
        self._recompute_states()

    def toggle_masked(self, path: Path, checked: bool) -> None:
        """Toggle mask for a path.

        Cascade on uncheck: removes path + descendants from revealed.
        """
        if checked:
            self._masked.add(path)
        else:
            self._masked.discard(path)
            # Cascade: remove path + descendants from revealed
            self._revealed = {
                p for p in self._revealed
                if not is_descendant(p, path, strict=False)
            }
        self._recompute_states()

    def toggle_revealed(self, path: Path, checked: bool) -> None:
        """Toggle reveal for a path. No cascade."""
        if checked:
            self._revealed.add(path)
        else:
            self._revealed.discard(path)
        self._recompute_states()

    def is_in_raw_set(self, field_name: str, path: Path) -> bool:
        """Check raw set membership — used for checkbox checked state.

        Args:
            field_name: One of 'mounted', 'masked', 'revealed', 'pushed'
            path: Path to check
        """
        if field_name == 'mounted':
            return path in self._mounts
        elif field_name == 'masked':
            return path in self._masked
        elif field_name == 'revealed':
            return path in self._revealed
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

    def _filter_sets_by_root(self, root: Path) -> dict:
        """Filter raw sets to paths under a specific root.

        Used for both project extraction (get_config_data) and
        sibling extraction (get_sibling_configs). DRY helper.
        """
        return {
            'mounts': {p for p in self._mounts if is_descendant(p, root, strict=False)},
            'masked': {p for p in self._masked if is_descendant(p, root, strict=False)},
            'revealed': {p for p in self._revealed if is_descendant(p, root, strict=False)},
            'pushed_files': {p for p in self._pushed_files if is_descendant(p, root, strict=False)},
        }

    def get_config_data(self) -> dict:
        """Get mount/mask/reveal/pushed data from raw sets.

        Filters to project-root paths only (excludes sibling state).
        """
        if not self._host_project_root:
            return {'mounts': set(), 'masked': set(), 'revealed': set(), 'pushed_files': set()}
        return self._filter_sets_by_root(self._host_project_root)

    def get_sibling_configs(self) -> list:
        """Extract per-sibling SiblingMount configs from unified raw sets.

        Each sibling's sets are filtered to paths under that sibling's root.
        """
        from ..core.config import SiblingMount
        result = []
        for sib_root in self._sibling_nodes:
            filtered = self._filter_sets_by_root(sib_root.path)
            result.append(SiblingMount(
                host_path=sib_root.path,
                container_path=sib_root.container_path,
                **filtered,
            ))
        return result

    def load_config_data(self, data: dict) -> None:
        """Load configuration data into raw sets, recompute."""
        self._mounts = set(data.get('mounts', set()))
        self._masked = set(data.get('masked', set()))
        self._revealed = set(data.get('revealed', set()))
        self._recompute_states()

    def load_config(self, config) -> None:
        """Phase 3→4: Load all config sets + compute states once.

        Sets all raw sets from config (Phase 3), loads sibling subtrees,
        merges sibling sets into unified raw sets, then recomputes
        NodeState via CORE (Phase 4) in a single pass.
        Caller manages batch mode and view refresh.
        """
        # Remove old sibling nodes from root_node.children
        if self._root_node:
            self._root_node.children = [
                c for c in self._root_node.children if c.source != NodeSource.SIBLING
            ]
        self._sibling_nodes.clear()

        # Project raw sets
        self._mounts = set(config.mounts)
        self._masked = set(config.masked)
        self._revealed = set(config.revealed)
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

        # Sibling subtrees — append to root_node, merge sets
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
            # Merge sibling sets into unified raw sets
            self._mounts.update(sibling.mounts)
            self._masked.update(sibling.masked)
            self._revealed.update(sibling.revealed)
            self._pushed_files.update(sibling.pushed_files)

        self._recompute_states()

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
            mounts=tree_data['mounts'],
            masked=tree_data['masked'],
            revealed=tree_data['revealed'],
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
        self._mounts.clear()
        self._masked.clear()
        self._revealed.clear()
        self._pushed_files.clear()
        self._container_files.clear()
        self._extensions.clear()
        self._show_hidden = False
        MountDataNode.show_hidden = False
        self._states.clear()
        self._sibling_nodes.clear()
        self._virtual_nodes.clear()
        self.structureChanged.emit()  # Sync menu checkbox on project switch
