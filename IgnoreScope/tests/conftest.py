"""Pytest configuration for IgnoreScope tests.

Defines custom markers and fixtures used across test modules.
"""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "docker: marks tests as requiring Docker (deselect with '-m \"not docker\"')"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow-running (deselect with '-m \"not slow\"')"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip Docker tests if Docker is not available."""
    import subprocess

    # Check if Docker is available
    docker_available = False
    try:
        result = subprocess.run(
            ['docker', 'info'],
            capture_output=True,
            timeout=10,
        )
        docker_available = result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    if not docker_available:
        skip_docker = pytest.mark.skip(reason="Docker not available")
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(skip_docker)
