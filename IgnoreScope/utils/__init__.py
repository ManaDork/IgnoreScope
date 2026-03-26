"""IgnoreScope utilities and helpers."""

from .paths import (
    to_relative_posix,
    to_relative_posix_or_name,
    to_dir_pattern,
    is_descendant,
    is_ancestor,
    relative_to_safe,
    normalize_posix,
)
from .strings import sanitize_volume_name
from .validation import validate_container_ready

__all__ = [
    "to_relative_posix",
    "to_relative_posix_or_name",
    "to_dir_pattern",
    "is_descendant",
    "is_ancestor",
    "relative_to_safe",
    "normalize_posix",
    "sanitize_volume_name",
    "validate_container_ready",
]
