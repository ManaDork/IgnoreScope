"""Validation and error handling for IgnoreScope.

Provides validation functions for container state and configuration.
"""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.config import ScopeDockerConfig


def validate_container_ready(container_name: str) -> list[str]:
    """Validate container is ready and accessible.

    Args:
        container_name: Name of container to validate

    Returns:
        List of error messages (empty if valid)
    """
    from ..docker import get_container_info

    errors = []

    # Get container info
    info = get_container_info(container_name)
    if not info:
        errors.append(f"Container not found or not accessible: {container_name}")
        return errors

    # Container must have valid status
    status = info.get('status', 'unknown')
    if status == 'unknown':
        errors.append(f"Container state unknown: {container_name}")

    return errors


def validate_config_completeness(config: 'ScopeDockerConfig') -> list[str]:
    """Validate that configuration has required fields.

    Checks:
    1. host_project_root is set
    2. container_name is set
    3. At least one mount is configured

    Args:
        config: ScopeDockerConfig to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    warnings = []

    # Check required fields
    if not config.host_project_root:
        errors.append("host_project_root is not set")

    if not config.scope_name:
        errors.append("scope_name is not set")

    if not config.mounts:
        errors.append("No mounts configured")

    if not config.masked:
        warnings.append("No masked folders configured")

    return errors + warnings


def validate_paths_exist(
    config: 'ScopeDockerConfig',
    check_mounts: bool = True,
    check_masked: bool = True,
    check_revealed: bool = True,
) -> list[str]:
    """Validate that configured paths exist on the host.

    Args:
        config: ScopeDockerConfig to validate
        check_mounts: Validate mounts exist
        check_masked: Validate masked paths exist
        check_revealed: Validate revealed paths exist

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if check_mounts:
        for mount in config.mounts:
            if not mount.exists():
                errors.append(f"Mount not found: {mount}")
            elif not mount.is_dir():
                errors.append(f"Mount is not a directory: {mount}")

    if check_masked:
        for mask in config.masked:
            if not mask.exists():
                errors.append(f"Masked path not found: {mask}")
            elif not mask.is_dir():
                errors.append(f"Masked path is not a directory: {mask}")

    if check_revealed:
        for reveal in config.revealed:
            if not reveal.exists():
                errors.append(f"Revealed path not found: {reveal}")
            elif not reveal.is_dir():
                errors.append(f"Revealed path is not a directory: {reveal}")

    return errors


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, errors: list[str]):
        """Initialize with list of error messages.

        Args:
            errors: List of error message strings
        """
        self.errors = errors
        message = "Validation failed:\n" + "\n".join(f"  * {e}" for e in errors)
        super().__init__(message)


def validate_and_raise(config: 'ScopeDockerConfig', container_name: Optional[str] = None) -> None:
    """Validate configuration and raise ValidationError if invalid.

    Args:
        config: ScopeDockerConfig to validate
        container_name: Optional container name to validate

    Raises:
        ValidationError: If validation fails
    """
    errors = []

    errors.extend(validate_config_completeness(config))
    errors.extend(validate_paths_exist(config))

    if container_name:
        errors.extend(validate_container_ready(container_name))

    if errors:
        raise ValidationError(errors)
