"""String sanitization utilities."""


def sanitize_volume_name(name: str) -> str:
    """Sanitize a name for use in Docker volume names.

    Docker volume names can only contain [a-zA-Z0-9][a-zA-Z0-9_.-]
    Must start with alphanumeric character.

    Args:
        name: Raw name to sanitize

    Returns:
        Sanitized name safe for Docker volumes
    """
    result = []
    for char in name.lower():
        if char.isalnum() or char in '_.-':
            result.append(char)
        elif char in '/\\ ':
            result.append('_')
    sanitized = ''.join(result)
    # Must start with alphanumeric
    if sanitized and not sanitized[0].isalnum():
        sanitized = 'v' + sanitized
    return sanitized or 'volume'
