#!/usr/bin/env python3
"""Build the geographic base layers from raw/ into data/generated/.

Outputs
  data/generated/base.json    ocean, neighbouring countries (+ label points), lake polygons, cities
  data/generated/states.json  simplified Bundesländer outlines
  data/generated/ne_rivers.json  Natural Earth river segments for the names in config.ne_aliases

Needs: shapely (requirements-geo.txt) and `python scripts/fetch_sources.py`.
"""
from __future__ import annotations

import math
from collections import defaultdict

from common import GENERATED, GEOMETRY_DIR, RAW, read_json, write_json

try:
    from shapely.geometry import box, shape
    from shapely.ops import unary_union
except ImportError:  # pragma: no cover
    raise SystemExit("shapely is missing: pip install -r requirements-geo.txt")

NE = RAW / "ne"
CLIP = box(2.8, 45.3, 17.8, 56.8)          # everything outside is irrelevant for the map
MAP_VIEW = box(5.3, 46.6, 15.75, 55.35)    # initial map view, used to place country labels

COUNTRIES = {
    "DEU": "Deutschland", "FRA": "Frankreich", "CHE": "Schweiz", "AUT": "Österreich",
    "CZE": "Tschechien", "POL": "Polen", "DNK": "Dänemark", "NLD": "Niederlande",
    "BEL": "Belgien", "LUX": "Luxemburg", "ITA": "Italien", "SVN": "Slowenien",
    "SVK": "Slowakei", "HUN": "Ungarn", "GBR": "Grossbritannien", "SWE": "Schweden",
    "LIE": "Liechtenstein", "HRV": "Kroatien",
}
# German cities kept regardless of population (hydrologically meaningful places).
MUST_DE = {
    "Kiel", "Rostock", "Magdeburg", "Erfurt", "Passau", "Regensburg", "Trier", "Ulm", "Würzburg",
    "Münster", "Freiburg", "Flensburg", "Konstanz", "Cuxhaven", "Emden", "Schwerin", "Potsdam",
    "Görlitz", "Kassel", "Bamberg", "Koblenz", "Mainz", "Heilbronn", "Bremerhaven",
    "Wilhelmshaven", "Lübeck", "Osnabrück", "Aachen", "Hof", "Weimar", "Jena", "Halle",
    "Dessau", "Wittenberg", "Braunschweig", "Göttingen", "Gera", "Neubrandenburg", "Stralsund",
    "Greifswald", "Husum", "Duisburg", "Frankfurt (Oder)", "Frankfurt an der Oder",
}
MUST_DE_PREFIX = ("Halle", "Aachen", "Trier", "Cuxhaven", "Görlitz", "Greifswald",
                  "Wilhelmshaven", "Bamberg", "Weimar", "Konstanz", "Husum")
MUST_FOREIGN = {
    "Wien", "Prag", "Zürich", "Basel", "Amsterdam", "Rotterdam", "Brüssel", "Kopenhagen",
    "Strassburg", "Straßburg", "Salzburg", "Innsbruck", "Stettin", "Szczecin", "Luxemburg",
    "Linz", "Bratislava", "Breslau", "Wrocław", "Metz", "Nancy", "Enschede", "Groningen",
}
# Missing or oddly named in Natural Earth — added by hand (name, lat, lon, population).
EXTRA_CITIES = [
    ("Halle (Saale)", 51.482, 11.970, 238000), ("Aachen", 50.776, 6.084, 246000),
    ("Trier", 49.756, 6.641, 111000), ("Cuxhaven", 53.867, 8.700, 48000),
    ("Görlitz", 51.152, 14.987, 56000), ("Konstanz", 47.663, 9.175, 85000),
    ("Wilhelmshaven", 53.529, 8.113, 76000), ("Hann. Münden", 51.418, 9.650, 23000),
]


def rings_of(geom, tol):
    g = geom.intersection(CLIP)
    if g.is_empty:
        return []
    g = g.simplify(tol, preserve_topology=True)
    polys = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
    out = []
    for p in polys:
        if p.geom_type != "Polygon":
            continue
        for ring in [p.exterior] + list(p.interiors):
            c = [[round(y, 3), round(x, 3)] for x, y in ring.coords]
            if len(c) >= 4:
                out.append(c)
    return out


def ocean():
    feats = read_json(NE / "ne_10m_ocean.geojson")["features"]
    return rings_of(unary_union([shape(f["geometry"]) for f in feats]), 0.012)


def countries():
    out = []
    for f in read_json(NE / "ne_10m_admin_0_countries.geojson")["features"]:
        p = f["properties"]
        iso = p.get("ADM0_A3") or p.get("ISO_A3")
        if iso not in COUNTRIES:
            continue
        g = shape(f["geometry"])
        rings = rings_of(g, 0.012)
        if not rings:
            continue
        gi = g.intersection(MAP_VIEW)
        if gi.is_empty or gi.area < 0.15:
            gi = g.intersection(CLIP)
        c = gi.representative_point()
        out.append({"iso": iso, "name": COUNTRIES[iso], "rings": rings,
                    "label": [round(c.y, 3), round(c.x, 3)]})
    return out


