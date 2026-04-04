"""File content filters applied between host read and container push.

Filters transform file content before docker cp. The original host file
is never modified — filters produce a temporary copy.

Placeholder module — filter implementations deferred to a later pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


# Type alias for filter functions.
# Input: host file path.
# Output: path to (possibly temp) file to push (may be same as input = no-op).
FileFilter = Callable[[Path], Path]


def passthrough(host_path: Path) -> Path:
    """No-op filter. Returns input path unchanged."""
    return host_path
