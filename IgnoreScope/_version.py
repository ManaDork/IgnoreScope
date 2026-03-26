__version__ = "0.1.5"


def check_version_mismatch(data: dict) -> dict:
    """Validate config version. Route to migration modules for future transitions.

    v1: No auto-migration. Warns on version mismatch.
    Future: Chain migration functions per version gap.

    Args:
        data: Raw dict from scope_docker_desktop.json

    Returns:
        data dict, potentially migrated to current version schema
    """
    file_version = data.get('version', '')
    if file_version and file_version != __version__:
        # Future: route to migration/migration_v{old}_v{new}.py
        pass
    data['version'] = __version__
    return data
