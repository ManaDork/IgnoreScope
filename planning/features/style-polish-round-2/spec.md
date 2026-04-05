# Style Polish Round 2

## Problem Statement

The state model and color system have naming and classification errors:

1. **MOUNTED_MASKED applied too broadly** — currently any `mounted + masked` folder gets this state. Should only apply when a folder has dual declaration: is a mount root AND has a mask on itself.
2. **VIRTUAL conflates three distinct types** — mirrored structural paths, named volume entries, and auth volume entries have different implementations and should have different visual treatments.
3. **Color variable naming is flat** — `"masked"`, `"visible"`, `"hidden"` don't indicate whether the color represents visibility, config action, or inheritance.
4. **File states visually identical** — FILE_MASKED = FILE_HIDDEN, FILE_REVEALED = FILE_VISIBLE in gradient. Kept as separate states but need font color differentiation.

## Success Criteria

- Color variable system uses categorical naming: `visibility.*`, `config.*`, `inherited.*`, `text.*`
- FOLDER_MOUNTED_MASKED only applies to dual-declaration (mount root + mask on self)
- FOLDER_MASKED exists as separate state for non-mount-root masked folders
- Three virtual types: VIRTUAL_MIRRORED, VIRTUAL_VOLUME, VIRTUAL_AUTH with distinct colors
- Inherited colors are dimmer and less saturated than config counterparts
- Container Scope panel uses same colors but has override capability

## Corrected State Model

### Folder States

| State | Condition | P1 | P2 | P3 | P4 | Text |
|---|---|---|---|---|---|---|
| FOLDER_VISIBLE | mounted, no mask | vis.visible | vis.visible | vis.visible | vis.visible | text.visible |
| FOLDER_HIDDEN | not under mount | vis.background | vis.background | vis.background | vis.background | text.hidden |
| FOLDER_MASKED | under mount, denied by pattern, NOT mount root | vis.hidden | vis.hidden | inherited.masked | inherited.masked | text.hidden |
| FOLDER_MOUNTED_MASKED | IS mount root AND mask on self (dual decl.) | vis.visible | vis.visible | config.masked | config.mount | text.visible |
| FOLDER_REVEALED | exception pattern punch-through | vis.visible | vis.visible | config.revealed | config.revealed | text.visible |
| FOLDER_VIRTUAL_MIRRORED | structural path, no direct revealed child | vis.hidden | vis.hidden | vis.hidden | vis.hidden | text.virtual_mirrored |
| FOLDER_VIRTUAL_MIRRORED_REVEALED | structural path, direct revealed child | vis.hidden | vis.hidden | ancestor.revealed | ancestor.revealed | text.virtual_mirrored |
| FOLDER_VIRTUAL_VOLUME | named volume entry (extensions) | vis.virtual | vis.virtual | purple | purple | text.virtual_volume |
| FOLDER_VIRTUAL_AUTH | auth/credential volume entry | vis.virtual | vis.virtual | purple | purple | text.virtual_auth |
| FOLDER_PUSHED_ANCESTOR | has pushed descendant | vis.hidden | vis.hidden | ancestor.pushed | ancestor.pushed | text.visible |
| FOLDER_CONTAINER_ONLY | container scan diff | container_only colors (keep current) | | | | italic |

### File States (slim layout — keep current framework)

| State | P1 | P2 | P3 | P4 | Text |
|---|---|---|---|---|---|
| FILE_HIDDEN | vis.hidden | bg | bg | bg | text.hidden |
| FILE_VISIBLE | vis.visible | bg | bg | bg | text.visible |
| FILE_MASKED | vis.hidden | bg | bg | bg | text.hidden (separate state, font color TBD) |
| FILE_REVEALED | vis.visible | bg | bg | bg | text.visible (separate state, font color TBD) |
| FILE_PUSHED | vis.hidden | bg | bg | config.pushed | text.pushed_sync or text.pushed_nosync |
| FILE_HOST_ORPHAN | DEFERRED | | | | italic |
| FILE_CONTAINER_ORPHAN | vis.hidden | bg | bg | warning | italic |
| FILE_CONTAINER_ONLY | container_only | bg | bg | bg | italic |

File P3 reserved for sync state (not yet implemented).
Pushed file special treatment deferred.
File font color may be primary differentiator (TBD).
File P2-P4 positional movement may be adjusted (TBD).

## Color Variable System

### Categories

```
text.*           — font colors per state type
visibility.*     — left-side gradient (what the container sees)
config.*         — right-side gradient (user's direct config action)
inherited.*      — right-side gradient (state from ancestor, dimmer + less saturated)
ancestor.*       — P3 descendant tracking (pushed, revealed descendants)
```

### Variables

```
TEXT
  text.visible              white
  text.hidden               muted/dim
  text.virtual_mirrored     = text.visible (dir exists in container)
  text.virtual_volume       purple
  text.virtual_auth         purple
  text.pushed_sync          (new — synced pushed file)
  text.pushed_nosync        (new — unsynced pushed file)

VISIBILITY
  visibility.visible        #4C566A
  visibility.hidden         #2E3440
  visibility.virtual        #373E4D (auth/volume left side)
  visibility.background     #3B4252

CONFIG
  config.masked             #4A3B42
  config.mount              #3D4A3E (renamed from "mounted")
  config.revealed           #4A4838
  config.pushed             #3D4A3E (current "pushed")

INHERITED (dimmer, less saturated than config)
  inherited.masked          (new — derived from config.masked)
  inherited.revealed        (new — derived from config.revealed)
  inherited.virtual_auth    (new)
  inherited.virtual_volume  (new)

ANCESTOR TRACKING
  ancestor.pushed           (new — folder has pushed descendant)
  ancestor.revealed         (new — folder has revealed descendant)
```

## Out of Scope

- Pushed file special treatment (deferred)
- FILE_HOST_ORPHAN implementation (deferred)
- Sync state for P3 on files (not yet implemented)
- Container Scope panel separate color overrides (ensure capability, don't implement yet)

## Open Questions

1. File font color differentiation — how to visually distinguish FILE_MASKED from FILE_HIDDEN when gradient is identical?
2. Purple hex value for virtual_auth/virtual_volume?
3. Exact dimming formula for inherited.* colors?
4. Does FOLDER_MASKED need a `config.masked` variant for directly-masked (pattern names this folder) vs `inherited.masked` (ancestor pattern covers this folder)?
