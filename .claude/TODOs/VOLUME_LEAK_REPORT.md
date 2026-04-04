# VOLUME_LEAK_REPORT.md

Container security analysis of Docker Desktop volume masking for IgnoreScope v0.1.4.
Conducted 2026-03-25 from inside the running container.

---

## 1. Primary Goal: File Content Protection Below a Mount

**Verdict: PASS — all 14 tested escape vectors fail.**

The 9p mount at `/FPS_GBuffer/URP_Vanilla` correctly confines access to the project subtree. The host drive `E:\` is shared to the 9p server but the kernel VFS mount root binding restricts visibility to `/Unity_Fab/FPS_GBuffer/URP_Vanilla` only.

### Mount topology

```
mountinfo: mount_root=/Unity_Fab/FPS_GBuffer/URP_Vanilla
           mount_point=/FPS_GBuffer/URP_Vanilla
           9p aname=drvfs;path=E:\
```

The 9p server exposes `path=E:\` (entire drive). The kernel binds only the subtree as the visible root.

### Device boundary map

| Device | Filesystem | Paths |
|---|---|---|
| 73 | 9p (drvfs) | `/FPS_GBuffer/URP_Vanilla` |
| 95 | overlay | `/`, `/root`, `/FPS_GBuffer`, `/tmp`, `/etc` |
| 122 | proc | `/proc` |
| 123 | tmpfs | `/dev` |
| 125 | sysfs | `/sys` |
| 2112 | ext4 | `/root/.claude`, `/etc/resolv.conf`, `/etc/hostname`, `/etc/hosts` |

### Escape vector results

| # | Vector | Source | Result |
|---|---|---|---|
| 1 | `..` path traversal from mount | container_probe.py | **BLOCKED** — crosses device boundary to overlay (dev 95) |
| 2 | Symlink inside mount pointing outside | Generated | Reads overlay content, not host files |
| 3 | Hardlink across device boundary | Generated | **BLOCKED** — `EXDEV` (cross-device link) |
| 4 | `/proc/self/root` alternate traversal | Generated | Reaches overlay, not host |
| 5 | Alternate mount paths (`/mnt/host`, `/mnt/e`) | container_probe.py | Not found — not mounted into container |
| 6 | `symlinkroot=/mnt/host/` exploitation | Generated | `/mnt` exists but empty on overlay |
| 7 | `openat(mount_fd, "..")` syscall | Generated | **BLOCKED** — crosses to overlay |
| 8 | Write access probe | Generated | rw confirmed but scoped to subtree |
| 9 | `mountinfo` root analysis | container_probe.py | Reveals host path structure (metadata only) |
| 10 | Capability check for remount | Generated | **No CAP_SYS_ADMIN** — cannot remount |
| 11 | `mount(2)` with broader 9p root | Generated | **EPERM** — permission denied |
| 12 | `unshare -m` new mount namespace | Generated | **EPERM** — no CAP_SYS_ADMIN |
| 13 | Direct `mount(2)` syscall via ctypes | Generated | **EPERM** |
| 14 | Docker socket for sibling container | Generated | `/var/run/docker.sock` not mounted |

### Three interlocking layers that hold

**Layer 1 — VFS mount root binding:** Every path resolution within the 9p mount is relative to the bound subtree root. `..` at the boundary crosses back to the parent device (overlay). Enforced in kernel `follow_dotdot()`.

**Layer 2 — Capability denial:** `CAP_SYS_ADMIN` dropped. Prevents `mount(2)`, `unshare(CLONE_NEWNS)`, `pivot_root`. Cannot create a new 9p mount with a broader root.

**Layer 3 — No alternate access paths:** `/mnt/host` absent. No Docker socket. No `CAP_SYS_PTRACE`. No raw block device access (`CAP_SYS_RAWIO` dropped, `/dev/sde` not visible).

### Metadata leak (informational, not content)

`/proc/self/mountinfo` reveals the full host path `E:\Unity_Fab\FPS_GBuffer\URP_Vanilla`, mount options including `uid`, `gid`, `symlinkroot`. An attacker learns the host path structure but cannot act on it from inside.

---

## 2. Secondary Goal: Hiding Specified Folder Content Below a Mount

**Verdict: FAIL — no folder hiding mechanism succeeded.**

### IgnoreScope configuration vs reality

`scope_docker_desktop.json` declares:

```json
{
  "masked": [
    "Library",
    "Library/PackageCache/com.unity.burst@1.8.21",
    "Library/PackageCache/com.unity.cinemachine@2.10.3",
    "Library/PackageCache/com.unity.collab-proxy@2.10.2"
  ],
  "revealed": [
    "Library/PackageCache"
  ]
}
```

`docker-compose.yml` emits only:

```yaml
volumes:
  - "E:/Unity_Fab/FPS_GBuffer/URP_Vanilla:/FPS_GBuffer/URP_Vanilla"
