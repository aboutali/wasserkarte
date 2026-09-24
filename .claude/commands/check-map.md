---
description: Visually review the map around a river or region and report drawing problems
argument-hint: <water id or region, e.g. "havel" or "Ruhrgebiet">
---

Review how the map draws: $ARGUMENTS

1. `make site` and `make screenshots`.
2. Write a throwaway Playwright script in build/ (see scripts/render.mjs for the pattern) that opens
   dist/index.html, selects the water (`.row[data-id="<id>"]` after expanding the tree, or search
   `#q`) so the map zooms to it, and screenshots the `.mapbox` element in light and dark mode.
3. Look at the screenshots. Check: does the course follow the real river (compare with the
   Wikipedia map), do tributaries meet their parent, are labels readable and not colliding,
   is anything drawn outside Germany that should not be.
4. For a wrong course, read docs/PIPELINE.md → decide between via points (traced rivers),
   a manual course (untraced rivers) or a canal route; propose the concrete edit and the drawn
   vs documented length before and after (`common.polyline_km`).
