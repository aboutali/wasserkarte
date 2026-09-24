#!/usr/bin/env python3
"""Download the raw geodata the heavy pipeline needs into raw/ (git-ignored).

    python scripts/fetch_sources.py            # everything that is missing
    python scripts/fetch_sources.py --force    # re-download
    python scripts/fetch_sources.py --fonts    # only the poster fonts (build/fonts)

Sources
  * Natural Earth 10m vector layers (public domain), GeoJSON mirror on GitHub
  * German state borders, isellsoap/deutschlandGeoJSON (medium resolution)
  * GSHHG / WDBII river network, full resolution, read through the
    `basemap-data-hires` package (needs requirements-geo.txt)
  * Spectral, Archivo and IBM Plex Mono from the google/fonts repository (OFL),
    only used to render the print poster
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

from common import BUILD, RAW, write_json

NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
NE_LAYERS = [
    "ne_10m_rivers_europe", "ne_10m_rivers_lake_centerlines",
    "ne_10m_admin_0_countries", "ne_10m_ocean", "ne_10m_lakes", "ne_10m_lakes_europe",
    "ne_10m_populated_places",
]
STATES_URL = ("https://raw.githubusercontent.com/isellsoap/deutschlandGeoJSON/main/"
              "2_bundeslaender/3_mittel.geo.json")
FONT_BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {
    "Spectral-Regular.ttf": "spectral/Spectral-Regular.ttf",
    "Spectral-Medium.ttf": "spectral/Spectral-Medium.ttf",
    "Spectral-SemiBold.ttf": "spectral/Spectral-SemiBold.ttf",
    "Spectral-Italic.ttf": "spectral/Spectral-Italic.ttf",
    "Spectral-MediumItalic.ttf": "spectral/Spectral-MediumItalic.ttf",
    "IBMPlexMono-Regular.ttf": "ibmplexmono/IBMPlexMono-Regular.ttf",
    "IBMPlexMono-Medium.ttf": "ibmplexmono/IBMPlexMono-Medium.ttf",
    "Archivo.ttf": "archivo/Archivo%5Bwdth,wght%5D.ttf",
}
# GSHHG extraction window (lon0, lat0, lon1, lat1) — wider than the map on purpose,
# so the Rhine delta and the Czech Elbe/Moldau are part of the network.
GSHHS_BBOX = (2.5, 44.0, 19.5, 57.0)


def download(url: str, dest, force: bool) -> None:
    if dest.exists() and not force:
        print(f"  ok      {dest.relative_to(dest.parents[1])}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetch   {url}")
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as fh:
        fh.write(r.read())


def extract_gshhs(dest, force: bool) -> None:
    if dest.exists() and not force:
        print("  ok      raw/gshhs_rivers_f.json")
        return
    try:
        import warnings
        warnings.filterwarnings("ignore")
        from mpl_toolkits.basemap import Basemap
    except ImportError:
        sys.exit("basemap is missing: pip install -r requirements-geo.txt")
    lon0, lat0, lon1, lat1 = GSHHS_BBOX
    m = Basemap(projection="cyl", llcrnrlon=lon0, llcrnrlat=lat0,
                urcrnrlon=lon1, urcrnrlat=lat1, resolution="f")
    segs, _ = m._readboundarydata("rivers")
    out = [[[round(y, 4), round(x, 4)] for x, y in s] for s in segs if len(s) > 1]
    write_json(dest, out, compact=True)
    print(f"  wrote   raw/gshhs_rivers_f.json  ({len(out)} segments, "
          f"{sum(len(s) for s in out)} points)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fonts", action="store_true", help="only download the poster fonts")
    a = ap.parse_args()

    if not a.fonts:
        print("Natural Earth")
        for layer in NE_LAYERS:
            download(NE_BASE + layer + ".geojson", RAW / "ne" / f"{layer}.geojson", a.force)
        print("Bundesländer")
        download(STATES_URL, RAW / "bundeslaender.geojson", a.force)
        print("GSHHG rivers")
        extract_gshhs(RAW / "gshhs_rivers_f.json", a.force)
    print("Fonts")
    for name, path in FONTS.items():
        download(FONT_BASE + path, BUILD / "fonts" / name, a.force)


if __name__ == "__main__":
    main()