```

No mask volumes. No reveal re-binds.

### Exposure of masked paths

| Intended Mask | Status | Files | Size |
|---|---|---|---|
| `Library/` | **FULLY VISIBLE** | 38,448 | 3,654 MB |
| `Library/PackageCache/com.unity.burst@1.8.21/` | **FULLY VISIBLE** | 330 | 1,128 MB |
| `Library/PackageCache/com.unity.cinemachine@2.10.3/` | **FULLY VISIBLE** | 945 | 28 MB |
| `Library/PackageCache/com.unity.collab-proxy@2.10.2/` | **FULLY VISIBLE** | 1,679 | 23 MB |

### Mount table confirmation

27 mounts in the container. **1** under `/FPS_GBuffer`:

```
/FPS_GBuffer/URP_Vanilla    9p    E:\
```

No submounts. No tmpfs overlays. No empty volumes over subpaths.

### Broken steps (see VOLUME_OVERLAY_FIX.md)

1. Config authored correctly
2. **Compose generator drops masks** — only processes `local.mounts`, ignores `local.masked`
3. **No volume ordering logic** — masks must layer: base > masks > reveals > sub-masks
4. **Named volumes for masks not declared** — top-level `volumes:` block incomplete
5. **Compose file never executed** — container launched by Docker Desktop directly

---

## 3. /proc Volume Masks

**Verdict: PARTIAL — masks work on 7 paths, 36 files leak host metadata.**

### Masked paths (effective)

| Path | Mechanism | Bypass? |
|---|---|---|
| `/proc/kcore` | char device (inode 5, `crw-rw-rw-`) | No — reads 0 bytes |
| `/proc/keys` | char device | No |
| `/proc/timer_list` | char device | No |
| `/proc/interrupts` | char device | No |
| `/proc/acpi` | empty tmpfs overlay | No — lists empty |
| `/proc/scsi` | empty tmpfs overlay | No |
| `/sys/firmware` | empty tmpfs overlay | No |

### Unmasked paths (leaking host metadata)

36 readable `/proc` files not covered by any mask:

| Path | Leak |
|---|---|
| `/proc/kallsyms` | Kernel symbol addresses (KASLR defeat) |
| `/proc/config.gz` | Full kernel build configuration |
| `/proc/cpuinfo` | Host CPU model, core count, flags |
| `/proc/meminfo` | Host total RAM (32 GB) |
| `/proc/version` | Exact kernel version + build toolchain |
| `/proc/cmdline` | WSL kernel boot args and debug flags |
| `/proc/diskstats` | Host disk topology |
| `/proc/self/mountinfo` | Full container mount table with host paths |
| `/proc/buddyinfo` | Memory allocator state |
| `/proc/crypto` | Available kernel crypto modules |
| `/proc/devices` | Character/block device registrations |
| `/proc/filesystems` | Supported filesystem types |
| `/proc/iomem` | I/O memory map |
| `/proc/ioports` | I/O port allocations |
| `/proc/consoles` | Console device info |

**Root cause:** Docker masks a hardcoded denylist of ~7 paths. Everything else in `/proc` is readable. This is a denylist applied to an allowlist problem.

### /proc/[pid] information leaks

| Path | Content |
|---|---|
| `/proc/[pid]/fd/` | Open file descriptors — reveals all files held open by all processes |
| `/proc/[pid]/maps` | Memory-mapped file paths — reveals host binary locations |
| `/proc/[pid]/environ` | Process environment variables |
| `/proc/[pid]/mountinfo` | Per-process mount table |

---

## 4. Capability Profile

Effective capabilities: `0x00000000a80425fb`

### Granted (14)

| Capability | Risk |
|---|---|
| CAP_CHOWN | Low |
| CAP_DAC_OVERRIDE | Medium — bypasses file read/write permission checks |
| CAP_FOWNER | Low |
| CAP_FSETID | Low |
| CAP_KILL | Low (container-scoped) |
| CAP_SETGID | Low |
| CAP_SETUID | Low |
| CAP_SETPCAP | Low |
| CAP_NET_BIND_SERVICE | Low |
| CAP_NET_RAW | Medium — raw sockets, network probing |
| CAP_SYS_CHROOT | Low (not exploitable without CAP_SYS_ADMIN) |
| CAP_MKNOD | Low |
| CAP_AUDIT_WRITE | Low |
| CAP_SETFCAP | Low |

### Denied (key)

| Capability | What it blocks |
|---|---|
| **CAP_SYS_ADMIN** | mount(2), unshare, pivot_root, namespace creation |
| **CAP_SYS_PTRACE** | Process attachment, cross-process memory access |
| **CAP_SYS_RAWIO** | Raw block device reads |
| **CAP_SYS_MODULE** | Kernel module loading |
| CAP_NET_ADMIN | Network configuration changes |
| CAP_DAC_READ_SEARCH | Bypassing directory read permission |

---

## 5. Network Boundary

| Target | Result |
|---|---|
| `host.docker.internal` DNS | Resolves to `192.168.65.254` |
| Port 2375 (Docker daemon) | Closed |
| Port 2376 (Docker TLS) | Closed |
| Port 8811 (MCP Gateway) | Closed |
| `/var/run/docker.sock` | Not mounted |

Network escape path sealed. DNS resolution leaks host IP but no services are reachable.

---

## 6. Methods Used

### From container_probe.py (8 functions)

| Function | Lines | Purpose | What it found |
|---|---|---|---|
| `probe_identity()` | 29-60 | Container confirmation, env vars | `.dockerenv` present, env filtered |
| `probe_known_mounts()` | 63-91 | Check hardcoded mount paths | `/mnt` accessible but empty |
| `probe_host_dns()` | 114-120 | Resolve `host.docker.internal` | Resolves to 192.168.65.254 |
| `probe_host_ports()` | 123-138 | TCP scan host ports | All scanned ports closed |
| `probe_mcp_gateway()` | 141-162 | HTTP probe MCP Gateway | Unreachable |
| `walk_filesystem()` | 171-202 | `os.walk` with cycle detection | Informed walk pattern for mask verification |
| `probe_mount_scope()` | 205-250 | `st_dev` comparison, `..` traversal | Mount confinement confirmed |
| `probe_mounts()` | 282-302 | Parse `/proc/mounts` | Revealed `aname=drvfs;path=E:\` — full drive shared |

Also informed by `check_symlink_types()` (lines 253-273) for symlink classification approach.

### Generated during analysis (14 additional methods)

| Method | What it exposed |
|---|---|
| Device ID mapping across all paths | Full 6-device topology of the container |
| `/proc` mask mechanism identification | char device (inode 5) vs empty tmpfs — two distinct mask types |
| Unmasked `/proc` file enumeration | 36 readable files Docker doesn't mask |
| `/proc/[pid]/fd` traversal | Open FDs to credentials, history, session files |
| `/proc/[pid]/maps` + `/proc/[pid]/environ` | Host binary paths, environment variable leakage |
| `openat(mount_fd, "..")` FD-relative escape | Confirmed VFS enforces boundary at syscall level |
| Symlink creation attack | Symlinks resolve to overlay, not host |
| Hardlink cross-device attempt | `EXDEV` — blocked by kernel |
| `/proc/self/root` + `/proc/1/root` traversal | Both resolve to overlay |
| Capability bitmask decode | 14 granted, 4 critical denials identified |
| `mount(2)` via ctypes | EPERM — syscall-level enforcement confirmed |
| `unshare -m` namespace escape | EPERM — no CAP_SYS_ADMIN |
| Docker socket probe | Not mounted |
| IgnoreScope mask path verification | All 4 masked paths fully visible, 38k+ files / 3.6 GB exposed |

### Attribution summary

| Source | Count | Focus |
|---|---|---|
| container_probe.py | 8 functions | Reconnaissance — identity, mount topology, host reachability, device boundaries |
| Generated | 14 methods | Attack vectors — syscall escapes, capability analysis, FD traversal, /proc audit, mask verification |

`container_probe.py` established the surface area. The generated methods tested whether each surface could be breached, and audited what the probe never covered (the `/proc` mask gap, FD-based credential access, IgnoreScope implementation failure).

---

## 7. Overall Scorecard

| Protection Goal | Mechanism | Result |
|---|---|---|
| Host file content below mount | VFS mount namespace + capability denial | **PASS** |
| Folder hiding within mount | IgnoreScope volume overlay masks | **FAIL** — never applied |
| `/proc` sensitive files | char device + tmpfs masks | **PARTIAL** — 7 masked, 36 leak |
| Network isolation | Port closure + no Docker socket | **PASS** |
| Capability restriction | Dropped CAP_SYS_ADMIN/PTRACE/RAWIO/MODULE | **PASS** |
| FD-based information access | (no protection) | **FAIL** — credentials readable via `/proc/pid/fd` |
| Host metadata exposure | (no protection beyond 7 masks) | **FAIL** — kernel version, CPU, RAM, symbols exposed |
