# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this is

A curated dataset of **523 German waters** (rivers, lakes, canals, coastal waters, 3 seas) organised
as a hydrological family tree — every water points to the water it drains into — plus a static
site that shows that tree next to a map, and an A0 print poster.

- UI, data and all user-facing copy are **German**. Code, comments and developer docs are English.
- Output is a single self-contained `dist/index.html` (data embedded as JSON), no framework, no bundler.

## Commands

```bash
make check        # validate data/waters — run after every data edit
make fix          # rewrite data/waters canonically (moves records to the right file, key order)
make site         # dist/index.html, dist/gewaesser.json, build/poster.html
make geometry     # recompute drawn courses (stdlib only) — run after changing coordinates,
                  #   parents, canal routes or manual courses; commit data/generated/geometry.json
make smoke        # headless-browser test of dist/index.html (needs `npm ci`)
make poster       # dist/gewaesserstammbaum-a0.pdf (downloads fonts on first run)
make screenshots  # docs/img/*.png
make serve        # http://localhost:8000
make geo          # FULL rebuild from raw sources: needs `pip install -r requirements-geo.txt`
```

Tier 1 (`check fix site csv geometry`) needs only the Python ≥ 3.10 standard library (output is identical on 3.10–3.13). Tier 2 (`smoke poster
screenshots`) needs Node ≥ 18 and `npm ci && npx playwright install chromium`. Tier 3
(`sources base trace geo`) needs the heavy geo stack and network access to raw.githubusercontent.com.

## Layout

```
data/waters/*.json       CANONICAL records, one per line, grouped by river system (hand-edited)
data/geometry/*.json     hand-maintained geometry inputs: canal routes, manual courses, via points, config
data/generated/*.json    pipeline outputs, COMMITTED so tiers 1–2 work without the geo stack
schema/waters.schema.json
scripts/                 pipeline (see docs/PIPELINE.md); common.py holds paths + helpers
web/*.template.html      page and poster templates: __DATA__ and {{placeholders}} are filled by build_site.py
docs/                    DATA_MODEL.md, PIPELINE.md, img/
raw/ build/ dist/        git-ignored
```

Which file a record lives in is derived from its ancestry (`common.file_for`): the order-1 system
(`rhein`, `elbe`, `donau`, `weser`, `ems`, `oder`, `maas`) or `nordsee_weitere` / `ostsee_weitere`.
Don't place records by hand — add them anywhere and run `make fix`.

## Data conventions (enforced by scripts/validate.py)

- Coordinates are **`[lat, lon]`** everywhere in this repo. Raw GeoJSON is `[lon, lat]` and is
  converted when read. Swapped coordinates are the most likely mistake; the validator catches most.
- `id`: `^[a-z0-9_]+$`, umlauts transcribed (`fraenkische_saale`); homonyms get the parent as suffix
  (`wuerm_amper`, `wuerm_nagold`, `schwalm_eder`, `schwalm_rur`).
- `name`, `note`, `mouth_place`: German **with umlauts**, but **`ss` instead of `ß`** (project convention).
- `parent`: the receiving water. Lakes hang on the water they drain into; canals on the water their
  **end point merges into** (Mittellandkanal → Elbe-Havel-Kanal, Datteln-Hamm-Kanal → Dortmund-Ems-Kanal).
- `side`: `"L"`/`"R"` = bank of the **parent**, looking **downstream along the parent**. Mosel → Rhein is `"L"`.
- `mouth` must lie on the parent's course; `make geometry` snaps it for drawing, but a mouth far
  off the parent (> 16 km, canals > 10 km) is a data error.
- `states`: German states as 2-letter ISO 3166-2:DE suffix (`BE` = Berlin); foreign countries as
  ISO 3166-1 **alpha-3** (`BEL` = Belgium, `NLD`, `FRA`, …). Never mix the two.
