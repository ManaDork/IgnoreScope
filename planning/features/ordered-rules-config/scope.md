# Scope: Ordered Rules Config

> **SUPERSEDED** — This VolumeRule-based design was replaced by the MountSpecPath architecture (mount-centric, gitignore-style patterns via `pathspec` library). Implementation: `core/mount_spec_path.py`, `core/local_mount_config.py`. See `ARCHITECTUREGLOSSARY.md → MountSpecPath` for current design.

## Phases

### Phase 1: Core Config Model
Replace `masked`/`revealed` sets with `rules: list[VolumeRule]` in `LocalMountConfig`. Add serialization, deserialization, validation, and migration from old format.
- [ ] `VolumeRule` dataclass
- [ ] `LocalMountConfig.rules` field replaces `masked`/`revealed`
- [ ] `evaluate_rules()` function
- [ ] `rules_to_sets()` extraction helper
- [ ] `add_rule()` / `remove_rule()` / `move_rule()` methods
- [ ] `to_dict()` / `from_dict()` updated for `rules` JSON key
- [ ] `SiblingMount` and `ScopeDockerConfig` inheritance updated
- [ ] Migration function: old `masked`/`revealed` arrays -> `rules` array
- [ ] Version bump in `_version.py`

### Phase 2: State Computation
Wire rules through CORE state computation pipeline.
- [ ] `compute_node_state()` accepts `rules` parameter, calls `evaluate_rules()`
- [ ] `apply_node_states_from_scope()` passes rules via config namespace
- [ ] `MountDataTree._recompute_states()` builds config from `_rules`
- [ ] `_collect_all_paths()` extracts rule paths for path collection
- [ ] `compute_mirrored_intermediate_paths()` receives extracted sets

### Phase 3: Volume Generation
Interleaved volume ordering from rules.
- [ ] `compute_container_hierarchy()` accepts `rules` parameter
- [ ] `_process_root()` extracts sets for sub-functions (Option A)
- [ ] `_compute_volume_entries()` generates interleaved volumes from rule order
- [ ] `_validate_hierarchy()` validates rules (mask under mount, reveal under prior mask)
- [ ] 4 call sites in `container_lifecycle.py` updated
- [ ] `hierarchy.revealed_parents` still works for mkdir -p

### Phase 4: GUI Integration

#### Phase 4a: Checkbox Toggle + Config Plumbing
Wire rules into existing Mask/Reveal checkbox workflow.
- [ ] `toggle_masked()` / `toggle_revealed()` append/remove rules with cascade
- [ ] Cascade on unmask: remove mask rule + all descendant rules (reveals, nested masks)
- [ ] `is_in_raw_set()` checks rule list membership for checkbox state
- [ ] Context menu: "Add Mask Rule" enabled under revealed folders (NEW capability)
- [ ] Multi-select mask/reveal actions work with rules
- [ ] Sibling merge concatenates rule lists (scoped per root)
- [ ] `_filter_rules_by_root()` replaces `_filter_sets_by_root()`
- [ ] `build_config()` / `get_config_data()` export rules
- [ ] Clear/reset methods clear rules list

#### Phase 4b: Rule List Panel
Port from archive, integrate into layout. **Prerequisite: decide layout slot** (new dock widget, tabbed section, or collapsible panel — see GUI Layout Gaps in technical-design.md).
- [ ] Audit archive `pattern_list.py` for PyQt6 compatibility and API
- [ ] Define layout slot in GUI_LAYOUT_SPECS + GUI_STRUCTURE
- [ ] Port rule list panel widget
- [ ] Ordered rule list display with action + path
- [ ] Drag-to-reorder (triggers stateChanged + volume reorder)
- [ ] Ordering conflict warnings (port from archive `pattern_conflict.py`)
- [ ] Undo/redo (Ctrl+Z/Y)

### Phase 5: Tests & Docs
Update all tests, add nested scenarios, update architecture blueprints per audit.
- [ ] Update 65 tests in `test_node_state.py` for `rules` parameter
- [ ] Update 30 tests in `test_mount_data_tree.py` for `_rules` list
- [ ] Update 4 tests in `test_interactive.py` for rule operations
- [ ] New tests: nested mask-within-reveal state computation
- [ ] New tests: interleaved volume ordering in hierarchy
- [ ] New tests: migration from old format
- [ ] New tests: cascade on rule removal
- [ ] `ARCHITECTUREGLOSSARY.md` — redefine "masked"/"revealed" as rule actions, add VolumeRule + RuleEvaluation entries, revise "Config IS the State" principle, update volume layering table
- [ ] `COREFLOWCHART.md` — Phase 1 (rules field), Phase 3 (evaluate_rules step), Phase 6 (interleaved volumes), Phase 7 (cascade = rule filtering)
- [ ] `DATAFLOWCHART.md` — Phase 4 (GUI `_rules` field), Rule 8 (cascade direction with rules)
- [ ] `MIRRORED_ALGORITHM.md` — no code change needed but add note that sets are extracted via `rules_to_sets()` at hierarchy.py entry
- [ ] `01_features.md` — add Ordered Rules Config to Active Features table

## Task Breakdown

| # | Task | Depends On | Complexity | Zone |
|---|------|-----------|------------|------|
| 1 | `VolumeRule` dataclass + `evaluate_rules()` + `rules_to_sets()` | -- | S | Core |
| 2 | `LocalMountConfig` field swap + CRUD methods | 1 | M | Core |
| 3 | Serialization (`to_dict`/`from_dict`) + migration | 2 | M | Core |
| 4 | `SiblingMount` / `ScopeDockerConfig` inheritance | 3 | S | Core |
| 5 | `compute_node_state()` rules evaluation | 1 | M | Core |
| 6 | `apply_node_states_from_scope()` + `MountDataTree._recompute_states()` | 5 | M | Core + GUI |
| 7 | `_collect_all_paths()` rule path extraction | 2 | S | GUI |
| 8 | `compute_container_hierarchy()` entry point + `_process_root()` | 2 | M | Core |
| 9 | `_compute_volume_entries()` interleaved volumes | 8 | M | Core |
| 10 | 4 `container_lifecycle.py` call sites | 8 | S | Docker |
| 11 | `toggle_masked()`/`toggle_revealed()` rule append/remove + cascade | 2, 6 | M | GUI |
| 12 | `is_in_raw_set()` + checkbox state | 2, 11 | S | GUI |
| 13 | Context menu updates (mask under revealed) | 11 | S | GUI |
| 14 | Sibling merge + `_filter_rules_by_root()` | 2 | M | GUI |
| 15 | `build_config()` + `get_config_data()` + clear/reset | 2, 14 | S | GUI |
| 16 | Rule list panel (port from archive) | 2, 11 | L | GUI |
| 17 | `export_structure.py` update | 2 | S | GUI |
| 18 | `interactive.py` CLI update | 2 | S | CLI |
| 19 | Update existing tests (99 tests) | 1-18 | L | Tests |
| 20 | New tests: nested scenarios, migration, cascade | 1-18 | M | Tests |
| 21 | Architecture blueprint updates | 1-18 | S | Docs |

## Testing Strategy

- **Unit:** `evaluate_rules()` with nested paths, `rules_to_sets()`, `VolumeRule` serialization, migration function, cascade removal logic
- **Integration:** `apply_node_states_from_scope()` with nested rules produces correct NodeState booleans; `compute_container_hierarchy()` generates correct interleaved volume entries; full toggle -> recompute -> display cycle
- **Manual:** Create scope with mount -> mask -> reveal -> nested mask; verify GUI tree visibility, container filesystem (`docker exec ls`), and docker-compose.yml volume order
