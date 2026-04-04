# Technical Design: Ordered Rules Config

> **SUPERSEDED** — This VolumeRule-based design was replaced by the MountSpecPath architecture. See `ARCHITECTUREGLOSSARY.md → MountSpecPath`.

## Overview

Replace the flat `masked: set[Path]` and `revealed: set[Path]` fields in `LocalMountConfig` with an ordered `rules: list[VolumeRule]` list. Each rule is a `(action, path)` pair where action is `"mask"` or `"reveal"`. Rules evaluate in order with last-match-wins semantics. Docker volumes are generated in rule order, enabling interleaved mask/reveal layers at arbitrary depth.

## Architecture

### Data Model

```python
@dataclass
class VolumeRule:
    action: str   # "mask" or "reveal"
    path: Path    # Absolute folder path

@dataclass
class LocalMountConfig:
    mounts: set[Path]            # Base layer -- unchanged
    rules: list[VolumeRule]      # Ordered mask/reveal rules (NEW)
    pushed_files: set[Path]      # File-level, docker cp -- unchanged
    mirrored: bool = True        # Unchanged
```

### Rule Evaluation

```python
def evaluate_rules(path: Path, rules: list[VolumeRule]) -> str | None:
    """Last matching rule wins. Returns 'mask', 'reveal', or None."""
    result = None
    for rule in rules:
        if path == rule.path or is_descendant(path, rule.path, strict=False):
            result = rule.action
    return result
```

Uses existing `is_descendant()` from `utils/paths.py`. No new dependencies.

### Docker Volume Mapping

Rules map 1:1 to Docker volume entries:
```
Rule("mask", /src/vendor)         -> mask_vendor:/container/src/vendor       (named volume)
Rule("reveal", /src/vendor/pub)   -> /src/vendor/pub:/container/vendor/pub   (bind mount)
Rule("mask", /src/vendor/pub/tmp) -> mask_pub_tmp:/container/vendor/pub/tmp  (named volume)
```

Docker applies volumes in declaration order (last-writer-wins), so rule order = volume order = correct layering.

### JSON Format

```json
{
  "mounts": ["src"],
  "rules": [
    {"action": "mask", "path": "vendor"},
    {"action": "reveal", "path": "vendor/public"},
    {"action": "mask", "path": "vendor/public/tmp"}
  ],
  "pushed_files": []
}
```

Paths stored as relative POSIX (same convention as current masked/revealed).

## Dependencies

### Internal
- `is_descendant()` -- `IgnoreScope/utils/paths.py` (rule evaluation)
- `to_relative_posix()` -- `IgnoreScope/utils/paths.py` (serialization)
- `to_absolute_paths()` -- `IgnoreScope/utils/paths.py` (deserialization)
- Archive `pattern_conflict.py` -- `E:\SANS\SansMachinatia\_workbench\Archive\IgnoreScope\utils\` (ordering validation)
- Archive `pattern_list.py` -- `E:\SANS\SansMachinatia\_workbench\Archive\IgnoreScope\panels\` (rule list UI)

### External
- None (no new pip dependencies)

### Ordering
1. Phase 1: Core config model (`VolumeRule`, `LocalMountConfig`, serialization, migration)
2. Phase 2: State computation (`compute_node_state`, `apply_node_states_from_scope`)
3. Phase 3: Volume generation (`hierarchy.py`, `container_lifecycle.py` call sites)
4. Phase 4: GUI integration (toggles, context menu, rule list panel)
5. Phase 5: Tests and migration validation

## Key Changes

### New
- `VolumeRule` dataclass -- `core/local_mount_config.py`
- `evaluate_rules()` function -- `core/local_mount_config.py`
- `rules_to_sets()` utility -- extracts `(masked_set, revealed_set)` from rules for CORE compatibility
- Rule list panel widget -- port from archive `panels/pattern_list.py`
- Migration function -- `_version.py` or `core/migration.py`

### Modified (28 locations across 14 files)

| File | What Changes |
|------|-------------|
| `core/local_mount_config.py` | Root definition, query methods, CRUD, validation, serialization |
| `core/config.py` | `SiblingMount` and `ScopeDockerConfig` inheritance, `from_dict`/`to_dict` |
| `core/node_state.py` | `compute_node_state()` signature: `masked=`/`revealed=` -> `rules=` |
| `core/node_state.py` | `apply_node_states_from_scope()` -- pass rules through config namespace |
| `core/hierarchy.py` | `compute_container_hierarchy()` entry point accepts `rules`, extracts sets for sub-functions (Option A: minimal -- sub-functions unchanged) |
| `core/hierarchy.py` | `_compute_volume_entries()` -- interleaved rule-order volumes |
| `docker/container_lifecycle.py` | 4 call sites pass `rules=` instead of `masked=`/`revealed=` |
| `gui/mount_data_tree.py` | `_masked`/`_revealed` sets -> `_rules` list; toggle methods append/remove rules; sibling merge concatenates lists; config init/export |
| `gui/mount_data_model.py` | `is_in_raw_set()` checks rule list membership |
| `gui/local_host_view.py` | Context menu: "Add Mask Rule" enabled under revealed folders |
| `gui/export_structure.py` | `masked`/`revealed` params -> extract from rules |
| `cli/interactive.py` | Direct set operations -> rule operations |
| `_version.py` | Version bump + migration function |

### Unchanged
- `NodeState` dataclass -- `masked`/`revealed` remain as boolean flags
- `compute_visibility()` truth table -- priority matrix unchanged
- Display system -- delegates, proxy filters, tooltips read NodeState booleans
- `can_check_revealed()` / `can_check_masked()` -- query CORE state, not config

## Interfaces & Data

### VolumeRule -> NodeState Flow

```
Config:  rules: [VolumeRule("mask", /a), VolumeRule("reveal", /a/b)]
           |
           v
