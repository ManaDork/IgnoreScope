# Style Pass: FOLDER_MASKED_REVEALED Gradient

## Status: RESOLVED (2026-04-01)

Gradient framework established: LEFT=self, MID=ancestor, RIGHT=descendant exception.
- F5 MASKED_REVEALED: `(masked, masked, masked, revealed)` + muted font
- F6 MASKED_MIRRORED: `(hidden, hidden, masked, mirrored)` + muted font
- Gradient stop positions adjusted to 3-zone layout (0.0, 0.4, 0.6, 0.85)
- Gradient x_offset aligned to cell rect for proper rendering at all indent levels

## Issue

`FOLDER_MASKED_REVEALED` gradient `(masked, revealed, visible, visible)` is visually too similar to `FOLDER_REVEALED` gradient `(revealed, revealed, visible, visible)`. Users read the parent of a revealed child as "revealed" when it's actually "masked with revealed content inside" (mirrored state).

## State Mapping

```
Visibility: "mirrored" + has_direct_visible_child=True → FOLDER_MASKED_REVEALED
Visibility: "mirrored" + has_direct_visible_child=False → FOLDER_MASKED_MIRRORED
Visibility: "revealed" → FOLDER_REVEALED
```

All three are distinct states with distinct gradients, but FOLDER_MASKED_REVEALED and FOLDER_REVEALED look too similar at a glance.

## Suggestion

Adjust FOLDER_MASKED_REVEALED gradient to emphasize the "masked" aspect more — e.g., `(masked, masked, mirrored, revealed)` or use a distinct indicator color. Review alongside all 17 state gradients in a dedicated style pass.

## Files

- `gui/display_config.py` line 72-75: gradient definition
- `gui/display_config.py` line 160: state mapping
- `.claude/IgnoreScopeContext/architecture/GUI_STATE_STYLES.md`: style reference doc
