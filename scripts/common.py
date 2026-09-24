"""Shared paths, I/O and geometry helpers for the Gewässerstammbaum pipeline.

Coordinate convention everywhere in this repo: **[lat, lon]** (not GeoJSON's
[lon, lat]). Only the raw Natural Earth / GeoJSON inputs use [lon, lat]; they
are converted when read.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data"
WATERS_DIR = DATA / "waters"          # canonical, hand-edited records
GEOMETRY_DIR = DATA / "geometry"      # hand-maintained geometry inputs
GENERATED = DATA / "generated"        # pipeline outputs that are committed
RAW = ROOT / "raw"                    # downloaded sources (git-ignored)
BUILD = ROOT / "build"                # scratch outputs (git-ignored)
DIST = ROOT / "dist"                  # publishable outputs (git-ignored)
WEB = ROOT / "web"

# Field order used when writing water records back to disk.
FIELD_ORDER = [
    "id", "name", "type", "parent", "side", "length_km", "length_de_km", "area_km2",
    "source", "mouth", "mouth_place", "states", "historic", "note",
]
REQUIRED_FIELDS = ["id", "name", "type", "parent", "side", "length_km", "source",
                   "mouth", "mouth_place", "states", "note"]

# File a record lives in, keyed by its order-1 ancestor (the water directly below a sea).
SYSTEM_FILES = {
    "rhein": "rhein.json", "elbe": "elbe.json", "donau": "donau.json",
    "weser": "weser.json", "ems": "ems.json", "oder": "oder.json", "maas": "maas.json",
}
SEA_FALLBACK_FILES = {"nordsee": "nordsee_weitere.json", "ostsee": "ostsee_weitere.json",
                      "schwarzes_meer": "donau.json"}
SEAS_FILE = "meere.json"


# --------------------------------------------------------------------------- I/O
def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, obj, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def ordered(record: dict) -> dict:
    out = {k: record[k] for k in FIELD_ORDER if k in record}
    for k in record:                      # keep unknown keys, but at the end
        if k not in out:
            out[k] = record[k]
    return out


def write_records(path: Path, records: list[dict]) -> None:
    """One record per line: readable in review, small diffs in git."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(ordered(r), ensure_ascii=False, separators=(", ", ": ")) for r in records]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"waters": [\n')
        fh.write(",\n".join(lines))
        fh.write("\n]}\n")


def load_waters() -> list[dict]:
    """All water records, in stable file order (meere first, then alphabetical)."""
    files = sorted(WATERS_DIR.glob("*.json"), key=lambda p: (p.name != SEAS_FILE, p.name))
    out = []
    for f in files:
        for w in read_json(f)["waters"]:
            w["_file"] = f.name
            out.append(w)
    return out


def strip_private(w: dict) -> dict:
    return {k: v for k, v in w.items() if not k.startswith("_")}


def ancestors(wid: str, by_id: dict) -> list[str]:
    """[wid, parent, grandparent, …, sea]"""
    chain, seen = [], set()
    while wid and wid not in seen:
        seen.add(wid)
        chain.append(wid)
        wid = by_id[wid].get("parent") if wid in by_id else None
    return chain


def sea_of(wid: str, by_id: dict) -> str:
    return ancestors(wid, by_id)[-1]


def file_for(wid: str, by_id: dict) -> str:
    chain = ancestors(wid, by_id)
    if len(chain) == 1:
        return SEAS_FILE
    top = chain[-2]
    return SYSTEM_FILES.get(top) or SEA_FALLBACK_FILES[chain[-1]]


# --------------------------------------------------------------------- geometry
def kmd(a, b) -> float:
    """Approximate distance in km between two [lat, lon] points."""
    return math.hypot((a[0] - b[0]) * 111.2,
                      (a[1] - b[1]) * 111.2 * math.cos(math.radians((a[0] + b[0]) / 2)))


def polyline_km(pts) -> float:
    return sum(kmd(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
