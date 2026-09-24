---
description: Add one or more waters (river, lake, canal, coastal water) to the dataset, verified against de.wikipedia
argument-hint: <name(s)> [e.g. "Lenne, Volme"]
---

Add these waters to the dataset: $ARGUMENTS

For each one:

1. Check it is not already there: `grep -il '"name": "<name>' data/waters/*.json` (also try the id slug).
2. Look it up on de.wikipedia.org (WebSearch/WebFetch). Take from the infobox: length, source and
   mouth coordinates (convert to decimal degrees, `[lat, lon]`, 4 decimals), mouth location, the
   receiving water and on which bank it enters (looking downstream along the receiving water).
   Anything you cannot verify is `null` — never estimate a length.
3. Make sure the receiving water exists as a record; if not, add it first (same procedure).
4. Append the record to any file in `data/waters/` following docs/DATA_MODEL.md
   (German name with umlauts, `ss` not `ß`, states: 2-letter Bundesland / 3-letter country codes,
   note ≤ 95 characters), then run `make fix` so it lands in the right file.
5. `make check` — 0 errors; read any new warnings about the added records.
6. `make geometry` — the new water gets a schematic course unless it is traced (tier 3:
   `make trace geometry` if the raw sources are available). Mouths more than 16 km off the
   parent's drawn course will not snap: re-check the mouth coordinate if that happens.
7. `make site smoke`, then `make screenshots` and look at docs/img/map.png around the new water.
8. Summarise what you added with the Wikipedia URLs you used, and list anything left `null`.
