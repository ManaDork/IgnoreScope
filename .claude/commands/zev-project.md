---
description: "Guided project architecture scaffolding (lite, brainstorm, or review)"
---

# /zev-project — Architecture Scaffolding

> Create foundational architecture documentation. Three modes: `lite` (placeholders), `brainstorm` (iterative), `review` (refine existing). Use `/zev-feature` for feature specs — this command is for project-level architecture only.

Architecture docs focus on pipeline data flow, domain ownership, and referencing known libraries/projects.

## Parse Argument

Extract mode from `$ARGUMENTS`:
- **`lite`** — Quick scaffolding with placeholders
- **`brainstorm`** — Multi-round iterative discovery
- **`review`** — Refine and gap-check existing docs
- **`add {name}`** — Add a new architecture doc and update tables
- **`update`** — Resync CLAUDE.md tables with current doc state
- **Empty** — Ask which mode to use

## LITE Mode

Brief project identity. Scaffold architecture docs with placeholders:
1. Create `docs/architecture/OVERVIEW.md` — system purpose, boundaries, high-level components
2. Create `docs/architecture/GLOSSARY.md` — domain terms, patterns, state values
3. Create `docs/architecture/CONVENTIONS.md` — naming, file org, patterns

Set Tracking adherence. Populate CLAUDE.md Architecture Blueprints table.

During `/zev-feature` and `/zev-discuss`, propose additions as patterns are discovered.

## BRAINSTORM Mode

Multi-round iteration:
1. **Domain discovery Q&A** — Ask about system boundaries, components, data flow, ownership
2. **Section-by-section brainstorm** — Work through each doc iteratively with the user
3. **Consolidate** — Build ASCII flow diagrams showing data movement through the system
4. **Research** — Look up libraries, prior art, reference implementations relevant to the design
5. **Gap analysis** — Check for missing domains, undefined terms, ownership conflicts
6. **Repeat** — Iterate until the user is satisfied
7. **Finalize** — Write docs, set adherence levels, populate CLAUDE.md tables

## REVIEW Mode

1. **Collect existing docs** — Read all files in `.claude/IgnoreScopeContext/architecture/`:
   - `ARCHITECTUREGLOSSARY.md` — terms, patterns, state values, domain ownership
   - `COREFLOWCHART.md` — data flow, phase pipeline
   - `DATAFLOWCHART.md` — GUI data flow, module responsibility
   - `MIRRORED_ALGORITHM.md` — mirrored intermediate computation
   - `GUI_STATE_STYLES.md` — state visual definitions
   - `GUI_LAYOUT_SPECS.md` — widget layout spec
   - `GUI_STRUCTURE.md` — widget hierarchy and sizing
2. **Gap scan** — Check for missing domains, undefined cross-references, stale terms
3. **Refinement** — Separate specs from architecture, suggest structural improvements
4. **Configure adherence** — Set levels per doc (Tracking/Planning/Structural/GAP)
5. **Populate tables** — Update CLAUDE.md Architecture Blueprints table

## Add / Update

- **`add {name}`** — Create a new architecture doc in `.claude/IgnoreScopeContext/architecture/`, add to CLAUDE.md table
- **`update`** — Scan current docs, resync CLAUDE.md tables with actual file state

## Architecture Adherence Levels

| Level | Meaning |
|-------|---------|
| Tracking | Informational — read before designing, no hard enforcement |
| Planning | Must consult during `/zev-feature` and `/zev-discuss` |
| Structural | Must verify alignment during `/zev-start` and `/zev-review` |
| GAP | Halt — conflict must be resolved before proceeding |