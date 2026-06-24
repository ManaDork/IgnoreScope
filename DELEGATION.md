## Delegation

- **Delegate by default; justify *not* delegating.** The standing bias is to under-delegate and to pull too much back into the main thread. If a step needs material you don't already hold — read an unfamiliar file, scan a directory, digest more than ~30 lines — that is a delegation, not main-thread work.
- **Utilize the Agent Tool Often** — Prevent Bias Context buildup by keeping unvalidated specifics in Agent context
- **Inherit context sparingly** — Get the condensed summary and confidence in result from an Agent
- **Inherit validated and tested context** — Read high confidence results
- **Cap the return (the noise valve).** A subagent hands back a 3–5 line conclusion + confidence + paths — never raw excerpts or its working. The main thread holds conclusions, not source. *Too much coming back IS the failure.*

### When to Delegate

1. **Eagerly Delegate the bounded** — Haiku or Sonnet Agent - Fetches, Location Queries, File Writes, Exact and Near Phrase Searches, Existence. **Bounded is the trigger, not a suggestion** — if it's bounded, it goes out.
2. **Validation of the Complex** — Offload investigation into low confidence returns

### How to Delegate

1. **Tell the agent what you need, not how** — unless the method is the constraint.
2. **Declare expected output shape before launch.** No shape, no spawn.
3. **Pass minimum serialized context.** Never pass live tool state or session history.
4. **Pass paths to Agent context.** Whenever possible pass by reference, not context
5. **On failure: diagnose the contract first** — wrong type, missing context, or ambiguous scope.

**Supporting principles:**
- **Terse** — brief subagents concisely. State WHAT, not HOW.
- **Trust capability** — production guide, not spec. The subagent fills gaps from context.

### How to Validate

- **Non Validated - High Complexity Low Confidence** — Launch multiple Opus Agent team - `dry run`, `review`, `manager`. **Opus on purpose:** the material is prose-heavy and Sonnet drifts on large text sets; cost is not the binding constraint right now (revisit only if that changes — the drift rationale is the durable one).
- **Synthesize in a subagent, not in main** — when fan-out yields verbose reports, a delegated Opus synthesizer consumes them and returns only the final artifact; verbose prose never lands in the main thread.
- **Pass by Reference** - location, paths, agentId, overloaded terms; Allow Agents to opt into information based on their directive

- FIRST PASS
- **Dry Run** - Agent with instructions only, not context
- **Review** - Agent without context reviews `Dry Run`
- **Research** - Launch Sonnet Agent investigates staleness of references by file age, reports information to both Opus agents on their Second Pass. 

- SECOND PASS
- **Peer Review** - Both Opus Agents discuss: Cross Examination, Challenge, Critique

- THIRD PASS
- **Manager** - Collect and consolidate Results for Report; capture foot notes of interesting discoveries (good and bad) 


### Meta

- **Flag repeated operations (>2x)** as skill-elevation candidates.
- **Feedback-driven** — when delegation fails, capture the friction. Templates evolve from use.