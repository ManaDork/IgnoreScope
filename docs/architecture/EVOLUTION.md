# Mount/Isolation System — Evolution

**Purpose:** Narrate, in one page, how IgnoreScope's mount and isolation model arrived at its current shape. Read this if you're confused why STENCIL exists, why `delivery` is per-spec, why "isolation" is a compound term, or why blueprint prose deliberately avoids historical narrative.

**Audience:** Contributors approaching the codebase for the first time who encounter overlapping vocabulary in `ARCHITECTUREGLOSSARY.md` (e.g., `delivery`, `isolation`, `STENCIL`, `stencil_tier`, `owner`, `vol_*`) and want the chronological context that the timeless blueprints intentionally omit. Blueprints describe the **current contract**; this doc describes the **path that produced it**.

---

## Origin — Single Mount Type

IgnoreScope shipped as a Docker container manager whose only mount mechanism was a host bind-mount. A scope's `mount_specs` list described directories to bind-mount into the container; mask volumes hid everything else; no per-spec choice of delivery mechanism existed. This worked for the Hybrid Mount workflow but had no story for content that should live **only** in the container (extension auth tokens, isolated workspaces).

## First Attempt — Isolation Container Mode (abandoned)

A scope-level binary field `container_mode: "Hybrid" | "Isolation"` was introduced on `feature/isolation-container-mode`. "Isolation" mode skipped bind-mounts and seeded content via `docker cp` instead. The branch shipped Tasks 1.1–1.8 between 2026-04-17 and 2026-04-19 (CLI `--mode`, GUI menu split into "+ New Hybrid Scope" / "+ New Isolation Scope", `init_source` field, L4 isolation volume split, scope-convert workflow).

The design was reverted on 2026-04-18. A DRY Audit had escalated a perceived duplication into Task 1.3a, which extracted a private helper, modified `hierarchy.py` (violating the original design constraint), and canonicalized the helper as a Blueprint invariant. The lesson: prescriptive DRY audits during feature emergence canonicalize implementation details before the design is settled, and the resulting Blueprint entries then fight the next pivot rather than guide it. The pre-revert snapshot is preserved on the `archive/isolation-phase-1-pre-revert` branch; the `_workbench/_feedback/dry-audit-restrictive-new-feature-emergence.md` write-up captures the full post-mortem.

## Pivot — Virtual Mount (per-spec delivery)

A parallel pivot replaced the scope-level binary: delivery became a per-`MountSpecPath` field, `delivery: Literal["bind", "detached", "volume"]`. A single scope can now mix delivery modes across its mount_specs, and the scope-level `container_mode` field was removed. `"bind"` is the original host-backed bind-mount; `"detached"` is a `docker cp`-seeded snapshot; `"volume"` is a named Docker volume.

Per-spec delivery shipped in PR #17 (Virtual Mount Phase 1, 2026-04-20). Phase 3 added the schema fields `host_path`, `content_seed`, `preserve_on_update`, and the `"volume"` delivery tier (PRs #19–#29).

During Phase 3 the term "virtual" had become triple-overloaded: it named a `NodeSource` enum value, a UX label ("Virtual Mount" / "Virtual Folder"), and the `visibility="virtual"` MatrixState axis. PR #19 renamed `NodeSource.VIRTUAL` to `NodeSource.STENCIL` and `is_virtual` to `is_stencil_node`, restricting "virtual" to the UX-label and visibility-axis senses only. **STENCIL** is now the canonical name for synthetic-origin nodes.

## Convergence — Unify L4 (reclaim isolation)

A second emission path still existed for extension-owned named volumes (e.g., `/root/.claude` for the Claude installer). It used its own naming scheme (`iso_*`), its own helper (`_collect_isolation_paths`), and a hard-coded `claude-auth` special case. PRs #30–#56 (`unify-l4-reclaim-isolation-term`) collapsed it onto the per-spec delivery framework:

- `MountSpecPath.owner: str` distinguishes user-authored (`"user"`) from extension-synthesized (`"extension:{name}"`) specs.
- `ExtensionConfig.synthesize_mount_specs()` translates extension isolation paths into owner-tagged `delivery="volume"` specs that `compute_container_hierarchy(extensions=...)` merges into `mount_specs`.
- All named volumes now share a single naming scheme: `vol_{owner_segment}_{path}`.
- The word "isolation" was reclaimed as a **compound term**: any `MountSpecPath` where `delivery != "bind"`. It is no longer a code path or a configuration mode; it is a category that spans the `"detached"` and `"volume"` tiers.

