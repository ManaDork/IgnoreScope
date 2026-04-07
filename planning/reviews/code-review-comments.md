# Code Review: Comments vs Behavior — Phase 1 Findings

**Date:** 2026-04-05
**Scope:** All zones — Core, GUI, Docker, CLI, Extensions
**Method:** Trace code stacks ignoring comments, collect comments, compare
**Total findings:** 25

---

## CORE ZONE (7 findings)

### [node_state.py:376] Stage 1 count discrepancy
- **Type:** terminology
- **Current:** "Stage 1: Per-node MatrixState (5 values)"
- **Actual:** Stage 1 computes 6 boolean flags (mounted, masked, revealed, pushed, container_orphaned, is_mount_root) + 1 derived visibility = 7 values
- **Recommendation:** rewrite → "(6 flags + visibility)"

### [node_state.py:84] container_orphaned "mount removed" misleading
- **Type:** comment-conflict
- **Current:** "Pushed file stranded in mask volume, mount removed (TTFF matrix)"
- **Actual:** Static point-in-time condition (`is_pushed and is_masked and not is_mounted and not is_revealed`), doesn't track mount removal events
- **Recommendation:** rewrite → "Pushed file under mask volume with no active mount coverage"

### [node_state.py:145-150] F5/F6 UI terminology in core module
- **Type:** stale-reference
- **Current:** References "FOLDER_VIRTUAL_REVEALED" and "F5/F6 distinction"
- **Actual:** These are now FOLDER_MIRRORED_REVEALED / FOLDER_MIRRORED — GUI display names, not core concepts
- **Recommendation:** rewrite to use field names: "has_direct_visible_child=True vs False"

### [node_state.py:216] "pathspec evaluation" attribution
- **Type:** terminology
- **Current:** "Compute per-node state using pathspec evaluation (last-match-wins)"
- **Actual:** compute_node_state() delegates to MountSpecPath.is_masked()/is_unmasked() which use pathspec
- **Recommendation:** rewrite → "Compute per-node state by querying MountSpecPath patterns"

### [node_state.py:373-374] Function name mismatch in docstring
- **Type:** terminology
- **Current:** "ApplyNodeStateFromScope()" (PascalCase, singular)
- **Actual:** Function is `apply_node_states_from_scope()` (snake_case, plural)
- **Recommendation:** update to actual name

### [node_state.py:6] COREFLOWCHART reference without link
- **Type:** stale-reference
- **Current:** "This module is the CORE owner of per-node state (COREFLOWCHART Phase 3)."
- **Actual:** COREFLOWCHART is in `.claude/IgnoreScopeContext/architecture/` — no code-level link
- **Recommendation:** minor — add path or replace with plain description

### [node_state.py:87] Visibility value order doesn't match truth table
- **Type:** terminology
- **Current:** docstring lists "visible"|"masked"|"virtual"|"revealed"|"hidden"|"orphaned"|"container_only"
- **Actual:** compute_visibility() priority: orphaned → revealed → masked → visible → container_only → hidden
- **Recommendation:** reorder to match priority

---

## GUI ZONE (11 findings)

### [display_config.py:6] "MatrixState" undefined
- **Type:** terminology
- **Current:** `state_styles: dict[str, StateStyleClass]` for MatrixState -> visual lookup
- **Actual:** Keyed by display state names ("FOLDER_MOUNTED" etc.), MatrixState is a conceptual term not a class
- **Recommendation:** rewrite → "display state name -> visual lookup"

### [display_config.py:53] P3 fallback chain incomplete
- **Type:** comment-conflict
- **Current:** "P3 = ancestor — falls to P4 when absent"
- **Actual:** P3 → P4 → P1 (full chain). Comment omits final P1 fallback
- **Recommendation:** update → "P3 = ancestor — falls to P4, which falls to P1"

### [display_config.py:91-92] REVEALED P2=hidden undocumented
- **Type:** comment-conflict
- **Current:** No inline comment explaining why `is_revealed` sets P2 to "hidden"
- **Actual:** Critical design decision from style polish — visible in hidden context
- **Recommendation:** add comment: `# REVEALED: P2=hidden (visible in hidden context — punch-through)`

### [display_config.py:110] has_visible_descendant parameter name
- **Type:** terminology
- **Current:** Parameter named `has_visible_descendant`
- **Actual:** Caller combines `has_pushed_descendant OR has_direct_visible_child` — parameter is a compound signal
- **Recommendation:** minor — consider rename or document the compound nature

### [display_config.py:249-251] "matched against" stale description
- **Type:** stale-reference
- **Current:** "matched against _FOLDER_STATE_INPUTS to find the state name"
- **Actual:** Uses _resolve_folder_state() if/elif chain, not matching
- **Recommendation:** rewrite → "resolved via _resolve_folder_state() if/elif chain"

