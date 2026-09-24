#!/usr/bin/env python3
"""Check the water records (and, if present, the generated geometry).

    python scripts/validate.py          # report; exit 1 on errors
    python scripts/validate.py --fix    # also rewrite data/waters/*.json canonically
                                        # (record in the right file, key order, one per line)

Errors break the build; warnings are things a human should look at.
Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict

from common import (GENERATED, GEOMETRY_DIR, REQUIRED_FIELDS, WATERS_DIR, ancestors, file_for,
                    kmd, load_waters, polyline_km, read_json, strip_private, write_records)

TYPES = {"river", "lake", "canal", "coastal", "sea"}
# German states: ISO 3166-2:DE suffix (2 letters). Foreign countries: ISO 3166-1 alpha-3.
STATES = set("BW BY BE BB HB HH HE MV NI NW RP SL SN ST SH TH".split())
COUNTRIES = set("AUT CHE FRA LUX NLD BEL CZE POL DNK".split())
ID_RE = re.compile(r"^[a-z0-9_]+$")
# ASCII transcriptions that should be written with umlauts (heuristic, warning only).
TRANSCRIBED = re.compile(r"\b\w*(?:muend|fluess|groess|laeng|suedl|oestl|ueber|fuer|waesser)\w*\b",
                         re.IGNORECASE)
NOTE_MAX = 120


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="rewrite data files canonically")
    args = ap.parse_args()

    waters = load_waters()
    errors, warnings = [], []
    err, warn = errors.append, warnings.append

    ids = Counter(w.get("id") for w in waters)
    for i, n in ids.items():
        if n > 1:
            err(f"{i}: id used {n} times")
    by_id = {w["id"]: w for w in waters if "id" in w}

    for w in waters:
        wid = w.get("id", "?")
        loc = f"{w['_file']}:{wid}"
        for f in REQUIRED_FIELDS:
            if f not in w:
                err(f"{loc}: missing field '{f}'")
        if not ID_RE.match(wid):
            err(f"{loc}: id must match {ID_RE.pattern}")
        t = w.get("type")
        if t not in TYPES:
            err(f"{loc}: unknown type {t!r}")
        par = w.get("parent")
        if t == "sea":
            if par is not None:
                err(f"{loc}: a sea has no parent")
        elif par not in by_id:
            err(f"{loc}: parent {par!r} does not exist")
        if w.get("side") not in (None, "L", "R"):
            err(f"{loc}: side must be 'L', 'R' or null")
        if w.get("side") and par in by_id and by_id[par]["type"] in ("sea", "coastal"):
            warn(f"{loc}: side is set, but the parent is a sea/coastal water")
        for key in ("source", "mouth"):
            p = w.get(key)
            if p is None:
                if t not in ("sea",) and key == "mouth":
                    err(f"{loc}: {key} missing")
                if t in ("river", "canal") and key == "source":
                    err(f"{loc}: {key} missing")
                continue
            if not (isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)):
                err(f"{loc}: {key} must be [lat, lon]")
            elif t != "sea" and not (44 <= p[0] <= 58 and 2 <= p[1] <= 30):
                err(f"{loc}: {key} {p} is outside the region — lat/lon swapped?")
        for s in w.get("states") or []:
            if s not in STATES | COUNTRIES:
                err(f"{loc}: unknown state/country code {s!r}")
        L = w.get("length_km")
        if L is not None and (not isinstance(L, (int, float)) or L < 0):
            err(f"{loc}: length_km must be a positive number or null")
        if t in ("river", "canal") and L is None:
            warn(f"{loc}: no length_km")
        if t in ("river", "canal") and L and w.get("source") and w.get("mouth"):
            if kmd(w["source"], w["mouth"]) > L * 1.05:
                warn(f"{loc}: source-mouth distance exceeds length_km ({L} km)")
        if t == "lake" and not w.get("area_km2"):
            warn(f"{loc}: lake without area_km2")
        for key in ("name", "note", "mouth_place"):
            v = w.get(key) or ""
            if "ß" in v:
                err(f"{loc}: {key} contains 'ß' — project convention is 'ss'")
            if key != "name" and TRANSCRIBED.search(v):
                warn(f"{loc}: {key} looks ASCII-transcribed ({TRANSCRIBED.search(v).group(0)}), use umlauts")
        if len(w.get("note") or "") > NOTE_MAX:
            warn(f"{loc}: note longer than {NOTE_MAX} characters")
        if wid in by_id and par in by_id:
            chain = ancestors(wid, by_id)
            if by_id[chain[-1]]["type"] != "sea":
                err(f"{loc}: ancestry does not end in a sea ({' <- '.join(chain)})")
            elif file_for(wid, by_id) != w["_file"]:
                (warn if args.fix else err)(
                    f"{loc}: belongs in {file_for(wid, by_id)} (run validate.py --fix)")

    # --- generated geometry (optional)
    geo_file = GENERATED / "geometry.json"
    if geo_file.exists() and not errors:
        geo = read_json(geo_file)
        lines, src = geo["lines"], geo["src"]
        routes = read_json(GEOMETRY_DIR / "canal_routes.json")["routes"]
        box = read_json(GEOMETRY_DIR / "config.json")["draw_bbox"]

        def inside(p):
            return box["lat"][0] <= p[0] <= box["lat"][1] and box["lon"][0] <= p[1] <= box["lon"][1]
        for w in waters:
            if w["type"] not in ("river", "canal"):
                continue
            if w["id"] not in lines:
                warn(f"{w['id']}: no drawn course — run `make geometry`")
                continue
            L = w.get("length_km")
            clipped = not (inside(w["source"]) and inside(w["mouth"]))
            if L and not clipped and src.get(w["id"]) in ("gshhs", "kanal"):
                r = polyline_km(lines[w["id"]]) / L
                lo, hi = (0.75, 1.25) if src[w["id"]] == "kanal" else (0.3, 1.6)
                if not lo <= r <= hi and w["id"] not in ("donau", "rhein", "elbe", "oder"):
                    warn(f"{w['id']}: drawn course is {r:.0%} of length_km ({src[w['id']]})")
        for cid in routes:
            if cid not in by_id or by_id[cid]["type"] != "canal":
                err(f"canal_routes.json: {cid} is not a canal record")
        stale = sorted(set(lines) - set(by_id))
        if stale:
            warn(f"geometry.json has courses for unknown ids {stale[:5]} — run `make geometry`")

    if args.fix and not any("belongs in" not in e for e in errors):
        groups = defaultdict(list)
        for w in waters:
            groups[file_for(w["id"], by_id)].append(strip_private(w))
        for f in WATERS_DIR.glob("*.json"):
            if f.name not in groups:
                f.unlink()
        for name, recs in groups.items():
            write_records(WATERS_DIR / name, recs)
        errors = [e for e in errors if "belongs in" not in e]
        print(f"rewrote {len(groups)} files in {WATERS_DIR.relative_to(WATERS_DIR.parents[1])}")

    for w_ in warnings:
        print("warning:", w_)
    for e in errors:
        print("ERROR:  ", e)
    types = Counter(w.get("type") for w in waters)
    print(f"\n{len(waters)} waters ({', '.join(f'{v} {k}' for k, v in types.most_common())}); "
          f"{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