## GUI Cohesion — Cross-Tree Coordination (v0.6.0)

Once the core mount/isolation model stabilized, the GUI layer's cross-tree behavior was rebuilt on top of it. Prior to v0.6 the LocalHost and Scope Config trees fought over a single selection model: clicking one would clear the other through programmatic `setCurrentIndex` cascades, multi-select couldn't span gestures, and the visual cue for "this row in the OTHER tree corresponds to your click" piggybacked on `selectionModel` state and got wiped by routine programmatic updates.

Three independent layers replaced the entanglement:

- **`TreeSelectionCoordinator`** (`gui/selection_coordinator.py`) — symmetric selection clearer wired to a `userRowClicked(path)` signal emitted only from `mousePressEvent` (via `_ClickAwareTreeView`). Programmatic state changes don't fire it, so multi-select survives `expand_to_path` and other cascades.
- **Tracked-path overlay** — Layer 4 paint in `TreeStyleDelegate`, decoupled from `selectionModel`. The "OTHER tree's selection" is mirrored as a teal outline on matching paths, with `setClipping(False)` so the outline spans the row across all columns. Driven by a `selectionChangedPaths(list)` signal driven off `selectionChanged` (selection state) rather than user-gesture-only.
- **Branch-indicator mirror chain** — LocalHost's `folderExpanded` / `folderCollapsed` signals drive `ScopeView.expand_path` / `collapse_path` one-way (no reverse loop). Chevron-state mirrors without needing selection.

The RMB context menu also moved to **cursor-primary**: `view_helpers.resolve_action_target(view, pos)` makes the row under the cursor the action target; the prior selection extends only when the cursor row overlaps it.

## Polish + Bugfixes (v0.6.0)

Two CORE / Docker bugs surfaced and were fixed alongside the GUI work:

- **`_validate_hierarchy` HCR-residency check** ran `mount_root.relative_to(host_container_root)` for every spec, including container-only specs (`host_path is None`) whose `mount_root` is a container path by contract. After installing any extension this fired "Mount '.local' is not under host container root" and blocked Update Container. The fix gates the check on `host_path is None and delivery != "bind"` (the bind exclusion is defense-in-depth — bind specs must stay HCR-anchored even if `__post_init__` is bypassed). Both extension-synth specs and user stencil gestures (`add_stencil_folder` / `add_stencil_volume`) now pass through correctly.
- **Compose YAML service-level `volumes:` key** was emitted unconditionally, leaving a dangling null when a scope had no mounts (full-virtual, no extensions): `services.<svc>.volumes must be a array`. Now buffered first and only emitted when entries exist — same pattern as the existing top-level `volumes:` handling.

The `tracked_outline_alpha` was also toned down (220 → 90) for a less aggressive cross-tree mirror outline.

## Current State

One mechanism (per-spec `delivery`), three modes (`bind` / `detached` / `volume`), three stencil tiers (`mirrored` / `volume` / `auth`), two owner kinds (`user` / `extension:*`), and one volume-naming scheme (`vol_*`). "Isolation" is descriptive vocabulary, not configuration. The Scope Config Tree's container header derives three orthogonal signals (`container_running`, `fully_virtual`, `has_mounts`) from this unified state. The GUI layer adds three orthogonal cross-tree coordination layers (selection / tracked-path overlay / branch-indicator mirror) on top, and a cursor-primary RMB target resolver — all decoupled from one another so programmatic updates in one layer don't cascade through the others.

## Cross-references

- `docs/architecture/ARCHITECTUREGLOSSARY.md` § Mount Delivery Terms, § STENCIL, § isolation (compound), § ScopeHeaderSignals
- `docs/architecture/COREFLOWCHART.md` Phase 6a (Per-Spec Delivery Emit)
- `docs/architecture/DATAFLOWCHART.md` § Cross-Tree Coordination, § Scope Config Tree RMB — Stencil Gesture Flow
- `docs/architecture/GUI_LAYOUT_SPECS.md` § 11-A Cross-Tree Coordination
- Branch lifecycle convention: `.claude/commands/zev-close.md` (feature/bug → `staging-vN.N`) and `.claude/commands/zev-publish.md` (`staging-vN.N` → `main` → `live` → release tag)
- Git history: `archive/isolation-phase-1-pre-revert` branch preserves the abandoned design's three foundational commits

---

*Last updated: 2026-05-05, reflecting state through release-v0.6.0 (cross-tree coordination + validator HCR-skip + compose service-volumes fix).*
