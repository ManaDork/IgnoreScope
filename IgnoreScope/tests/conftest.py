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


def _docker_skip_reason() -> str | None:
    """Return a skip reason if Docker is unusable for the test run.

    Two-stage probe: ``docker info`` covers daemon presence/reachability, then
    a throwaway bind-mount run catches host-bridge corruption (e.g. Docker
    Desktop / WSL2 ``mkdir /run/desktop/mnt/host/c: file exists``). The latter
    surfaces as "Docker available" in ``docker info`` but fails every bind
    mount, producing cascade failures across the integration suite if not
    caught up-front.
    """
    import shutil
    import subprocess
    import tempfile

    try:
        info = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10,
        )
        if info.returncode != 0:
            return "Docker not available (`docker info` failed)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "Docker not available (`docker info` unreachable)"

    probe_dir = tempfile.mkdtemp(prefix="igs-docker-probe-")
    try:
        probe = subprocess.run(
            ["docker", "run", "--rm",
             "-v", f"{probe_dir}:/probe",
             "alpine", "true"],
            capture_output=True, timeout=60,
        )
        if probe.returncode != 0:
            err_lines = [
                ln.strip()
                for ln in probe.stderr.decode(errors="replace").splitlines()
                if ln.strip() and not ln.lstrip().startswith("Run '")
            ]
            tail = err_lines[0] if err_lines else "(no stderr)"
            return f"Docker bind-mount probe failed — likely host-bridge / WSL2 issue: {tail}"
    except subprocess.TimeoutExpired:
        return "Docker bind-mount probe timed out"
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)

    return None


def pytest_collection_modifyitems(config, items):
    """Auto-skip Docker tests when Docker daemon or bind mounts are unusable."""
    reason = _docker_skip_reason()
    if reason is None:
        return
    skip_docker = pytest.mark.skip(reason=reason)
    for item in items:
        if "docker" in item.keywords:
            item.add_marker(skip_docker)
