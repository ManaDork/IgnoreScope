---
description: "Specify what to build: interactive feature specification, technical design, and scope planning."
---

# /zev-feature — Feature Specification

> Specify **what** to build: interactive feature specification, technical design, and scope planning. For planning **when** and **how** to execute, use `/zev-discuss` instead. Use `/zev-feature review {name}` to review an existing feature spec.

## Parse Argument

- **Empty** — Ask the user to name or describe the feature in a sentence
- **`{feature-name}`** — Use as working title, begin specification
- **`review {name}`** — Switch to review mode (see below)

---

## Specification Mode (default)

### Step 1: Check for Existing Docs

Search `planning/features/` for docs matching the feature name.
If found, ask: continue refining existing spec or start fresh?
If continuing, load existing docs as starting context.

### Step 2: Initial Exploration

Spawn exploration agents across all zones with `run_in_background: true`. Prompt them to:
- Identify systems, modules, and patterns relevant to the feature
- Report existing code the feature will interact with, extend, or depend on
- Surface architectural constraints from Architecture Blueprints
- Find related features already implemented as reference implementations

### Agent Zones
| Zone | Paths |
|------|-------|
| Core Logic | `IgnoreScope/core/` |
| Docker Layer | `IgnoreScope/docker/` |
| CLI | `IgnoreScope/cli/` |
| GUI | `IgnoreScope/gui/` |
| Extensions | `IgnoreScope/container_ext/` |
| Tests | `tests/`, `IgnoreScope/tests/` |

### Step 3: Iterative Discovery

Conduct structured Q&A using `AskUserQuestion` for multi-choice questions. Adapt order and depth based on responses — skip irrelevant areas, dig deeper on ambiguity.

**Problem & Purpose:**
- What problem does this solve? Who is it for?
- What does success look like?
- Existing workarounds or partial solutions?

**Scope & Boundaries:**
- MVP — minimum that delivers value?
- Explicitly out of scope?
- Phases or milestones?

**Behaviour & Requirements:**
- Key use cases and acceptance criteria?
- Error/edge cases?
- Performance requirements?

**Dependencies & Integration:**
- Existing systems touched? (ground in agent findings)
- External services: Docker Engine, Perforce, GitHub?
- Ordering dependencies?
- Related repo: p4mcp-server-linux?

**Technical Approach:**
- Proposed architecture? (suggest based on agent findings and existing patterns)
- New interfaces, services, data structures?
- Existing code modifications?
- Alternatives to evaluate?

**Testing Strategy:**
- Key test scenarios?
- Unit vs integration vs manual?
- Test data/fixture requirements?

**Risks & Unknowns:**
- Uncertainties?
- What could go wrong?
- External input needed?

### Step 4: Quality Gates

- **DRY Risk Flags** — Identify potential duplication with existing code from agent findings
- **Adherence Check** — Verify feature design aligns with Architecture Blueprints
- **Architecture Doc Impact** — List which Blueprints need updating for this feature

### Step 5: Produce Artifacts

Once discovery is complete, generate feature documentation. Ask for approval before writing.

```
planning/features/{feature-name}/
├── spec.md               # Feature specification
├── technical-design.md   # Technical design document
└── scope.md              # Scope, phases, task breakdown
```

**`spec.md`** — Problem statement, success criteria, user stories, acceptance criteria, out of scope, open questions.

**`technical-design.md`** — Overview, architecture, dependencies (internal/external/ordering), key changes (new/modified files), interfaces & data, alternatives considered, risks, Architecture Doc Impact section.

**`scope.md`** — Phases (MVP → v1 → full), task breakdown table with columns: #, Task, Depends On, Complexity, DRY Checkpoint.

### Step 6: Offer Next Steps

- Suggest `/zev-discuss` to plan execution around this feature
- Suggest `/zev-start` to begin the first task
- Highlight open questions that should be resolved first

---

## Review Mode

Invoked as `/zev-feature review {name}`.

### Step 1: Find Feature Docs
Search `planning/features/` for the named feature. If not found, list available features.

### Step 2: Load All Docs
Read `spec.md`, `technical-design.md`, and `scope.md`.

### Step 3: Spawn Exploration Agents
For each zone referenced in the technical design, check current state.

### Step 4: Assess Completeness

**Spec:** Problem clear? AC testable? Edge cases covered? Out of scope listed?
**Technical design:** Dependencies identified? Changes mapped to paths? Architecture aligned?
**Scope:** MVP separable? Tasks detailed enough for issues? Dependencies mapped?

### Step 5: Check Staleness
Using agent findings: dependencies changed? Code moved? New patterns introduced? Tasks partially done?

### Step 6: Report

```
## Feature Review: {Feature Name}

### Status
{Ready to implement / Needs refinement / Significant gaps}

### Completeness
- **Spec:** {status + gaps}
- **Technical Design:** {status + gaps}
- **Scope:** {status + gaps}

### Staleness
{Outdated items}

### Open Questions
{Unresolved + new questions}

### Recommendations
{Actions to address gaps}
```

### Step 7: Offer to Fix
For each gap, offer to update the feature docs interactively.