CORE:    evaluate_rules(path, rules) -> "mask" | "reveal" | None
           |
           v
State:   NodeState(masked=True, revealed=False, visibility="masked")
           |
           v
Display: Delegates read NodeState booleans -> paint row
```

### GUI Toggle Flow

```
User clicks Mask checkbox on path X
  -> mount_data_model.setData() routes to toggle_masked(X, checked)
  -> if checked: self._rules.append(VolumeRule("mask", X))
  -> if unchecked: remove rule + cascade (remove descendant rules)
  -> self._recompute_states()
  -> stateChanged signal -> view refresh
```

### Hierarchy Entry Point (Option A)

```python
def compute_container_hierarchy(..., rules: list[VolumeRule], ...):
    # Extract sets once at entry for sub-function compatibility
    masked = {r.path for r in rules if r.action == "mask"}
    revealed = {r.path for r in rules if r.action == "reveal"}
    # Sub-functions receive sets -- unchanged signatures
    _validate_hierarchy(mounts, masked, revealed, ...)
    _compute_volume_entries(mounts, rules, ...)  # This one uses rules directly
    _compute_revealed_parents(pushed_files, masked, ...)
    _walk_mirrored_intermediates(masked, revealed, mounts, ...)
```

## Alternatives Considered

1. **Gitignore glob patterns with `pathspec`** -- More powerful but adds dependency, requires glob-to-concrete-path expansion for Docker volumes. Reserved for future extension.
2. **Keep flat sets, add a "depth limit" to reveals** -- Simpler but doesn't solve the general nesting problem. Rejected.
3. **Full hierarchy.py refactor** (Option B: pass rules everywhere) -- More consistent but 6+ function signatures change. Option A (extract at entry) is simpler with same result.

## Risks

- **Migration correctness** -- Old configs must produce identical Docker output after migration. Mitigated by: masks-first-then-reveals ordering preserves 3-layer behavior exactly.
- **Sibling rule merge ordering** -- Concatenating sibling rules into primary list must not create ordering conflicts. Mitigated by: sibling rules are scoped to their root, evaluated independently.
- **Cascade on unmask** -- Removing a mask rule must also remove dependent reveal/nested-mask rules. Mitigated by: filter rules whose paths descend from the removed mask's path.
- **Performance** -- `evaluate_rules()` is O(rules * paths). With typical rule counts (<20), this is negligible vs the optimized O(n*depth) state computation.

---

## Architecture Audit — Conflicts & Required Updates

DRY audit performed against all architecture blueprints. Results below.

### CRITICAL: MatrixState vs RuleEvaluation

`evaluate_rules()` uses last-match-wins cascading iteration — this contradicts the MatrixState glossary entry which states "independent flags, NOT cascading; gating at data level creates contradictions."

**Resolution:** MatrixState still applies to `compute_visibility()` (truth table over boolean flags). The change is UPSTREAM: how `masked`/`revealed` boolean flags are DERIVED. Previously derived from flat set membership; now derived from `evaluate_rules()`. The MatrixState truth table itself is unchanged.

Add `RuleEvaluation` as a new glossary entry describing the ordered evaluation that feeds INTO the MatrixState truth table:

```
RuleEvaluation → evaluate_rules() → (masked=bool, revealed=bool)
    ↓
