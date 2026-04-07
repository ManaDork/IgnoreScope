# Documentation & Project Code Review

## Problem Statement

Multiple significant changes across two features (pathspec-native-state, style-polish-round-2 + formulaic-gradient-system) have created documentation drift. The project workflow enforces documentation reference during planning and execution (/zev-start adherence checks, /zev-feature blueprint reads). When docs are wrong, planning and execution quality degrades.

No full audit has been done in a while. Code comments may conflict with actual behavior, architecture blueprints may describe removed or renamed concepts, and the CLAUDE.md may reference stale functions/states.

## Success Criteria

- Findings report covering all zones: code comments vs behavior, architecture docs vs code, CLAUDE.md accuracy
- All misleading code comments identified with file:line references
- All stale doc references catalogued with what changed
- Report reviewed by user before any fixes applied

## Scope

### Phase 1: Code Comments Audit (all zones)

Per CLAUDE.md debug protocol: trace full code stacks ignoring comment descriptions. Collect comments. Compare for:
- Conflicting intentions (comment says X, code does Y)
- Terminology inconsistency (comment uses old term, code uses new)
- Redundant behaviors described across stacks
- Ownership inconsistency (comment says module A owns, code shows module B)

Zones:
| Zone | Key files to trace |
|------|-------------------|
| Core | node_state.py, mount_spec_path.py, local_mount_config.py, hierarchy.py, config.py |
| Docker | compose.py, container_lifecycle.py, container_ops.py, file_ops.py |
| CLI | commands.py, interactive.py |
| GUI | display_config.py, style_engine.py, delegates.py, mount_data_tree.py, local_host_view.py, scope_view.py, display_filter_proxy.py, export_structure.py |
| Extensions | install_extension.py, claude_extension.py, git_extension.py |
| Tests | All test files — check docstrings match test behavior |

### Phase 2: Architecture Blueprints Audit

Compare each blueprint against current code reality:
| Document | Check against |
|----------|--------------|
| ARCHITECTUREGLOSSARY.md | All term definitions, NodeState table, display state table, domain ownership |
| COREFLOWCHART.md | Phase 3 pipeline, module map, rules, orchestration entry points |
| DATAFLOWCHART.md | GUI data flow, module responsibility map |
| MIRRORED_ALGORITHM.md | Walk functions, data flow, stage descriptions, file table |
| GUI_STATE_STYLES.md | Gradient formula, state enumeration, color variables, selected mechanism |
| GUI_LAYOUT_SPECS.md | Widget layout, column definitions |
| GUI_STRUCTURE.md | Widget hierarchy, sizing |

### Phase 3: CLAUDE.md Audit

Check project CLAUDE.md for:
- Stale function/class references
- Removed or renamed states
- Workflow table accuracy
- Key locations table accuracy
- Agent zone path accuracy

## Deliverable

Findings report per phase: `planning/reviews/code-review-{phase}.md`

Format per finding:
```
### [file:line] Finding title
- **Type:** comment-conflict | terminology | stale-reference | ownership
- **Current:** what the comment/doc says
- **Actual:** what the code does
- **Recommendation:** delete | rewrite | update doc
```

## Out of Scope

- Fixing findings (Phase 2 of this initiative — after report review)
- Performance audit
- Test coverage gaps (separate concern)
- Feature completeness review