### [display_config.py:264] "unchanged" misleading
- **Type:** comment-conflict
- **Current:** `# File path — table lookup (unchanged)`
- **Actual:** File table is unchanged but folder state names around it changed significantly
- **Recommendation:** clarify → "FILE_STATE_TABLE keys unchanged; folders now use formula"

### [display_config.py:4-8] Module docstring references undo_scope
- **Type:** stale-reference
- **Current:** "Subclasses override columns, filters, and undo_scope."
- **Actual:** undo_scope exists on TreeDisplayConfig base class (line 378) — still present
- **Recommendation:** verify — may be accurate. Check if subclasses actually override it.

### [delegates.py:15] Outdated emphasis on removed concepts
- **Type:** stale-reference
- **Current:** "No TreeContext enum. No RowStyleInput."
- **Actual:** Correct but emphasizes absence of things that were removed long ago
- **Recommendation:** rewrite → "Config-parameterized delegates — state derivation via resolve_tree_state()"

### [mount_data_tree.py:73] virtual_type comment uses old naming
- **Type:** terminology
- **Current:** `# "mirrored" | "volume" | "auth"`
- **Actual:** Display states renamed: VIRTUAL_MIRRORED → MIRRORED, but the field values are still "mirrored"/"volume"/"auth"
- **Recommendation:** minor — comment is technically correct for field values. Clarify: `# field value for _resolve_folder_state: "mirrored" | "volume" | "auth"`

### [display_config.py:158-160] File gradient framework P3 description stale
- **Type:** comment-conflict
- **Current:** "P3 = sync (deferred → background)"
- **Actual:** P3 is always background — sync was never implemented
- **Recommendation:** rewrite → "P2/P3 = background, P4 = config/status"

### [display_filter_proxy.py:83-85] Hidden filter exception undocumented
- **Type:** comment-conflict
- **Current:** No comment on why hidden nodes with pushed descendants pass the filter
- **Actual:** Logic: show hidden nodes only if they have pushed children
- **Recommendation:** add comment explaining the exception

---

## DOCKER/CLI/EXTENSIONS ZONE (7 findings)

### [cli/commands.py:1-7] Module docstring uses flat collections
- **Type:** terminology
- **Current:** "Setup container with mounts, masked, revealed"
- **Actual:** Uses mount_specs (new model). Flat collections are backward-compat properties
- **Recommendation:** rewrite → "Setup container with mount_specs configuration"

### [cli/commands.py:163-177] Function docstring stale
- **Type:** terminology
- **Current:** "config: ScopeDockerConfig with mounts, masked, revealed"
- **Actual:** config has mount_specs. mounts/masked/revealed are computed @properties
- **Recommendation:** update to reference mount_specs

### [docker/container_lifecycle.py:245-253] Same stale terminology
- **Type:** terminology
- **Current:** "config: ScopeDockerConfig with mounts, masked, revealed"
- **Actual:** Same as above
- **Recommendation:** update

### [docker/container_lifecycle.py:1-13] Ownership description
- **Type:** ownership
- **Current:** "Both GUI and CLI consume these — neither owns the orchestration"
- **Actual:** Correct statement but could be clearer
- **Recommendation:** clarify → "execute_* functions are the sole orchestration owners; GUI and CLI are thin consumers"

### [docker/compose.py:154-160] Mask volume ownership unclear
- **Type:** stale-reference
- **Current:** "Named mask volumes for volumes declaration"
- **Actual:** hierarchy.py pre-computes these, compose just formats
- **Recommendation:** clarify hierarchy owns computation

### [docker/compose.py:66-92] Shelved function still present
- **Type:** comment-conflict
- **Current:** "SHELVED — not called from production"
- **Actual:** Confirmed never called. generate_dockerfile() used instead
- **Recommendation:** keep SHELVED note. Consider eventual removal

### [cli/interactive.py:191-267] Uses backward-compat properties
- **Type:** terminology
- **Current:** Accesses config.mounts, config.masked, config.revealed directly
- **Actual:** These work (computed @property from mount_specs) but mount_specs is the real model
- **Recommendation:** acceptable for backward compat. Add note in comments

---

## SUMMARY

| Zone | Comment-conflict | Terminology | Stale-reference | Ownership | Total |
|------|-----------------|-------------|-----------------|-----------|-------|
| Core | 1 | 4 | 2 | 0 | 7 |
| GUI | 5 | 3 | 3 | 0 | 11 |
| Docker/CLI/Ext | 2 | 4 | 1 | 1 | 7+1 |
| **Total** | **8** | **11** | **6** | **1** | **25+1** |

**Critical:** No logic bugs found — all code behaves correctly. Issues are purely documentation/comment accuracy.

**Most impactful:** Stale state names (VIRTUAL_MIRRORED → MIRRORED, MOUNTED_MASKED removed).

**Clarified:** mount_specs flat properties (.mounts, .masked, .revealed) are legacy convenience kept for CLI display/iteration and utils validation. Not primary API but useful. Comments should note "computed from mount_specs" — not a code change, just doc clarity.
