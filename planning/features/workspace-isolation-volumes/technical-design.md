# Technical Design: Workspace Isolation Volumes

## Overview

Extensions become tracked `LocalMountConfig` entries in config with a `state` lifecycle field. Install paths are backed by Layer 4 isolation volumes (named Docker volumes that overlay all other mounts). Live View's scan framework detects discrepancies between desired state (config) and actual state (container), triggering reconciliation actions.

## Architecture

### Declarative Reconciliation Loop

```
 scope_docker_desktop.json              Container (actual)
 (desired state)                        (scanned state)
         |                                     |
         +-----------> LIVE VIEW SCAN <--------+
                            |
                      DISCREPANCY?
                       /    |    \
                      /     |     \
               deploy +   installed   remove +
               missing    + present    present
                 |           |           |
            RUN INSTALL    NO-OP     UNINSTALL
                 |                      |
            state →                 state →
            'installed'             (remove entry)
```

### Extension State Machine

```
User clicks Install → state = 'deploy'
                          |
                     container start
                     live scan detects
                     binary missing
                          |
                     run install cmds
                          |
                     verify success
                          |
                     state = 'installed'
                          |
              +-----------+-----------+
              |                       |
         Update Container        Recreate Container
         volumes survive         volumes destroyed
         binary present          binary missing
         state = 'installed'     state = 'installed'
              |                       |
         scan: match             scan: mismatch
         → no-op                 → re-deploy
```

### Volume Layer Stacking

```
Layer 1: Bind Mounts         host dir → container path (base visibility)
Layer 2: Mask Volumes         empty named volume overlays Layer 1 (hide)
Layer 3: Revealed Mounts      host dir re-mounted over Layer 2 (punch-through)
Layer 4: Isolation Volumes    named volume overlays everything (persist + isolate)
```

Layer 4 is the **final overlay**. Nothing punches through isolation.

## Data Model Changes

### `LocalMountConfig` — Add state field

```python
# core/local_mount_config.py
@dataclass
class LocalMountConfig:
    mounts: set[Path]
    masked: set[Path]
    revealed: set[Path]
    pushed_files: set[Path]
    state: str = ""  # NEW: "", "deploy", "installed", "remove"
```

`state` is empty string for project/sibling configs (not extension-managed). Only extension entries use the lifecycle states.

### `ScopeDockerConfig` — Add extensions list

```python
# core/config.py
@dataclass
class ScopeDockerConfig:
    ...
    extensions: list[ExtensionConfig] = field(default_factory=list)  # NEW
```

Where `ExtensionConfig` wraps `LocalMountConfig` with extension metadata:

```python
@dataclass
class ExtensionConfig(LocalMountConfig):
    name: str = ""              # "claude", "git", "p4-mcp"
    installer_class: str = ""   # "ClaudeInstaller", "GitInstaller", "P4McpInstaller"
    isolation_paths: list[str] = field(default_factory=list)  # Container paths needing volumes
    seed_method: str = "empty"  # "empty" or "clone" per path
```

### JSON Serialization

```json
{
  "extensions": [
    {
      "name": "claude",
      "state": "installed",
      "installer_class": "ClaudeInstaller",
      "isolation_paths": ["/root/.local/bin", "/root/.local/lib"],
      "seed_method": "empty"
    },
    {
      "name": "git",
      "state": "installed",
      "installer_class": "GitInstaller",
      "isolation_paths": ["/usr/bin", "/usr/lib/git-core"],
      "seed_method": "empty"
    }
  ]
}
```

## Dependencies

### Internal (modify)
| File | Change |
|------|--------|
| `core/local_mount_config.py` | Add `state` field |
| `core/config.py` | Add `ExtensionConfig`, `extensions` list to `ScopeDockerConfig` |
| `core/hierarchy.py` | Add Layer 4 isolation volume computation to `_compute_volume_entries()` |
| `docker/compose.py` | Generate Layer 4 volumes in compose.yml |
| `docker/container_lifecycle.py` | Reconciliation phase after container start |
| `container_ext/install_extension.py` | `deploy_runtime()` updates config state on success |
| `gui/display_config.py` | Add [Isolate] column definition |
| `gui/mount_data_tree.py` | Track isolation paths in tree state |

### Internal (reuse as-is)
| File | What |
|------|------|
| `container_ext/install_extension.py` | `deploy_runtime()` — install commands already defined per extension |
| `docker/container_ops.py` | `scan_container_directory()` — already implemented, never called |
| `docker/container_ops.py` | `push_file_to_container()` — directory support already added |
| `core/node_state.py` | `container_only` field + visibility — already added |
| `gui/display_config.py` | CONTAINER_ONLY state + gradient — already added |

### Ordering
1. Config schema changes (ExtensionConfig, state field)
2. Hierarchy + compose generation (Layer 4)
3. Lifecycle reconciliation (scan + deploy/skip/remove)
4. GUI [Isolate] column
5. Remove/uninstall UX (deferred)

## DRY Audit

### Clone Risk: LocalMountConfig Consumers

`LocalMountConfig` is now used by three consumers:
- `ScopeDockerConfig` (project root)
- `SiblingMount` (external directories)
- `ExtensionConfig` (extension install paths) — NEW

**Audit point:** Hierarchy computation (`_process_root()`) processes mounts/masked/revealed per root. Extension isolation paths are NOT mounts/masks — they're a new volume type. Must NOT be processed through the existing mask pipeline. Separate code path in `_compute_volume_entries()` for Layer 4.

### Clone Risk: Extension Install + State Update

Each extension installer calls `deploy_runtime()` (single method in base class). State update (`deploy` → `installed`) should happen in the base class after successful deploy, NOT duplicated in each concrete installer.

**Solution:** `ExtensionInstaller.deploy_runtime()` returns `DeployResult`. The caller (lifecycle reconciler or GUI handler) updates config state in ONE place after checking result.

### Clone Risk: Compose Volume Generation

Auth volume, mask volumes, and isolation volumes are all "named volume entries in compose.yml." Currently auth is special-cased in `generate_compose_with_masks()`.

**Audit point:** Don't add another special case for isolation. Refactor to: all named volumes (auth + mask + isolation) generated from a unified list. Auth becomes just another entry in that list.

## Alternatives Considered

| Approach | Rejected Because |
|----------|-----------------|
| Warn + manual re-install | User must remember and repeat. Doesn't solve the persistence problem. |
| Bake into Docker image (Dockerfile RUN) | Ties extensions to build time. Can't add/remove without image rebuild. Breaks user-initiated install pattern. |
| Persist in writable layer via docker commit | Creates snowflake containers. Breaks reproducibility. Docker anti-pattern. |
| Volume per file (fine-grained) | Too many volumes. Docker has practical limits. Directory-level is correct granularity. |

## Risks

- **Volume path granularity** — Git installs across `/usr/bin/`, `/usr/lib/git-core/`, `/usr/share/git-core/`. Isolating all of `/usr/bin/` is too broad. May need per-extension path lists.
- **Apt-get + isolation** — `apt-get install git` writes to system paths. Volume must exist before install runs, but compose creates it empty. Install fills it. Works, but first `apt-get` in an empty `/usr/bin/` volume would fail (missing system binaries). May need clone-from-image seed for system paths.
- **Layer 4 ordering** — isolation volumes must come AFTER reveals in compose. Hierarchy computation must enforce this ordering.
