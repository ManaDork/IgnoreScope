"""
container_probe.py
------------------
Collection of diagnostic and test utilities from the LLM-in-container
architecture exploration. Run from INSIDE the container unless noted.

Sections:
  1. Container Identity & Filesystem Probe
  2. Host Network & MCP Gateway Probe
  3. Filesystem Walker (symlink/junction-safe)
  4. Mount Point Inspector
  5. Test Result Runner (run on HOST side)
"""

import os
import json
import socket
import platform
import urllib.request
import urllib.error
from pathlib import Path


# ─────────────────────────────────────────────
# SECTION 1 — Container Identity & Filesystem Probe
# Run from inside the container.
# ─────────────────────────────────────────────

def probe_identity() -> dict:
    """
    Confirm we're inside a container and report basic environment info.
    """
    report = {}

    report["hostname"] = socket.gethostname()
    report["platform"] = platform.platform()
    report["python"] = platform.python_version()
    report["cwd"] = os.getcwd()

    # Near-certain container indicator
    report["is_container"] = os.path.exists("/.dockerenv")

    # cgroup membership — shows container ID on most Docker setups
    cgroup_path = "/proc/1/cgroup"
    if os.path.exists(cgroup_path):
        try:
            report["cgroup"] = open(cgroup_path).read().strip()
        except PermissionError:
            report["cgroup"] = "permission_denied"
    else:
        report["cgroup"] = "not_found"

    # Environment variables (filtered — skip secrets/tokens)
    skip_keys = {"PATH", "HOME", "USER", "SHELL", "TERM", "LANG"}
    report["env"] = {
        k: v for k, v in os.environ.items()
        if k not in skip_keys and "TOKEN" not in k and "SECRET" not in k and "KEY" not in k
    }

    return report


def probe_known_mounts(paths: list[str] | None = None) -> dict:
    """
    Check a list of expected mount/probe points and report what's visible.
    Adjust `paths` to match your actual container mount topology.
    """
    default_paths = [
        "/workspace",
        "/app",
        "/host",
        "/data",
        "/shared",
        "/tests",
        "/results",
        "/mnt",
    ]
    targets = paths or default_paths
    results = {}

    for p in targets:
        if os.path.exists(p):
            try:
                contents = os.listdir(p)
                results[p] = {"status": "visible", "contents": contents[:10]}  # sample
            except PermissionError:
                results[p] = {"status": "permission_denied"}
        else:
            results[p] = {"status": "not_found"}

    return results


# ─────────────────────────────────────────────
# SECTION 2 — Host Network & MCP Gateway Probe
# Run from inside the container.
# Tests reachability of host via host.docker.internal.
# ─────────────────────────────────────────────

HOST = "host.docker.internal"

# Common ports to scan — add/remove as needed
SCAN_PORTS = [
    2375,   # Docker daemon (unencrypted) — high value target
    2376,   # Docker daemon (TLS)
    8811,   # Docker Desktop MCP Gateway (reported default)
    8080,   # Generic HTTP
    9000,   # Portainer / misc
    3000,   # Dev servers
    5000,   # Flask / misc
]


def probe_host_dns() -> dict:
    """Confirm host.docker.internal resolves — indicates default bridge networking."""
    try:
        ip = socket.gethostbyname(HOST)
        return {"resolved": True, "ip": ip}
    except socket.gaierror as e:
        return {"resolved": False, "error": str(e)}


def probe_host_ports(ports: list[int] | None = None, timeout: float = 1.0) -> dict:
    """TCP connect scan against host ports."""
    targets = ports or SCAN_PORTS
    results = {}

    for port in targets:
        try:
            s = socket.create_connection((HOST, port), timeout=timeout)
            s.close()
            results[port] = "open"
        except (ConnectionRefusedError, OSError):
            results[port] = "closed"
        except socket.timeout:
            results[port] = "timeout"

    return results


def probe_mcp_gateway(port: int = 8811) -> dict:
    """
    Attempt to contact the Docker Desktop MCP Gateway over HTTP.
    Probes the root endpoint and reports response/error.
    """
    url = f"http://{HOST}:{port}/"
    result = {"url": url}

    try:
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=2)
        result["status"] = resp.status
        result["body_preview"] = resp.read(256).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        result["http_error"] = e.code
        result["reason"] = e.reason
    except urllib.error.URLError as e:
        result["url_error"] = str(e.reason)
    except Exception as e:
        result["error"] = str(e)

    return result


# ─────────────────────────────────────────────
# SECTION 3 — Filesystem Walker (symlink-safe)
# Run from inside the container.
# Traverses from a root, handles symlinks and junctions without infinite loops.
# ─────────────────────────────────────────────

