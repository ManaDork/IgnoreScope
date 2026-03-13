"""IgnoreScope core models and configuration."""

from .config import (
    ScopeDockerConfig,
    SiblingMount,
    load_config,
    save_config,
    DEFAULT_CONTAINER_ROOT,
)
from .local_mount_config import LocalMountConfig
from .constants import (
    CONTAINER_WORKSPACE,
    CONTAINER_CLAUDE_AUTH,
    CONTAINER_CLAUDE_DIR,
    CONTAINER_HOOKS_DIR,
)
from .hierarchy import ContainerHierarchy, compute_container_hierarchy
from .node_state import (
    NodeState,
    compute_visibility,
    find_container_orphaned_paths,
    compute_node_state,
    apply_node_states_from_scope,
    detect_orphan_creating_removals,
)

__all__ = [
    "ScopeDockerConfig",
    "SiblingMount",
    "LocalMountConfig",
    "ContainerHierarchy",
    "load_config",
    "save_config",
    "compute_container_hierarchy",
    "DEFAULT_CONTAINER_ROOT",
    "CONTAINER_WORKSPACE",
    "CONTAINER_CLAUDE_AUTH",
    "CONTAINER_CLAUDE_DIR",
    "CONTAINER_HOOKS_DIR",
    "NodeState",
    "compute_visibility",
    "find_container_orphaned_paths",
    "compute_node_state",
    "apply_node_states_from_scope",
    "detect_orphan_creating_removals",
]
