"""IgnoreScope: Docker container management with masked folders.

Extends LocalMountConfig to support exception files—individual files
within masked folders that can be dynamically pushed/pulled to/from Docker containers
without rebuild.

Key Innovation: Uses docker cp to write files into mask volumes (hidden folders),
making them visible to the containerized application at their original paths.
"""

import builtins
from ._version import __version__
builtins.__version__ = __version__
__author__ = "Claude Code"

from .core.config import ScopeDockerConfig, load_config, save_config
from .core import LocalMountConfig

__all__ = [
    "ScopeDockerConfig",
    "LocalMountConfig",
    "load_config",
    "save_config",
]
