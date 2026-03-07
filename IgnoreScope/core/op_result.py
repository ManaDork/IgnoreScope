"""Standardized operation result types for CORE file and container operations.

Provides:
- OpWarning: Pre-flight warnings (user can confirm to proceed)
- OpError: Blocking errors (operation cannot proceed)
- OpResult: Standardized single-operation result
- BatchFileResult: Categorized results for batch operations

Used by docker/file_ops.py orchestrators and consumed by GUI/CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


class OpWarning(Enum):
    """Pre-flight warnings. User can confirm to proceed (GUI dialog / CLI --force)."""

    FILE_ALREADY_TRACKED = auto()        # push: path in pushed_files already
    FILE_IN_CONTAINER_UNTRACKED = auto() # push: container has file, not tracked
    NOT_IN_MASKED_AREA = auto()          # push: file outside mask, push may have no effect
    LOCAL_FILE_EXISTS = auto()           # pull: would overwrite host file (non-dev-mode)
    DESTRUCTIVE_REMOVE = auto()          # remove-file: cannot be undone
    CONTAINER_DATA_LOSS = auto()         # remove/recreate container: volumes destroyed


class OpError(Enum):
    """Blocking errors. Operation cannot proceed regardless of force."""

    NO_PROJECT = auto()              # no host_project_root set
    CONFIG_LOAD_FAILED = auto()      # scope_docker.json unreadable
    CONTAINER_NOT_RUNNING = auto()   # container stopped or missing
    CONTAINER_NOT_FOUND = auto()     # container doesn't exist (for remove)
    DOCKER_NOT_RUNNING = auto()      # Docker daemon not available
    PROJECT_IN_INSTALL_DIR = auto()  # creating container in ISD's own dir
    NO_PUSHED_FILES = auto()         # no files configured for push (batch)
    NO_MATCHING_FILES = auto()       # --files filter matched nothing
    VALIDATION_FAILED = auto()       # config or hierarchy validation errors
    HOST_FILE_NOT_FOUND = auto()     # host file doesn't exist
    PARENT_NOT_MOUNTED = auto()      # push would create orphan (TTFF)
    INVALID_LOCATION = auto()        # path not under host_container_root
    FILE_NOT_IN_CONTAINER = auto()   # pull: container file missing


@dataclass
class OpResult:
    """Standardized operation result.

    Attributes:
        success: Whether the operation completed successfully
        message: Human-readable status message
        error: Blocking error if operation failed precondition check
        warnings: List of confirmable warnings from preflight
        details: Additional detail lines (e.g., validation error list)
    """

    success: bool
    message: str
    error: OpError | None = None
    warnings: list[OpWarning] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


@dataclass
class BatchFileResult:
    """Categorized results of batch preflight or execution.

    Attributes:
        errors: Files that cannot proceed (blocking errors)
        warnings: Files that need user confirmation
        clean: Files ready to execute (no issues)
    """

    errors: dict[Path, OpResult] = field(default_factory=dict)
    warnings: dict[Path, OpResult] = field(default_factory=dict)
    clean: list[Path] = field(default_factory=list)