def walk_filesystem(
    root: str = "/",
    max_depth: int = 4,
    follow_links: bool = True,
    sample_files: int = 5,
) -> dict:
    """
    Walk the filesystem from `root`, respecting max_depth and avoiding
    cycles from symlinks or NTFS junctions.

    Returns a dict of { path: [sampled_files] } for visible directories.
    """
    visible = {}
    seen_real = set()

    for dirpath, dirs, files in os.walk(root, followlinks=follow_links):
        # Cycle detection
        real = os.path.realpath(dirpath)
        if real in seen_real:
            dirs.clear()
            continue
        seen_real.add(real)

        # Depth limit
        depth = dirpath.rstrip("/").count("/")
        if depth > max_depth:
            dirs.clear()
            continue

        visible[dirpath] = files[:sample_files]

    return visible


def check_symlink_types(paths: list[str]) -> dict:
    """
    For a list of paths, report what kind of filesystem object each is.
    Helps diagnose mount vs junction vs symlink behaviour.
    """
    results = {}
    for p in paths:
        path = Path(p)
        if not path.exists() and not path.is_symlink():
            results[p] = "not_found"
        elif path.is_symlink():
            results[p] = f"symlink -> {os.readlink(p)}"
        elif path.is_mount():
            results[p] = "mount_point"
        elif path.is_dir():
            results[p] = "directory"
        elif path.is_file():
            results[p] = "file"
        else:
            results[p] = "unknown"
    return results


# ─────────────────────────────────────────────
# SECTION 4 — Mount Point Inspector
# Run from inside the container.
# Reads /proc/mounts to show the full mount table the container sees.
# ─────────────────────────────────────────────

def probe_mounts() -> list[dict]:
    """
    Parse /proc/mounts and return structured mount entries.
    Compare against host output to verify mask/punch-through topology.
    """
    mounts_path = "/proc/mounts"
    if not os.path.exists(mounts_path):
        return [{"error": "/proc/mounts not available"}]

    mounts = []
    with open(mounts_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 4:
                mounts.append({
                    "device": parts[0],
                    "mountpoint": parts[1],
                    "fstype": parts[2],
                    "options": parts[3],
                })
    return mounts


# ─────────────────────────────────────────────
# SECTION 5 — Test Result Runner
# Run on the HOST side, not inside the container.
# Executes tests written by the LLM against real source,
# writes sanitized results to the shared results folder.
# ─────────────────────────────────────────────

def run_tests_and_write_results(
    test_file: str,
    results_path: str = "./results/last_run.json",
    strip_tracebacks: bool = True,
) -> None:
    """
    HOST-SIDE RUNNER. Do not run inside the container.

    Runs pytest on `test_file`, collects results, and writes a sanitized
    JSON report to `results_path`. Tracebacks are stripped by default to
    avoid leaking implementation details back into the container.

    Requirements: pip install pytest
    """
    import subprocess
    import sys

    os.makedirs(os.path.dirname(results_path) or ".", exist_ok=True)

    # Run pytest with JSON output via subprocess to isolate execution
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "--tb=short", "-q", "--no-header"],
        capture_output=True,
        text=True,
    )

    raw_output = result.stdout + result.stderr
    lines = raw_output.splitlines()

    results = {}
    current_test = None

    for line in lines:
        # pytest -q format: "test_name PASSED" / "test_name FAILED"
        if " PASSED" in line:
            name = line.split(" PASSED")[0].strip()
            results[name] = {"status": "pass"}
        elif " FAILED" in line:
            name = line.split(" FAILED")[0].strip()
            results[name] = {"status": "fail"}
        elif " ERROR" in line:
            name = line.split(" ERROR")[0].strip()
            results[name] = {"status": "error", "type": "CollectionError"}

    # If tracebacks stripped, we only expose exception type, not message
    if not strip_tracebacks:
        # Attach raw output — only use this for internal/host-side debugging
        for name in results:
            results[name]["raw"] = raw_output

    summary = {
        "return_code": result.returncode,
        "tests": results,
        "counts": {
            "pass": sum(1 for v in results.values() if v["status"] == "pass"),
            "fail": sum(1 for v in results.values() if v["status"] == "fail"),
            "error": sum(1 for v in results.values() if v["status"] == "error"),
        },
    }

    with open(results_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Results written to {results_path}")


# ─────────────────────────────────────────────
# MAIN — run all container-side probes and print report
# ─────────────────────────────────────────────

if __name__ == "__main__":
    report = {}

    print("=== Running container probes ===\n")

    print("[1/4] Identity...")
    report["identity"] = probe_identity()

    print("[2/4] Known mount points...")
    report["mounts_probed"] = probe_known_mounts()

    print("[3/4] Host network...")
    report["host_dns"] = probe_host_dns()
    if report["host_dns"].get("resolved"):
        report["host_ports"] = probe_host_ports()
        report["mcp_gateway"] = probe_mcp_gateway()
    else:
        report["host_ports"] = "skipped (DNS failed)"
        report["mcp_gateway"] = "skipped (DNS failed)"

    print("[4/4] Mount table...")
    report["proc_mounts"] = probe_mounts()

    print("\n=== Report ===\n")
    print(json.dumps(report, indent=2, default=str))

    # Optionally write to shared results folder if it exists
    out_path = "/results/probe_report.json"
    if os.path.exists(os.path.dirname(out_path)):
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport also written to {out_path}")
