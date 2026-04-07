# MIRRORED_ALGORITHM.md

Design document for the mirrored intermediate directory computation.

> **Note (MountSpecPath integration):** The walk functions still receive flat `masked`, `revealed`, `mounts` sets as parameters. Callers (`_process_root()` in hierarchy.py) extract these sets from `mount_specs` at the call site via `ms.get_masked_paths()` / `ms.get_revealed_paths()`. The walk algorithm itself is unchanged.

---

## Architecture: Unified Walk + Two Consumers

Mirrored intermediates are computed by a single internal walk function
`_walk_mirrored_intermediates()` that accepts an optional `ceiling` parameter.
Two consumers call it with different ceilings:

```
hierarchy.py:
  _walk_mirrored_intermediates(masked, revealed, mounts, ceiling=None, pushed_files=None)
    ├─ ceiling=None  → per-mask ceiling (container mkdir -p)
    └─ ceiling=Path  → fixed ceiling (GUI tree inclusion)

  _compute_mirrored_parents(pushed_files=None)   → delegates ceiling=None → container paths
  compute_mirrored_intermediate_paths(ceiling=, pushed_files=None) → delegates to walk → host paths
```

Walk logic (three loops):
```
  # Walk 1: Reveal-to-ceiling (mask-to-reveal intermediates)
  effective_ceiling = ceiling if ceiling is not None else mask
  current = reveal.parent
  while current != effective_ceiling and is_descendant(current, effective_ceiling):
      add(current)
      current = current.parent

  # Walk 2: Mount-parent walk (structural ancestors of bind mounts)
  # Only in GUI-ceiling mode — container mkdir-p doesn't need these
  if ceiling is not None:
      for mount in mounts:
          current = mount.parent
          while current != ceiling and is_descendant(current, ceiling):
              add(current)
              current = current.parent

  # Walk 3: Pushed-to-ceiling (mask-to-pushed-file intermediates)
  # Identical logic to Walk 1 but for pushed files instead of reveals.
  # Pushed files under a mask with a valid mount walk from
  # pushed.parent up to effective ceiling.
  if pushed_files:
      for pushed in pushed_files:
          # find mask, verify mount, walk pushed.parent → ceiling
```

---

## Ceiling Matrix (Resolved)

```
                    Container mkdir -p       GUI tree inclusion
                    ------------------       ------------------
Ceiling             mask (per-mask)          host_container_root (exclusive)
                                             = host_project_root.parent

Rationale           Docker auto-creates      Full structural path from
                    bind mount targets.      project root down to reveals.
                    Only intermediates        Includes dirs above mount
                    between mask and          boundary so ScopeView shows
                    reveal need mkdir -p.    unbroken tree structure.
```

### Resolved Answers

**Q1: Docker auto-creates bind mount targets** — confirmed. Container ceiling = mask.

**Q2: GUI ceiling is `host_project_root.parent` (exclusive)** — the project root
itself is the tree root node (always visible), so it does not need mirrored
visibility. Its parent serves as the exclusive walk boundary.

**Q3: One walk function, two consumers** — `_walk_mirrored_intermediates()` is the
shared core. Container consumer calls with `ceiling=None` (per-mask). GUI consumer
calls with `ceiling=host_project_root.parent`.

---

## Example: Full GUI Walk

```
host_project_root.parent/   ← GUI ceiling (exclusive) — NOT included
  host_project_root/        ← Stage 2b: hidden→virtual
    SubDir/                 ← Stage 2b: hidden→virtual
      Content/              ← mount (visible — Stage 1)
        Stuff/              ← mask (virtual — Stage 2, has revealed descendant)
          Internal/         ← Stage 2: masked→virtual (has revealed descendant)
            Handlers/       ← Stage 2: masked→virtual (has revealed descendant)
              Public/       ← reveal (revealed — Stage 1)
```

Container walk (ceiling=None → per-mask):
Result: `{Internal, Handlers}` — only dirs between mask and reveal.

GUI walk (ceiling=host_project_root.parent):
Result: `{host_project_root, SubDir, Content, Stuff, Internal, Handlers}`

---

## Visibility Pipeline Stages

### Stage 1: Per-Node MatrixState
Pure boolean flag computation → visibility from truth table.
Paths above mount boundary get "hidden".

### Stage 2: Config-Native Virtual Detection (refactored)
No tree walks. Three checks per masked/hidden path:

- **Check 1 (within-mount):** `owning_spec.has_exception_descendant(path)` — pattern string scan
- **Check 2 (any path):** `config.has_pushed_descendant(path)` — pushed_files scan
- **Check 3 (above-mount):** any `mount_root` is descendant of path — mount_specs scan

Dual computation: config queries (primary) + inverse pattern derivation via
`MountSpecPath.get_virtual_paths()` (cross-reference with discrepancy logging).

Replaces the former tree-walk `find_mirrored_paths()` and subsumes Stage 2b.

### Stage 3: Config-Native Descendant Flags (refactored)
- `has_pushed_descendant` via `config.has_pushed_descendant(path)` — no tree walk
- `has_direct_visible_child` via single-pass parent collection (s.revealed or s.pushed)

---

## Data Flow

```
mount_data_tree._recompute_states()
  │
  ├─ config = LocalMountConfig(mount_specs, pushed_files, mirrored)
  │
  ├─ IF mirrored AND host_project_root:
  │    mirrored_intermediates = compute_mirrored_intermediate_paths(
  │        config.masked, config.revealed, config.mounts,
  │        ceiling=host_project_root.parent)
  │  ELSE:
  │    mirrored_intermediates = set()
  │    (path inclusion only — virtual detection is in CORE)
  │
  ├─ all_paths = _collect_all_paths(mirrored_intermediates)
  │    └─ tree nodes ∪ config sets ∪ mirrored_intermediates
  │
  └─ apply_node_states_from_scope(config, all_paths)
       ├─ Stage 1: per-node MatrixState
       ├─ Stage 2: config-native virtual detection (Checks 1/2/3)
       │    + inverse pattern cross-reference
       └─ Stage 3: config-native descendant flags
```

---

## Files

| File | Role |
|---|---|
| `core/hierarchy.py` | `_walk_mirrored_intermediates()` — path inclusion (GUI tree + container mkdir) |
| `core/node_state.py` | `_compute_virtual_paths_from_config()` — config-native virtual detection (Checks 1/2/3) |
| `core/mount_spec_path.py` | `has_exception_descendant()`, `get_virtual_paths()` — pattern queries + inverse derivation |
| `core/local_mount_config.py` | `has_pushed_descendant()` — pushed files descendant query |
| `gui/mount_data_tree.py` | Orchestrator — computes intermediates for path inclusion, delegates virtual detection to CORE |
