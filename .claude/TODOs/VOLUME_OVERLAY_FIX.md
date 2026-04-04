# VOLUME_OVERLAY_FIX.md

Volume masking for IgnoreScope v0.1.4 is non-functional. The `scope_docker_desktop.json` config declares masks, but the `docker-compose.yml` generator never emits them. All masked paths are fully visible inside the container.

---

## Step-by-step breakdown

### Step 1: Config authored correctly

`scope_docker_desktop.json` declares intent:

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

**Status: OK** — the mask/reveal hierarchy is well-formed.

### Step 2: Compose generation drops masks (BROKEN)

The generator emits only the base bind mount:

```yaml
volumes:
  - "E:/Unity_Fab/FPS_GBuffer/URP_Vanilla:/FPS_GBuffer/URP_Vanilla"
```

The `masked` and `revealed` arrays are never translated into volume entries.

**Root cause:** The compose generator reads the config but only processes `local.mounts`. It does not iterate `local.masked` to emit overlay volumes, nor does it handle the `local.revealed` re-punch-through.

**Fix:** After emitting the base bind mount, iterate `local.masked` and emit an empty named volume over each masked path. Then iterate `local.revealed` and emit a bind mount that re-exposes the host path beneath the mask.

### Step 3: Mask ordering (BROKEN)

Docker compose volume order matters. Masks must be declared **after** the base mount. Reveals must come **after** the mask they punch through. The current generator has no ordering logic because it emits no masks at all.

**Fix:** Emit volumes in this order:
1. Base bind mount (project root)
2. Mask volumes (broadest first — `Library` before `Library/PackageCache/...`)
3. Reveal volumes (re-bind the host subpath over the mask)

### Step 4: Named volumes for masks not declared (BROKEN)

Each mask directory needs an empty named volume. The `volumes:` top-level block only declares `urp_vanilla__dev-claude-auth`. No mask volumes are declared.

**Fix:** Generate a named volume for each masked path.

### Step 5: Container not launched from this compose file (BROKEN)

The actual running container was launched by Docker Desktop / Claude Code with a single bind mount. The IgnoreScope compose file sits inert on disk — it was never executed.

**Fix:** Either integrate IgnoreScope compose generation into the Claude Code container launch pipeline, or provide a separate launch script that uses this compose file.

---

## Fixed docker-compose.yml

```yaml
name: urp_vanilla__dev

services:
  claude:
    container_name: urp_vanilla__dev
    image: urp_vanilla__dev:latest
    build: .
    volumes:
      # === Auth volume ===
      - "urp_vanilla__dev-claude-auth:/root/.claude"

      # === 1. Base bind mount (project root) ===
      - "E:/Unity_Fab/FPS_GBuffer/URP_Vanilla:/FPS_GBuffer/URP_Vanilla"

      # === 2. Masks (empty volumes hide host content) ===
      # Order: broadest path first
      - "mask_library:/FPS_GBuffer/URP_Vanilla/Library"

      # === 3. Reveals (re-bind host subpaths through the mask) ===
      # This punches PackageCache back through the Library mask
      - "E:/Unity_Fab/FPS_GBuffer/URP_Vanilla/Library/PackageCache:/FPS_GBuffer/URP_Vanilla/Library/PackageCache"

      # === 4. Sub-masks (hide specific packages within the revealed path) ===
      - "mask_burst:/FPS_GBuffer/URP_Vanilla/Library/PackageCache/com.unity.burst@1.8.21"
      - "mask_cinemachine:/FPS_GBuffer/URP_Vanilla/Library/PackageCache/com.unity.cinemachine@2.10.3"
      - "mask_collab:/FPS_GBuffer/URP_Vanilla/Library/PackageCache/com.unity.collab-proxy@2.10.2"

    working_dir: /FPS_GBuffer/URP_Vanilla
    stdin_open: true
    tty: true

volumes:
  urp_vanilla__dev-claude-auth:
    name: urp_vanilla__dev-claude-auth
  mask_library:
    name: urp_vanilla__dev-mask-library
  mask_burst:
    name: urp_vanilla__dev-mask-burst
  mask_cinemachine:
    name: urp_vanilla__dev-mask-cinemachine
  mask_collab:
    name: urp_vanilla__dev-mask-collab
```

### Why this works

Docker processes volumes in declaration order. Each subsequent mount overlays the previous:

```
Layer 1:  E:/...URP_Vanilla  ->  /FPS_GBuffer/URP_Vanilla     (full project)
Layer 2:  empty volume       ->  .../Library                   (hides Library/)
Layer 3:  E:/.../PackageCache -> .../Library/PackageCache      (re-exposes PackageCache)
Layer 4:  empty volumes      ->  .../PackageCache/com.unity.*  (hides specific packages)
```

Container sees:
- `/FPS_GBuffer/URP_Vanilla/Assets/` — visible (not masked)
- `/FPS_GBuffer/URP_Vanilla/Library/` — empty (masked)
- `/FPS_GBuffer/URP_Vanilla/Library/PackageCache/` — visible (revealed)
- `/FPS_GBuffer/URP_Vanilla/Library/PackageCache/com.unity.burst@1.8.21/` — empty (sub-masked)

---

## Verification after fix

Run inside the container:

```bash
python3 -c "
import os
mount = '/FPS_GBuffer/URP_Vanilla'
checks = {
    'Library':                                          'should be empty (masked)',
    'Library/PackageCache':                             'should have entries (revealed)',
    'Library/PackageCache/com.unity.burst@1.8.21':      'should be empty (sub-masked)',
    'Library/PackageCache/com.unity.cinemachine@2.10.3': 'should be empty (sub-masked)',
    'Assets':                                           'should have entries (not masked)',
}
for rel, expect in checks.items():
    full = os.path.join(mount, rel)
    if os.path.isdir(full):
        count = len(os.listdir(full))
        status = 'empty' if count == 0 else f'{count} entries'
        print(f'{rel}: {status}  ({expect})')
    else:
        print(f'{rel}: not found  ({expect})')
"
```

---

## Generator fix pseudocode

The compose generator must be patched to process masks and reveals:

```python
def generate_volumes(config, host_project_path, container_project_path):
    volumes = []
    named_volumes = {}

    # 1. Base bind mount
    volumes.append(f"{host_project_path}:{container_project_path}")

    # 2. Masks — sorted by path depth (shallowest first)
    masked = sorted(config["local"]["masked"], key=lambda p: p.count("/"))
    for rel_path in masked:
        vol_name = slugify(f"mask-{rel_path}")
        container_path = f"{container_project_path}/{rel_path}"
        volumes.append(f"{vol_name}:{container_path}")
        named_volumes[vol_name] = {}

    # 3. Reveals — sorted by path depth (shallowest first)
    revealed = sorted(config["local"].get("revealed", []), key=lambda p: p.count("/"))
    for rel_path in revealed:
        host_path = f"{host_project_path}/{rel_path}"
        container_path = f"{container_project_path}/{rel_path}"
        volumes.append(f"{host_path}:{container_path}")

    # 4. Re-apply any masks that are children of revealed paths
    #    (already handled if masked list is complete and sorted after reveals)

    return volumes, named_volumes
```

Key requirement: volume entries must be emitted in this exact order — base, masks, reveals, sub-masks — because Docker applies them as a stack.
