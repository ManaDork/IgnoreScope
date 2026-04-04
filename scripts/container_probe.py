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
  5. Device Topology & Mount Escape Tests
  6. /proc Mask Audit
  7. Capability & Privilege Probe
  8. Volume Mask Verification (IgnoreScope)
  9. Test Result Runner (run on HOST side)
"""

import os
import json
import socket
import stat
import platform
import ctypes
import ctypes.util
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


def probe_mount_scope(mount_point: str | None = None) -> dict:
    """
    Test whether a 9p/drvfs mount exposes anything beyond the mounted path.
    Returns folder count visible at mount root — does NOT return names.
    """
    if mount_point is None:
        mount_point = os.getcwd()
    result = {"mount_point": mount_point}

    if not os.path.exists(mount_point):
        result["status"] = "mount_not_found"
        return result

    if not os.path.ismount(mount_point):
        result["status"] = "not_a_mount_point"
        return result

    mount_dev = os.stat(mount_point).st_dev
    parent_dev = os.stat(os.path.dirname(mount_point)).st_dev
    result["crosses_device_boundary"] = mount_dev != parent_dev

    # Count top-level folders inside the mount — no names, no children
    try:
        entries = os.listdir(mount_point)
        folder_count = sum(
            1 for e in entries
            if os.path.isdir(os.path.join(mount_point, e))
        )
        result["top_level_folder_count"] = folder_count
        result["top_level_total_entries"] = len(entries)
        result["status"] = "accessible"
    except PermissionError:
        result["status"] = "permission_denied"

    # Check if traversing ../ from inside the mount stays on the host device
    # or escapes back to the container overlay
    try:
        parent_from_inside = os.path.join(mount_point, "..")
        parent_dev_from_inside = os.stat(parent_from_inside).st_dev
        result["parent_traversal"] = {
            "mount_device": mount_dev,
            "parent_device": parent_dev_from_inside,
            "stays_on_host": mount_dev == parent_dev_from_inside,
        }
    except PermissionError:
        result["parent_traversal"] = {"status": "permission_denied"}

    return result


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
# SECTION 5 — Device Topology & Mount Escape Tests
# Run from inside the container.
# Maps all device boundaries and tests escape vectors against mount confinement.
# ─────────────────────────────────────────────

def probe_device_topology(extra_paths: list[str] | None = None) -> dict:
    """
    Map every distinct device in the container's filesystem.
    Returns { device_id: { "paths": [...], "fstype": "..." } }.
    """
    probe_paths = [
        "/", "/root", "/tmp", "/etc", "/proc", "/dev", "/sys",
        "/etc/resolv.conf", "/etc/hostname", "/etc/hosts",
    ]
    if extra_paths:
        probe_paths.extend(extra_paths)

    # Auto-discover mount points from mountinfo
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) > 4:
                    probe_paths.append(parts[4])
    except (PermissionError, FileNotFoundError):
        pass

    # Stat each path and group by device
    devices: dict[int, dict] = {}
    for p in probe_paths:
        try:
            s = os.stat(p)
            dev = s.st_dev
            if dev not in devices:
                devices[dev] = {"paths": [], "fstype": "unknown"}
            if p not in devices[dev]["paths"]:
                devices[dev]["paths"].append(p)
        except (FileNotFoundError, PermissionError):
            pass

    # Resolve filesystem types from /proc/mounts
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    mountpoint = parts[1]
                    fstype = parts[2]
                    for dev, info in devices.items():
                        if mountpoint in info["paths"]:
                            info["fstype"] = fstype
                            break
    except (PermissionError, FileNotFoundError):
        pass

    return {str(dev): info for dev, info in sorted(devices.items())}


def probe_mount_escape(mount_point: str | None = None) -> dict:
    """
    Test multiple escape vectors against a mount boundary.
    Returns per-vector pass/fail results.
    """
    if mount_point is None:
        mount_point = os.getcwd()
    results = {"mount_point": mount_point}

    if not os.path.exists(mount_point):
        results["status"] = "mount_not_found"
        return results

    try:
        mount_dev = os.stat(mount_point).st_dev
    except PermissionError:
        results["status"] = "permission_denied"
        return results

    results["mount_device"] = mount_dev

    # Vector 1: .. path traversal
    try:
        parent_dev = os.stat(os.path.join(mount_point, "..")).st_dev
        results["dotdot_traversal"] = {
            "parent_device": parent_dev,
            "escaped": parent_dev == mount_dev,
        }
    except PermissionError:
        results["dotdot_traversal"] = {"status": "permission_denied"}

    # Vector 2: openat(mount_fd, "..") — FD-relative escape
    try:
        mount_fd = os.open(mount_point, os.O_RDONLY | os.O_DIRECTORY)
        try:
            parent_fd = os.open("..", os.O_RDONLY | os.O_DIRECTORY, dir_fd=mount_fd)
            parent_dev_fd = os.fstat(parent_fd).st_dev
            results["openat_escape"] = {
                "parent_device": parent_dev_fd,
                "escaped": parent_dev_fd == mount_dev,
            }
            os.close(parent_fd)
        except OSError as e:
            results["openat_escape"] = {"error": str(e)}
        os.close(mount_fd)
    except OSError as e:
        results["openat_escape"] = {"error": str(e)}

    # Vector 3: /proc/self/root alternate traversal
    mount_name = os.path.basename(mount_point)
    mount_parent = os.path.dirname(mount_point)
    proc_parent = f"/proc/self/root{mount_parent}"
    try:
        proc_dev = os.stat(proc_parent).st_dev
        results["proc_self_root"] = {
            "path": proc_parent,
            "device": proc_dev,
            "escaped": proc_dev == mount_dev,
        }
    except (FileNotFoundError, PermissionError) as e:
        results["proc_self_root"] = {"error": str(e)}

    # Vector 4: Symlink creation pointing outside mount
    test_link = os.path.join(mount_point, "_probe_escape_symlink")
    try:
        os.symlink("/etc/passwd", test_link)
        link_dev = os.stat(test_link).st_dev
        results["symlink_escape"] = {
            "target_device": link_dev,
            "escaped": link_dev == mount_dev,
        }
        os.unlink(test_link)
    except OSError as e:
        results["symlink_escape"] = {"error": str(e)}
        try:
            os.unlink(test_link)
        except OSError:
            pass

    # Vector 5: Hardlink across device boundary
    test_hardlink = os.path.join(mount_point, "_probe_escape_hardlink")
    try:
        os.link("/etc/hostname", test_hardlink)
        results["hardlink_escape"] = {"status": "CREATED — cross-device link succeeded"}
        os.unlink(test_hardlink)
    except OSError as e:
        results["hardlink_escape"] = {"blocked": True, "error": str(e)}

    # Vector 6: mount(2) syscall — attempt to remount with broader root
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        ret = libc.mount(b"none", b"/mnt", b"9p", 0, b"aname=drvfs;path=/")
        errno = ctypes.get_errno()
        results["mount_syscall"] = {
            "return": ret,
            "errno": errno,
            "blocked": ret != 0,
            "error": os.strerror(errno) if errno else None,
        }
    except OSError as e:
        results["mount_syscall"] = {"error": str(e)}

    # Vector 7: unshare — new mount namespace
    try:
        import subprocess
        r = subprocess.run(
            ["unshare", "-m", "true"],
            capture_output=True, text=True, timeout=5,
        )
        results["unshare_mount_ns"] = {
            "return_code": r.returncode,
            "blocked": r.returncode != 0,
            "error": r.stderr.strip() if r.stderr else None,
        }
    except FileNotFoundError:
        results["unshare_mount_ns"] = {"error": "unshare not found"}
    except Exception as e:
        results["unshare_mount_ns"] = {"error": str(e)}

    # Vector 8: Docker socket
    docker_sock = "/var/run/docker.sock"
    sock_exists = os.path.exists(docker_sock)
    results["docker_socket"] = {"exists": sock_exists, "blocked": True}
    if sock_exists:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(docker_sock)
            s.close()
            results["docker_socket"]["connectable"] = True
            results["docker_socket"]["blocked"] = False
        except OSError:
            results["docker_socket"]["connectable"] = False

    return results


def probe_mountinfo() -> list[dict]:
    """
    Parse /proc/self/mountinfo (richer than /proc/mounts).
    Returns mount_root, mount_point, fstype, source, and options per entry.
    """
    info_path = "/proc/self/mountinfo"
    if not os.path.exists(info_path):
        return [{"error": "mountinfo not available"}]

    entries = []
    with open(info_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 7:
                continue
            # Fields: id parent major:minor root mount_point options ... - fstype source super_options
            try:
                sep = parts.index("-")
            except ValueError:
                continue
            entries.append({
                "mount_id": parts[0],
                "parent_id": parts[1],
                "device": parts[2],
                "mount_root": parts[3],
                "mount_point": parts[4],
                "options": parts[5],
                "fstype": parts[sep + 1] if sep + 1 < len(parts) else "unknown",
                "source": parts[sep + 2] if sep + 2 < len(parts) else "unknown",
            })
    return entries


# ─────────────────────────────────────────────
# SECTION 6 — /proc Mask Audit
# Run from inside the container.
# Identifies which /proc paths are masked vs readable, and the mask mechanism.
# ─────────────────────────────────────────────

# Docker's default masked paths (as of Docker 24+)
DOCKER_DEFAULT_MASKS = {
    "/proc/kcore", "/proc/keys", "/proc/timer_list", "/proc/sched_debug",
    "/proc/scsi", "/proc/acpi", "/sys/firmware",
}


def probe_proc_masks() -> dict:
    """
    Audit /proc and /sys for masked vs readable paths.
    Identifies the masking mechanism (char device, empty tmpfs, ro remount)
    and enumerates unmasked readable files.
    """
    result = {"masked": {}, "unmasked_readable": [], "mask_mechanisms": {}}

    # Identify tmpfs device for comparison
    try:
        dev_tmpfs = os.stat("/dev").st_dev
    except (FileNotFoundError, PermissionError):
        dev_tmpfs = None

    # Check known mask targets
    for p in DOCKER_DEFAULT_MASKS:
        entry = {"path": p, "exists": os.path.exists(p)}
        if os.path.exists(p):
            try:
                s = os.stat(p)
                mode = stat.filemode(s.st_mode)
                entry["mode"] = mode
                entry["device"] = s.st_dev
                entry["inode"] = s.st_ino

                if stat.S_ISCHR(s.st_mode):
                    entry["mechanism"] = "char_device_null"
                    entry["readable_bytes"] = 0
                elif stat.S_ISDIR(s.st_mode):
                    contents = os.listdir(p)
                    entry["mechanism"] = "empty_tmpfs" if len(contents) == 0 else "populated_dir"
                    entry["entry_count"] = len(contents)
                elif dev_tmpfs and s.st_dev == dev_tmpfs:
                    entry["mechanism"] = "tmpfs_overlay"
                else:
                    entry["mechanism"] = "unknown"
            except PermissionError:
                entry["mechanism"] = "permission_denied"

        result["masked"][p] = entry

    # Enumerate unmasked /proc files
    try:
        for name in sorted(os.listdir("/proc")):
            if name.isdigit():  # skip PIDs
                continue
            p = f"/proc/{name}"
            if p in DOCKER_DEFAULT_MASKS:
                continue
            try:
                if os.path.isfile(p):
                    with open(p, "rb") as f:
                        data = f.read(64)
                        if len(data) > 0:
                            result["unmasked_readable"].append({
                                "path": p,
                                "preview_bytes": len(data),
                            })
            except (PermissionError, OSError):
                pass
    except PermissionError:
        pass

    return result


def probe_proc_pid_leaks() -> dict:
    """
    Enumerate /proc/[pid]/fd, maps, and environ for information leaks.
    Reports open FDs pointing to non-standard paths and host path exposure
    in memory maps and environment variables.
    """
    result = {"fd_leaks": [], "maps_leaks": [], "environ_leaks": []}

    skip_fd_prefixes = ("/dev", "pipe:", "socket:", "anon_inode:", "/proc")

    for pid_dir in sorted(os.listdir("/proc")):
        if not pid_dir.isdigit():
            continue

        # FD enumeration
        fd_dir = f"/proc/{pid_dir}/fd"
        try:
            for fd in os.listdir(fd_dir):
                try:
                    target = os.readlink(f"{fd_dir}/{fd}")
                    if not any(target.startswith(p) for p in skip_fd_prefixes):
                        result["fd_leaks"].append({
                            "pid": pid_dir,
                            "fd": fd,
                            "target": target,
                        })
                except (PermissionError, FileNotFoundError, OSError):
                    pass
        except (PermissionError, FileNotFoundError):
            pass

        # Memory maps — host binary paths
        try:
            with open(f"/proc/{pid_dir}/maps") as f:
                seen_paths = set()
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 6:
                        mapped_path = parts[-1]
                        if (mapped_path.startswith("/")
                                and not mapped_path.startswith(("/lib", "/usr/lib", "["))
                                and mapped_path not in seen_paths):
                            seen_paths.add(mapped_path)
                            result["maps_leaks"].append({
                                "pid": pid_dir,
                                "path": mapped_path,
                            })
        except (PermissionError, FileNotFoundError):
            pass

        # Environment variables — host paths and config
        try:
            with open(f"/proc/{pid_dir}/environ", "rb") as f:
                env_data = f.read().decode("utf-8", errors="replace")
                for entry in env_data.split("\x00"):
                    if "=" in entry:
                        k, v = entry.split("=", 1)
                        if any(marker in v for marker in (":\\", "/mnt/host", "/host")):
                            result["environ_leaks"].append({
                                "pid": pid_dir,
                                "key": k,
                                "value": v[:120],
                            })
        except (PermissionError, FileNotFoundError):
            pass

    return result


# ─────────────────────────────────────────────
# SECTION 7 — Capability & Privilege Probe
# Run from inside the container.
# Decodes the effective capability bitmask and identifies security-relevant grants/denials.
# ─────────────────────────────────────────────

# Capability bit definitions (Linux UAPI, up to cap 31)
_CAP_NAMES = {
    0: "CAP_CHOWN", 1: "CAP_DAC_OVERRIDE", 2: "CAP_DAC_READ_SEARCH",
    3: "CAP_FOWNER", 4: "CAP_FSETID", 5: "CAP_KILL", 6: "CAP_SETGID",
    7: "CAP_SETUID", 8: "CAP_SETPCAP", 9: "CAP_LINUX_IMMUTABLE",
    10: "CAP_NET_BIND_SERVICE", 11: "CAP_NET_BROADCAST", 12: "CAP_NET_ADMIN",
    13: "CAP_NET_RAW", 14: "CAP_IPC_LOCK", 15: "CAP_IPC_OWNER",
    16: "CAP_SYS_MODULE", 17: "CAP_SYS_RAWIO", 18: "CAP_SYS_CHROOT",
    19: "CAP_SYS_PTRACE", 20: "CAP_SYS_PACCT", 21: "CAP_SYS_ADMIN",
    22: "CAP_SYS_BOOT", 23: "CAP_SYS_NICE", 24: "CAP_SYS_RESOURCE",
    25: "CAP_SYS_TIME", 26: "CAP_SYS_TTY_CONFIG", 27: "CAP_MKNOD",
    28: "CAP_LEASE", 29: "CAP_AUDIT_WRITE", 30: "CAP_AUDIT_CONTROL",
    31: "CAP_SETFCAP",
}

# Capabilities with high security impact inside a container
_SECURITY_CRITICAL_CAPS = {
    "CAP_SYS_ADMIN", "CAP_SYS_PTRACE", "CAP_SYS_RAWIO", "CAP_SYS_MODULE",
    "CAP_NET_ADMIN", "CAP_NET_RAW", "CAP_DAC_READ_SEARCH", "CAP_SYS_CHROOT",
}


def probe_capabilities() -> dict:
    """
    Read and decode the effective capability bitmask from /proc/self/status.
    Returns granted and denied capabilities with security annotations.
    """
    result = {"raw": {}, "granted": [], "denied": [], "security_notes": []}

    try:
        with open("/proc/self/status") as f:
            for line in f:
                for prefix in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
                    if line.startswith(prefix + ":"):
                        val = line.split(":")[1].strip()
                        result["raw"][prefix] = val
    except (FileNotFoundError, PermissionError) as e:
        result["error"] = str(e)
        return result

    cap_eff_hex = result["raw"].get("CapEff", "0")
    cap_eff = int(cap_eff_hex, 16)

    for bit, name in sorted(_CAP_NAMES.items()):
        entry = {"capability": name, "bit": bit}
        critical = name in _SECURITY_CRITICAL_CAPS

        if cap_eff & (1 << bit):
            entry["status"] = "granted"
            if critical:
                entry["security"] = "notable"
            result["granted"].append(entry)
        else:
            entry["status"] = "denied"
            if critical:
                entry["security"] = "key_denial"
            result["denied"].append(entry)

    # Security summary
    granted_names = {e["capability"] for e in result["granted"]}
    if "CAP_SYS_ADMIN" in granted_names:
        result["security_notes"].append("CAP_SYS_ADMIN granted — mount/unshare/namespace attacks possible")
    else:
        result["security_notes"].append("CAP_SYS_ADMIN denied — mount/namespace escape blocked")

    if "CAP_SYS_PTRACE" in granted_names:
        result["security_notes"].append("CAP_SYS_PTRACE granted — can attach to other processes")
    if "CAP_NET_RAW" in granted_names:
        result["security_notes"].append("CAP_NET_RAW granted — raw socket probing available")

    return result


# ─────────────────────────────────────────────
# SECTION 8 — Volume Mask Verification (IgnoreScope)
# Run from inside the container.
# Checks whether declared volume masks in IgnoreScope config are actually enforced.
# ─────────────────────────────────────────────

def probe_volume_masks(
    scope_config: str | None = None,
    mount_point: str | None = None,
) -> dict:
    """
    Load an IgnoreScope scope_docker_desktop.json and verify whether
    declared masks and reveals match actual container visibility.

    If scope_config is None, auto-discovers from <mount_point>/.ignore_scope/*/scope_docker_desktop.json.
    """
    if mount_point is None:
        mount_point = os.getcwd()
    result = {"mount_point": mount_point, "config_path": scope_config, "checks": []}

    # Auto-discover config
    if scope_config is None:
        scope_dir = os.path.join(mount_point, ".ignore_scope")
        if os.path.isdir(scope_dir):
            for sub in os.listdir(scope_dir):
                candidate = os.path.join(scope_dir, sub, "scope_docker_desktop.json")
                if os.path.isfile(candidate):
                    scope_config = candidate
                    result["config_path"] = scope_config
                    break

    if scope_config is None or not os.path.isfile(scope_config):
        result["error"] = "No IgnoreScope config found"
        return result

    with open(scope_config) as f:
        config = json.load(f)

    result["scope_version"] = config.get("version")
    result["scope_name"] = config.get("scope_name")

    local = config.get("local", {})

    # Extract masked/revealed from mount_specs (MountSpecPath format)
    masked_paths = []
    revealed_paths = []
    for ms in local.get("mount_specs", []):
        mount_root = ms.get("mount_root", ".")
        for pattern in ms.get("patterns", []):
            is_exception = pattern.startswith("!")
            folder = pattern.lstrip("!").rstrip("/")
            if folder.endswith("/**"):
                folder = folder[:-3]
            elif folder.endswith("/*"):
                folder = folder[:-2]
            if not folder:
                continue
            rel = f"{mount_root}/{folder}" if mount_root != "." else folder
            if is_exception:
                revealed_paths.append(rel)
            else:
                masked_paths.append(rel)

    # Check each masked path
    for rel in masked_paths:
        full = os.path.join(mount_point, rel)
        check = {"path": rel, "expected": "masked"}

        if not os.path.exists(full):
            check["actual"] = "not_found"
            check["pass"] = True  # not found = effectively masked
        elif os.path.isdir(full):
            entries = os.listdir(full)
            if len(entries) == 0:
                check["actual"] = "empty_directory"
                check["pass"] = True
            else:
                # Count files to quantify the leak
                file_count = 0
                total_size = 0
                for dirpath, dirs, files in os.walk(full):
                    file_count += len(files)
                    for fname in files:
                        try:
                            total_size += os.path.getsize(os.path.join(dirpath, fname))
                        except OSError:
                            pass
                check["actual"] = "fully_visible"
                check["pass"] = False
                check["file_count"] = file_count
                check["total_size_mb"] = round(total_size / 1024 / 1024, 1)
        else:
            check["actual"] = "visible_file"
            check["pass"] = False
            check["size"] = os.path.getsize(full)

        # Check if a submount masks this path
        try:
            path_dev = os.stat(full).st_dev
            mount_dev = os.stat(mount_point).st_dev
            check["on_mount_device"] = path_dev == mount_dev
            if path_dev != mount_dev:
                check["actual"] = "submount_masked"
                check["pass"] = True
        except (FileNotFoundError, PermissionError):
            pass

        result["checks"].append(check)

    # Check each revealed path
    for rel in revealed_paths:
        full = os.path.join(mount_point, rel)
        check = {"path": rel, "expected": "revealed"}

        if not os.path.exists(full):
            check["actual"] = "not_found"
            check["pass"] = False
        elif os.path.isdir(full):
            entries = os.listdir(full)
            check["actual"] = "visible" if len(entries) > 0 else "empty"
            check["pass"] = len(entries) > 0
            check["entry_count"] = len(entries)
        else:
            check["actual"] = "visible_file"
            check["pass"] = True

        result["checks"].append(check)

    # Summary
    passed = sum(1 for c in result["checks"] if c["pass"])
    total = len(result["checks"])
    result["summary"] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "all_enforced": passed == total,
    }

    return result


# ─────────────────────────────────────────────
# SECTION 9 — Test Result Runner
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

    print("[1/8] Identity...")
    report["identity"] = probe_identity()

    print("[2/8] Known mount points...")
    report["mounts_probed"] = probe_known_mounts()

    print("[3/8] Host network...")
    report["host_dns"] = probe_host_dns()
    if report["host_dns"].get("resolved"):
        report["host_ports"] = probe_host_ports()
        report["mcp_gateway"] = probe_mcp_gateway()
    else:
        report["host_ports"] = "skipped (DNS failed)"
        report["mcp_gateway"] = "skipped (DNS failed)"

    print("[4/8] Mount table...")
    report["proc_mounts"] = probe_mounts()
    report["mountinfo"] = probe_mountinfo()

    print("[5/8] Device topology & mount escape tests...")
    report["device_topology"] = probe_device_topology()
    report["mount_escape"] = probe_mount_escape()

    print("[6/8] /proc mask audit...")
    report["proc_masks"] = probe_proc_masks()
    report["proc_pid_leaks"] = probe_proc_pid_leaks()

    print("[7/8] Capabilities...")
    report["capabilities"] = probe_capabilities()

    print("[8/8] Volume mask verification...")
    # Use cwd as mount point — docker-compose sets working_dir to project root
    report["volume_masks"] = probe_volume_masks(mount_point=os.getcwd())

    print("\n=== Report ===\n")
    print(json.dumps(report, indent=2, default=str))

    # Optionally write to shared results folder if it exists
    out_path = "/results/probe_report.json"
    if os.path.exists(os.path.dirname(out_path)):
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport also written to {out_path}")