- `historic: true` for waterways out of service (drawn dotted).
- Facts (lengths, mouths, sides) come from **de.wikipedia.org infoboxes**. Don't invent values:
  unknown → `null`. When adding waters, verify length and mouth coordinates against the article.

## How the map geometry is decided

`scripts/build_geometry.py`, first match wins, recorded as `geometry.json["src"]`:

1. `kanal` — `data/geometry/canal_routes.json` (documented waypoints, drawn as straight segments)
2. `gshhs` — `data/generated/traced.json`, courses matched in the GSHHG/WDBII network by
   `trace_rivers.py` (Rhein gets its Alpenrhein head, Elbe its estuary from `manual_courses.json`)
3. `ne` — Natural Earth line (`ne_rivers.json` via `config.json:ne_aliases`) and/or a manual course
4. `schema` — source → own tributaries' mouths → mouth; 2-point courses become an S-curve scaled by
   sinuosity. Drawn lighter/thinner on purpose — the map must not pretend to be more accurate than it is.

Then mouths are snapped onto the parent's drawn course and everything is clipped to the drawing box.
`make geometry` is deterministic; CI fails if the committed `geometry.json` is stale.

To **fix a wrong course**: prefer adding forced waypoints to `data/geometry/via_points.json` and
re-running `make trace` (tier 3); otherwise add a hand-drawn chain to `manual_courses.json`
(used only when the river is not traced). Canals: edit `canal_routes.json`, keep the drawn length
within ~75–125 % of `length_km` (the validator warns otherwise).

## Verifying changes

- Data edits: `make check` must report 0 errors. Read the warnings you introduced.
- Geometry or template edits: `make site smoke`, then `make screenshots` and **look at the images**
  (docs/img/map.png, map-dark.png, mobile.png). Visual bugs don't show up in tests.
- Poster edits: `make poster`, look at `build/poster-preview.png`; the render warns if the tree
  overflows its five columns.
- Page templates must keep working in **light and dark** mode: colours come only from CSS custom
  properties defined in `:root`, the dark media query and `[data-theme="dark"]`.

## Gotchas

- `web/index.template.html` is ~50 KB of hand-written HTML/CSS/JS in one file on purpose (the page
  is also published as a single-file artifact). Keep it dependency-free; the only external request
  is Google Fonts, and the page must render acceptably without it.
- `{{name}}` placeholders in the templates are filled from `build_site.stats()`; an unknown or
  leftover placeholder aborts the build. Don't hard-code counts in the copy.
- The poster computes label sizes from its render width (`LS = rect.width / 1780`); render it via
  `scripts/render.mjs` (viewport 4500 px ≈ 1189 mm) or sizes will be off.
- Natural Earth "Spree" includes the lower Havel, "Weser" includes the Werra — clipping at the
  documented source/mouth handles it; keep that in mind when adding aliases.
- GSHHG has no Alpenrhein↔Hochrhein connection through the Bodensee and prefers the Aare as the
  Rhine's headwater; that is why the Rhein is traced via `via_points.json`.
- Seas keep the order of `data/waters/meere.json` in the tree (Nordsee, Ostsee, Schwarzes Meer).

## Known issues / backlog

- 300 of 413 rivers are schematic: GSHHG only contains the larger rivers. A better source
  (OSM waterways, EU-Hydro, BKG DLM250) would allow real courses for all of them.
- `make check` warnings worth resolving: missing lengths (Kleine Vils, Sagter Ems, Broklandsau,
  Husumer Au, Wörpe, Bongsieler Kanal), `boize`/`pader`/`ihme` source–mouth distance exceeds
  length (coordinates or length wrong), `maas` has a `side` although it drains into the sea.
- `data/generated/states.json` derives from isellsoap/deutschlandGeoJSON (DIVA-GIS source); see
  DATA_SOURCES.md before any commercial use.
- Ludwigskanal and Main-Donau-Kanal overlap between Nürnberg and Kelheim (they really run close);
  labels can collide there.