MatrixState → compute_visibility(mounted, masked, revealed, ...) → visibility string
```

Two patterns, two layers. Not a replacement — a new upstream step.

### CRITICAL: "Config IS the State" Principle

ARCHITECTUREGLOSSARY line 228 says "Config JSON fields map 1:1 to NodeState flags." This breaks — `rules[]` is not 1:1 with `NodeState.masked`/`NodeState.revealed`.

**Resolution:** Revise to: "Config rules are evaluated to produce NodeState flags. The mapping is `rules → evaluate_rules() → boolean flags`, not direct 1:1."

### Stale Definitions to Update

| Doc | What's Stale |
|-----|-------------|
| ARCHITECTUREGLOSSARY "masked" entry | `local.masked[]` JSON field reference — field replaced by `rules[]` |
| ARCHITECTUREGLOSSARY "revealed" entry | `local.revealed[]` JSON field reference — field replaced by `rules[]` |
| ARCHITECTUREGLOSSARY volume layering | 4 static layers (Mount/Mask/Reveal/Isolation) — replaced by interleaved rule-order volumes + isolation |
| COREFLOWCHART Phase 1 | "mounts, masked, revealed (path sets)" → "mounts, rules, pushed_files" |
| COREFLOWCHART Phase 3 | "FOR EACH path in scope.masked" → "evaluate_rules(path, scope.rules)" |
| COREFLOWCHART Phase 6 | 3-layer compose model → rule-order compose model |
| COREFLOWCHART Phase 7 | Cascade "Mask off → revealed=False" → "remove mask rule + filter descendant rules" |
| DATAFLOWCHART Phase 4 | GUI fields `_masked`/`_revealed` → `_rules` |
| DATAFLOWCHART Rule 8 | Cascade direction assumes set toggle → rule filtering |

### New Glossary Entries Needed

- **VolumeRule** — Dataclass `(action, path)` representing a single ordered rule
- **RuleEvaluation** — Pattern: iterate rules in order, last match wins, feeds boolean flags into MatrixState
- **rules_to_sets()** — Bridge utility extracting `(masked_set, revealed_set)` from rules for CORE compatibility
- **Interleaved Volumes** — Docker compose volumes in rule order (masks and reveals alternating at arbitrary depth)

### Compatible (No Update Needed)

- **MIRRORED_ALGORITHM** — Walk receives extracted sets via `rules_to_sets()` at hierarchy.py entry. Algorithm unchanged.
- **GUI_STATE_STYLES** — All 15+5 state definitions read NodeState booleans. Booleans unchanged.
- **Display system** — Delegates, proxy, tooltips read NodeState. Unaffected.

### GUI Layout Gaps (Blockers for Phase 4)

1. **Rule list panel placement** — No slot allocated in GUI_LAYOUT_SPECS or GUI_STRUCTURE. Must decide: new dock widget, tabbed section, or collapsible panel.
2. **Checkbox toggle semantics** — GUI_LAYOUT_SPECS defines Mask/Reveal as binary checkboxes but doesn't specify "append rule at end" behavior or conflict when both mask and reveal rules exist for same path.
3. **Phase 4 needs sub-phases:**
   - 4a: Rule list panel widget — port from archive, define layout slot
   - 4b: Checkbox interaction model under ordered rules (append/remove/replace)
   - 4c: Rule reordering + conflict resolution + automatic NodeState refresh
   - 4d: Undo/redo integration
4. **Archive audit** — `pattern_list.py` from archive needs API review and PyQt6 compatibility check before Phase 4a.
