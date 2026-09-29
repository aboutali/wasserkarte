# Pipeline

```
                     ┌──────────────────── tier 3: heavy geo stack, network ─────────────────────┐
 Natural Earth  ─┐   │                                                                            │
 deutschland-    ├─► fetch_sources.py ─► raw/ ─┬─► prepare_base.py ─► data/generated/base.json     │
   GeoJSON       │   (+ GSHHG via basemap)     │                      data/generated/states.json   │
 HydroRIVERS   ──┤                             │                      data/generated/ne_rivers.json│
 GSHHG/WDBII   ──┘                             ├─► trace_hydrosheds.py ─► data/generated/hydro.json│
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
| `trace_hydrosheds.py` | `raw/hydrosheds/…/HydroRIVERS_v10_eu.shp`, waters, `data/geometry/*` | `hydro.json`, `build/hydro_report.json` | pyshp |
| `trace_rivers.py` | `raw/gshhs_rivers_f.json`, waters, `via_points.json`, `config.json` | `traced.json`, `build/trace_report.json` | numpy, scipy |
| `build_geometry.py` | waters, `data/geometry/*`, `hydro.json`, `traced.json`, `ne_rivers.json` | `geometry.json` | stdlib |
| `validate.py` | waters, `geometry.json` | — (`--fix` rewrites waters) | stdlib |
| `build_site.py` | waters, `data/generated/*`, `web/*.template.html` | `dist/`, `build/poster.html` | stdlib |
| `export_csv.py` | waters, `geometry.json` | `dist/gewaesser-deutschland.csv` | stdlib |
| `render.mjs` | `dist/index.html`, `build/poster.html` | PDF, screenshots | playwright |

## Tracing in HydroRIVERS (trace_hydrosheds.py)

[HydroRIVERS](https://www.hydrosheds.org/products/hydrorivers) v1.0 (HydroSHEDS, 15 arc-second, Europe tile;
`fetch_sources.py` downloads `HydroRIVERS_v10_eu_shp.zip`, ~68 MB, to `raw/hydrosheds/`) is a river network
derived from an elevation model. It is *routed*: every reach knows the reach it drains into (`NEXT_DOWN`) and
its vertices run downstream. It has no names. Since source, mouth and length of every river are known, the
course is found by walking the network downstream:

1. **Candidates.** Reaches with a vertex near the documented source: radius max(3, min(10, 0.08 L)) km,
   widened ×2.5 and then ×4 if nothing fits.
2. **Walk.** From each candidate follow `NEXT_DOWN`. If the walk passes closer to the documented source
   than its start, it starts there. Parents are traced before their tributaries. The walk ends where it
   enters the parent's course (the confluence), if that lies near the documented mouth; otherwise at the
   vertex nearest the documented mouth (or `draw_end`). A candidate is dropped when it joins the parent
   elsewhere before reaching the mouth (a neighbouring stream), or when it runs more than max(2, 0.1 L) km
   through reaches another river already claimed (two siblings would share one line).
3. **Score** (lowest wins): `|walked − 0.89·L| + 2·mouth distance + source distance + 3·Σ tributary distances`.
   The last term sums how far the mouths of the river's own tributaries lie from the walked course (capped
   at 8 km each), which separates a river from a neighbour with a similar length. The factor 0.89 is the
   median walked/documented length ratio: 15" lines cut the smallest meanders.
4. **Rejections.** Mouth more than max(5, min(15, 0.15 L)) km off the walk's end, except when the walk
   reaches the network outlet (an estuary; a straight tail to the mouth is then added); source more than
   min(15, max(3, 0.3 L)) km off the course; walked/documented length outside 0.6–1.45 (short courses pass
   when source and mouth both lie within 2.5 km); tributary mouths far off the course. The documented
   source is joined to the course only within 1.5 km; further off, the course starts where the network
   starts (HydroRIVERS begins at 10 km² catchment), since a straight stub would look wrong.
5. **Simplification.** Ramer–Douglas–Peucker at 0.12 km.

Because the walk starts at the documented source, a wrong source coordinate yields a wrong or missing
match: check the coordinates against de.wikipedia first. `build/hydro_report.json` states for every river
the chosen match or the reason for rejection; the rivers it lists as unmatched fall back to GSHHG, Natural
Earth or the schematic course. The Elbe gets its estuary tail from `manual_courses.json`.

## Tracing in GSHHG (trace_rivers.py)

GSHHG/WDBII is the fallback for rivers HydroRIVERS cannot match. It contains ~80 000 digitised river points around Germany but no names. For every river
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

Priority `kanal` → `hydro` → `gshhs` → `ne` → `schema`, then snapping and clipping; see CLAUDE.md.
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
