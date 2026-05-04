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

## Current State

One mechanism (per-spec `delivery`), three modes (`bind` / `detached` / `volume`), three stencil tiers (`mirrored` / `volume` / `auth`), two owner kinds (`user` / `extension:*`), and one volume-naming scheme (`vol_*`). "Isolation" is descriptive vocabulary, not configuration. The Scope Config Tree's container header derives three orthogonal signals (`container_running`, `fully_virtual`, `has_mounts`) from this unified state.

## Cross-references

- `docs/architecture/ARCHITECTUREGLOSSARY.md` § Mount Delivery Terms, § STENCIL, § isolation (compound), § ScopeHeaderSignals
- `docs/architecture/COREFLOWCHART.md` Phase 6a (Per-Spec Delivery Emit)
- `docs/architecture/DATAFLOWCHART.md` § Scope Config Tree RMB — Stencil Gesture Flow
- Git history: `archive/isolation-phase-1-pre-revert` branch preserves the abandoned design's three foundational commits

---

*Last updated: 2026-05-03, reflecting state through PR #56 (unify-l4-reclaim-isolation-term).*
