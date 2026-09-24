# Data model

Every water body is one JSON record in `data/waters/*.json`. Records form a tree: `parent` points
to the water that receives this one (its *Vorfluter*); the three seas are the roots.

```
Nordsee ← Rhein ← Mosel ← Saar ← Blies
```

The *Ordnung* (order) of a water is its depth in that tree: 1 = drains directly into a sea or
coastal water, 2 = into an order-1 water, and so on (the dataset reaches order 5).

## Files

| file | contents |
|---|---|
| `meere.json` | the three roots: Nordsee, Ostsee, Schwarzes Meer |
| `rhein.json`, `elbe.json`, `donau.json`, `weser.json`, `ems.json`, `oder.json`, `maas.json` | one river system each, including its lakes and canals |
| `nordsee_weitere.json` | Deutsche Bucht (Wattenmeer, Jade, Dollart …), Eider, Vechte, Wiedau and their tributaries |
| `ostsee_weitere.json` | Baltic bays, Förden, Bodden, Haffs and the coastal rivers draining into them |

Placement is computed from the ancestry — add a record to any file and run `make fix`.
Records are stored one per line so a diff shows exactly which water changed.

## Fields

| field | required | type | meaning |
|---|---|---|---|
| `id` | ✓ | string `^[a-z0-9_]+$` | unique slug, umlauts transcribed (`fraenkische_saale`); homonyms get a suffix (`wuerm_amper`) |
| `name` | ✓ | string | German name with umlauts, `ss` instead of `ß` |
| `type` | ✓ | `river` `lake` `canal` `coastal` `sea` | |
| `parent` | ✓ | id or `null` | receiving water; `null` only for seas |
| `side` | ✓ | `"L"` `"R"` `null` | bank of the parent where the mouth lies, **looking downstream along the parent** |
| `length_km` | ✓ | number or `null` | total length; `null` for lakes, coastal waters, seas, and when undocumented |
| `length_de_km` | | number | length of the German section, if different |
| `area_km2` | | number | lakes and coastal waters |
| `source` | ✓ | `[lat, lon]` or `null` | source · lake centre · canal start · inner point of a coastal water |
| `mouth` | ✓ | `[lat, lon]` | mouth · lake outflow · canal end · opening to the sea |
| `mouth_place` | ✓ | string | e.g. `"Koblenz, Deutsches Eck"` |
| `states` | ✓ | list | German states as ISO 3166-2:DE suffix (`BY`, `BE` = Berlin), foreign countries as ISO 3166-1 alpha-3 (`AUT`, `BEL`, `NLD` …) |
| `historic` | | `true` | waterway out of service (Ludwigskanal, Eiderkanal) |
| `note` | ✓ | string | one concise fact, ideally ≤ 95 characters |

Example:

```json
{"id": "mosel", "name": "Mosel", "type": "river", "parent": "rhein", "side": "L", "length_km": 544.0, "length_de_km": 231, "source": [47.901, 6.885], "mouth": [50.364, 7.606], "mouth_place": "Koblenz, Deutsches Eck", "states": ["RP", "SL", "FRA", "LUX"], "note": "Grösster Nebenfluss des Rheins, Quelle in den Vogesen am Col de Bussang"}
```

JSON Schema: `schema/waters.schema.json` (editors can validate while typing — VS Code picks it up
from `.vscode/settings.json`). Cross-record rules are checked by `scripts/validate.py`.

## Rules of the tree

- **Scope.** Waters with a German connection: flowing through or along Germany, plus the foreign
  upper or lower course of a German river, so that every chain reaches the sea.
- **Lakes** hang on the water they drain into, even if a short outflow is not modelled
  (Königssee → Salzach is recorded as `parent: "inn"` with a note).
- **Canals** hang on the water their end point merges into. The other connection is named in `note`.
- **Coastal waters** nest inside each other (Kleines Haff → Stettiner Haff → Pommersche Bucht → Ostsee)
  and receive the coastal rivers (Peene → Peenestrom).
- **Source-river pairs** (Brigach/Breg, Weisser/Roter Main, Fränkische/Schwäbische Rezat) have `side: null`.

## Sources for facts

Lengths, mouth locations, banks and coordinates come from the infoboxes of the German Wikipedia.
The canal records were individually checked for length, end points, receiving water and operating
status. When adding a water, cite nothing in the record itself but verify against the article —
and prefer `null` over a guess.
