# GUI Color Palette Shift

## Status: TODO

## Reference

Image: https://strapi.autentika.com/uploads/Newsroom_2_0a29e4efe3.png
Style: Dark dashboard/workflow UI — deep navy base, vivid saturated accents

## Current vs Target Palette

```
BACKGROUNDS
  current visibility.background  #3B4252  warm blue-grey (Nord)
  target                         ~#0D1117  deep cool navy (much darker)

  current visibility.visible     #4C566A  steel blue
  target                         ~#1C2128  elevated surface (darker, subtler)

  current visibility.hidden      #2E3440  near-black
  target                         ~#161B22  card surface (similar depth, cooler)

ACCENTS (biggest change — current are barely visible, target are vivid)
  current config.mount           #3D4A3E  barely-visible muted green
  target                         ~#22D3EE  vivid teal/cyan

  current config.revealed        #4A4838  muted olive
  target                         ~#F59E0B  warm orange/amber

  current config.masked          #4A3B42  dim warm rose
  target                         ~#F472B6  hot pink/magenta

  current config.pushed          #3D4A3E  same as mount (indistinct)
  target                         ~#A78BFA  purple/violet

TEXT
  current text_primary           #ECEFF4  warm white
  target                         ~#E6EDF3  cool white (similar)

  current text_dim               #616E88  grey
  target                         ~#8B949E  lighter grey (more contrast)

BORDERS/SURFACES
  target card border             ~#30363D
  target hover                   ~#1C2128
```

## Scope

Full GUI palette shift — not just gradients:
- `gui/tree_state_style.json` — all gradient color variables
- `gui/tree_state_font.json` — text color references
- `gui/theme.json` — app-wide theme (backgrounds, borders, scrollbars)
- `gui/list_style.json` — history panel
- `gui/style_engine.py` — QSS stylesheet colors
- `gui/display_config.py` — text_primary, text_dim, hover_color class attributes

## Key Observations

- Current Nord palette has muted accents that are hard to distinguish
- Target has vivid accents against darker base = much stronger visual hierarchy
- config.mount and config.pushed are currently identical (#3D4A3E) — need distinct colors
- Target maintains readability with lighter secondary text (#8B949E vs current #616E88)