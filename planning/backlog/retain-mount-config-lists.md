# Retain Mounted/Masked/Revealed JSON Lists on Mount Changes

## Status: TODO

## Problem

When a mount is removed via `toggle_mounted(path, False)`, the entire MountSpecPath is deleted — all patterns (masks, reveals) are lost. If the user re-mounts the same folder, they start with empty patterns.

## Proposed

Retain the `mounted`, `masked`, `revealed` lists (or the full MountSpecPath patterns) in the JSON config even when a mount is toggled off. This allows mount changes without losing the internal pattern structure that was configured.

Options:
- Keep MountSpecPath in mount_specs but mark as inactive (e.g., `"active": false`)
- Move removed MountSpecPath to a separate `"inactive_mount_specs"` list
- Store a "last known patterns" cache per mount_root path

## Files

- `gui/mount_data_tree.py` — `toggle_mounted()` currently deletes the MountSpecPath
- `core/mount_spec_path.py` — may need an `active` field
- `core/config.py` — serialization