def lakes():
    out, seen = [], set()
    for fn in ("ne_10m_lakes.geojson", "ne_10m_lakes_europe.geojson"):
        for f in read_json(NE / fn)["features"]:
            p = f["properties"]
            g = shape(f["geometry"])
            if not g.intersects(CLIP):
                continue
            area = g.area * 111.2 * 70
            if area < 12:
                continue
            key = (round(g.centroid.x, 2), round(g.centroid.y, 2))
            if key in seen:
                continue
            seen.add(key)
            rings = rings_of(g, 0.004)
            if rings:
                out.append({"name": p.get("name_de") or p.get("name") or "",
                            "rings": rings, "a": round(area)})
    return out


def cities():
    out = []
    for f in read_json(NE / "ne_10m_populated_places.geojson")["features"]:
        p = f["properties"]
        x, y = f["geometry"]["coordinates"]
        if not (3.2 <= x <= 17.4 and 45.6 <= y <= 56.4):
            continue
        iso, pop = p.get("ADM0_A3"), p.get("POP_MAX") or 0
        name = p.get("NAME_DE") or p.get("NAME")
        if iso == "DEU":
            keep = pop >= 150000 or name in MUST_DE or any(name.startswith(m) for m in MUST_DE_PREFIX)
        else:
            keep = name in MUST_FOREIGN or (
                p.get("FEATURECLA", "").startswith("Admin-0 capital") and pop >= 400000)
        if keep:
            out.append({"n": name, "lat": round(y, 3), "lon": round(x, 3), "pop": pop,
                        "de": 1 if iso == "DEU" else 0})
    have = {c["n"] for c in out}
    for name, lat, lon, pop in EXTRA_CITIES:
        if name not in have:
            out.append({"n": name, "lat": lat, "lon": lon, "pop": pop, "de": 1})
    out.sort(key=lambda c: -c["pop"])
    return out


def rdp(pts, eps):
    """Ramer–Douglas–Peucker on [lat, lon] points (degrees)."""
    if len(pts) < 3:
        return pts

    def dist(p, a, b):
        ay, ax = a
        by, bx = b
        py, px = p
        dy, dx = by - ay, bx - ax
        L = dy * dy + dx * dx
        if L == 0:
            return math.hypot(py - ay, px - ax)
        t = max(0, min(1, ((py - ay) * dy + (px - ax) * dx) / L))
        return math.hypot(py - ay - t * dy, px - ax - t * dx)

    stack, keep = [(0, len(pts) - 1)], {0, len(pts) - 1}
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        k, dmax = max(((k, dist(pts[k], pts[i], pts[j])) for k in range(i + 1, j)),
                      key=lambda x: x[1])
        if dmax > eps:
            keep.add(k)
            stack += [(i, k), (k, j)]
    return [pts[i] for i in sorted(keep)]


def states():
    out = []
    for f in read_json(RAW / "bundeslaender.geojson")["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = []
        for poly in polys:
            for ring in poly:
                pts = [[round(p[1], 4), round(p[0], 4)] for p in ring]
                s = rdp(pts, 0.010 if len(pts) > 4000 else 0.008)
                if len(s) < 5:
                    continue
                lats, lons = [p[0] for p in s], [p[1] for p in s]
                if max(lats) - min(lats) < 0.06 and max(lons) - min(lons) < 0.06:
                    continue                       # drop islets
                rings.append([[round(p[0], 3), round(p[1], 3)] for p in s])
        out.append({"id": f["properties"]["id"], "name": f["properties"]["name"], "rings": rings})
    return out


def ne_rivers():
    """Named Natural Earth river segments as [lat, lon], only for names we alias."""
    wanted = {n for names in read_json(GEOMETRY_DIR / "config.json")["ne_aliases"].values()
              for n in names}
    out = defaultdict(list)
    for fn in ("ne_10m_rivers_europe.geojson", "ne_10m_rivers_lake_centerlines.geojson"):
        for ft in read_json(NE / fn)["features"]:
            g = ft["geometry"]
            if not g:
                continue
            p = ft["properties"]
            name = p.get("name_de") or p.get("name")
            if name not in wanted:
                continue
            segs = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
            for s in segs:
                if any(4 <= x <= 20 and 45 <= y <= 56 for x, y in s):
                    out[name].append([[y, x] for x, y in s])
    return dict(out)


def main() -> None:
    base = {"ocean": ocean(), "countries": countries(), "lakes": lakes(), "cities": cities()}
    write_json(GENERATED / "base.json", base, compact=True)
    print("base.json      ocean %d rings, %d countries, %d lakes, %d cities" % (
        len(base["ocean"]), len(base["countries"]), len(base["lakes"]), len(base["cities"])))
    st = states()
    write_json(GENERATED / "states.json", st, compact=True)
    print("states.json    %d states, %d points" % (len(st), sum(len(r) for s in st for r in s["rings"])))
    ner = ne_rivers()
    write_json(GENERATED / "ne_rivers.json", ner, compact=True)
    print("ne_rivers.json %d names" % len(ner))


if __name__ == "__main__":
    main()
