# Pipeline

```
                     ┌──────────────────── tier 3: heavy geo stack, network ─────────────────────┐
 Natural Earth  ─┐   │                                                                            │
 deutschland-    ├─► fetch_sources.py ─► raw/ ─┬─► prepare_base.py ─► data/generated/base.json     │
   GeoJSON       │   (+ GSHHG via basemap)     │                      data/generated/states.json   │
 GSHHG/WDBII   ──┘                             │                      data/generated/ne_rivers.json│
                     │                         └─► trace_rivers.py ─► data/generated/traced.json   │
                     └────────────────────────────────────────────────────────────────────────────┘
                     ┌──────────────────── tier 1: Python stdlib ────────────────────────────────┐
 data/waters/*.json ─┼─► validate.py                                                              │
 data/geometry/*.json┼─► build_geometry.py ─► data/generated/geometry.json                         │
                     │   build_site.py ─► dist/index.html, dist/gewaesser.json, build/poster.html   │
                     │   export_csv.py ─► dist/gewaesser-deutschland.csv                           │
                     └────────────────────────────────────────────────────────────────────────────┘
                     ┌──────────────────── tier 2: Node + Playwright ────────────────────────────┐
                     │   render.mjs smoke | poster | screenshots                                   │
                     └────────────────────────────────────────────────────────────────────────────┘
```

Everything in `data/generated/` is committed. A fresh clone can build, test and deploy the site
with tier 1 (+2 for tests) only; tier 3 is needed when the raw sources or the tracing change.
Running tier 3 on the committed inputs reproduces the committed outputs byte for byte.

## Scripts

| script | reads | writes | deps |
|---|---|---|---|
| `fetch_sources.py` | internet | `raw/`, `build/fonts/` | basemap (for GSHHG) |
| `prepare_base.py` | `raw/` | `base.json`, `states.json`, `ne_rivers.json` | shapely |
| `trace_rivers.py` | `raw/gshhs_rivers_f.json`, waters, `via_points.json`, `config.json` | `traced.json`, `build/trace_report.json` | numpy, scipy |
| `build_geometry.py` | waters, `data/geometry/*`, `traced.json`, `ne_rivers.json` | `geometry.json` | stdlib |
| `validate.py` | waters, `geometry.json` | — (`--fix` rewrites waters) | stdlib |
| `build_site.py` | waters, `data/generated/*`, `web/*.template.html` | `dist/`, `build/poster.html` | stdlib |
| `export_csv.py` | waters, `geometry.json` | `dist/gewaesser-deutschland.csv` | stdlib |
| `render.mjs` | `dist/index.html`, `build/poster.html` | PDF, screenshots | playwright |

## Tracing (trace_rivers.py)

GSHHG/WDBII contains ~80 000 digitised river points around Germany but no names. For every river
and canal we know source, mouth and length, so the tracer searches the network for the best
matching path:

1. **Graph.** Consecutive points of one GSHHG segment are joined with their true distance. Points
   of *different* segments closer than 6 km get a *gap* edge weighted ×8, so paths use real
   geometry and only jump where digitising left holes.
2. **Anchor and candidates.** Anchor at whichever end (source or mouth) lies closer to the network;
   run Dijkstra from it; among network nodes near the other end choose the one whose path length
   plus snap distances best matches the documented length (accepted window 0.55–1.45 × length).
3. **Rejections.** Gap share > 25 %; any node outside the ellipse `d(S,n) + d(n,M) ≤ max(1.9 L, straight + 90 km)`;
   untraced head/tail too long (> min(85 km, max(25 km, 0.45 × straight)) or > 45 % of L).
   A *partial* match (`q = "teil"`) is kept when the untraced remainder is geometrically consistent
   with the missing length.
4. **Via points.** Rivers in `data/geometry/via_points.json` are traced leg by leg through forced
   waypoints (Rhein: Konstanz → Basel → … → Hoek van Holland; Donau: to Jochenstein).

`build/trace_report.json` states for every river why it was or wasn't matched
(`kein_treffer`: nothing near either end, `kein_lauf`: no path of plausible length,
`kein_teilstueck`: partial match inconsistent, `luecken`, `umweg`, `zu_kurz`).

## Geometry (build_geometry.py)

Priority `kanal` → `gshhs` → `ne` → `schema`, then snapping and clipping; see CLAUDE.md.
Parameters live in `data/geometry/config.json`:

| key | meaning |
|---|---|
| `ne_aliases` | Natural Earth names per id (`rhein: ["Rhine", "Nederrijn"]`) |
| `ne_clip_end` | cut NE lines at this point instead of the mouth (Donau at Passau) |
| `draw_end` | draw the course to this point instead of the mouth (Donau: Jochenstein, not the delta) |
| `snap_km` | max distance a mouth is moved onto the parent's course |
| `draw_bbox` | points outside are clipped |
| `trace_full_course_exempt` | ids exempt from head/tail checks (their ends are spliced by hand) |

## Base layers (prepare_base.py)

- **Ocean** — Natural Earth ocean, unioned, clipped to 2.8–17.8 °E / 45.3–56.8 °N, simplified 0.012°.
- **Countries** — Germany and its neighbours inside the window; label point = representative point inside the initial map view.
- **Lakes** — Natural Earth lakes (+ Europe supplement) ≥ 12 km², simplified 0.004°. Smaller lakes
  from the dataset are drawn as circles scaled to their area.
- **Cities** — German cities ≥ 150 000 inhabitants plus a list of hydrologically meaningful towns
  (Passau, Koblenz, Hann. Münden, Cuxhaven, …), foreign capitals and border cities.
- **States** — Bundesländer, Ramer–Douglas–Peucker 0.008–0.010°, islets < 0.06° dropped.
