# Data sources and licences

This repository mixes code, a curated dataset and geometry derived from third-party sources.
Each part keeps its own terms.

| part | origin | licence |
|---|---|---|
| Code (`scripts/`, `web/`, `Makefile`, …) | this project | MIT, see [LICENSE](LICENSE) |
| Water records (`data/waters/`), hand-made geometry (`data/geometry/`) | this project; facts checked against the German Wikipedia | CC BY 4.0 — attribute "Gewässerstammbaum Deutschland" |
| River courses in `data/generated/hydro.json` and the `hydro` courses in `geometry.json` (almost all rivers) | [HydroRIVERS v1.0](https://www.hydrosheds.org/products/hydrorivers) (HydroSHEDS, 15 arc-second, Europe), B. Lehner & G. Grill | HydroSHEDS License Agreement: free for non-commercial and commercial use, see [hydrosheds.org](https://www.hydrosheds.org) for the full terms |
| Fallback river courses in `data/generated/traced.json` and the `gshhs` courses in `geometry.json` (rivers HydroRIVERS cannot match) | [GSHHG / WDBII](https://www.soest.hawaii.edu/pwessel/gshhg/), P. Wessel & W. H. F. Smith, read via the `basemap-data-hires` package | GNU LGPL (GSHHG ≥ 2.2.2) |
| Ocean, countries, lakes, cities (`base.json`), river lines (`ne_rivers.json`) | [Natural Earth](https://www.naturalearthdata.com/) 10 m, GeoJSON mirror [nvkelso/natural-earth-vector](https://github.com/nvkelso/natural-earth-vector) | public domain |
| Bundesländer outlines (`states.json`) | [isellsoap/deutschlandGeoJSON](https://github.com/isellsoap/deutschlandGeoJSON) (archived), which names DIVA-GIS as its data source | repository: Unlicense; upstream terms: see note |
| Poster fonts (downloaded at build time, embedded in the PDF) | Spectral, Archivo, IBM Plex Mono via [google/fonts](https://github.com/google/fonts) | SIL Open Font License 1.1 |

**Wikipedia.** Lengths, coordinates and mouth locations are facts taken from de.wikipedia.org
infoboxes; the one-line notes are written for this project. Please credit Wikipedia as the
factual source when you republish the dataset.

**Bundesländer outlines.** deutschlandGeoJSON itself is released under the Unlicense, but it
credits DIVA-GIS as the origin of the boundaries, and DIVA-GIS administrative areas are derived
from GADM, whose terms restrict commercial use and redistribution. Check those terms before any
commercial use; the clean alternative is BKG's VG250 (Datenlizenz Deutschland – Namensnennung 2.0),
which `prepare_base.py` could read instead.

**HydroRIVERS.** The network is downloaded by `fetch_sources.py` from data.hydrosheds.org (~68 MB, not
committed); only the matched courses, simplified, are stored in `data/generated/hydro.json`. HydroRIVERS is
derived from an elevation model, not surveyed, and has no river names; the assignment to named rivers is
done by this project (`scripts/trace_hydrosheds.py`). The HydroRIVERS documentation (§4.1) places it under the
same License Agreement as HydroSHEDS; read the agreement at [hydrosheds.org](https://www.hydrosheds.org)
before any redistribution.

**Citation for HydroRIVERS:** Lehner, B., Grill G. (2013): Global river hydrography and network routing:
baseline data and new approaches to study the world's large river systems. *Hydrological Processes*,
27(15): 2171–2186. Data is available at www.hydrosheds.org.

**Citation for GSHHG:** Wessel, P., and W. H. F. Smith (1996), A Global Self-consistent,
Hierarchical, High-resolution Shoreline Database, *J. Geophys. Res.*, 101, 8741–8743.
