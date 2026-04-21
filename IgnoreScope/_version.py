import os

__version__ = "0.4.1"

# Dev-mode bypass: when truthy in os.environ, check_version_mismatch() returns
# data unchanged (no migration chain, no version stamping). Intended for tests
# and development workflows that want to exercise from_dict() directly without
# tying assertions to the current __version__ string.
DEV_BYPASS_ENV_VAR = "IGNORESCOPE_SKIP_VERSION_MIGRATION"


def _dev_bypass_enabled() -> bool:
    return os.environ.get(DEV_BYPASS_ENV_VAR, "").lower() in ("1", "true", "yes")


def _version_tuple(v: str) -> tuple:
    """Parse version string to comparable tuple."""
    try:
        return tuple(int(x) for x in v.split('.'))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def check_version_mismatch(data: dict) -> dict:
    """Validate config version and apply migrations as needed.

    Chains migration functions for each version gap between the file's
    version and the current version. Each migration transforms the raw
    data dict in-place before from_dict() parses it.

    When DEV_BYPASS_ENV_VAR is set in os.environ, returns data unchanged
    (no migration, no version stamping) — see module docstring.

    Args:
        data: Raw dict from scope_docker_desktop.json

    Returns:
        data dict, migrated to current version schema
    """
    if _dev_bypass_enabled():
        return data

    file_version = data.get('version', '')
    file_ver = _version_tuple(file_version)

    # Migration: pre-0.2.0 → 0.2.0 (flat sets → mount_specs)
    if file_ver < (0, 2, 0):
        from IgnoreScope.core.migration import migrate_to_0_2_0
        data = migrate_to_0_2_0(data)

    data['version'] = __version__
    return data
