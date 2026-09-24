#!/usr/bin/env python3
"""Flat CSV of all waters -> dist/gewaesser-deutschland.csv (semicolon, UTF-8 with BOM for Excel)."""
from __future__ import annotations

import csv

from common import DIST, GENERATED, ancestors, load_waters, read_json

TYPE_DE = {"river": "Fliessgewässer", "lake": "See/Talsperre", "canal": "Kanal",
           "coastal": "Küstengewässer", "sea": "Meer"}
COURSE_DE = {"gshhs": "vermessen", "ne": "vermessen", "kanal": "Wegpunkte", "schema": "schematisch"}
COLUMNS = ["id", "name", "typ", "status", "vorfluter_id", "vorfluter", "ordnung",
           "einzugsgebiet_meer", "laenge_km", "laenge_in_de_km", "flaeche_km2", "ufer",
           "muendung_ort", "muendung_lat", "muendung_lon", "quelle_lat", "quelle_lon",
           "bundeslaender", "verlauf_karte", "notiz"]


def main() -> None:
    waters = load_waters()
    by_id = {w["id"]: w for w in waters}
    src = read_json(GENERATED / "geometry.json")["src"]
    DIST.mkdir(parents=True, exist_ok=True)
    path = DIST / "gewaesser-deutschland.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        out = csv.writer(fh, delimiter=";")
        out.writerow(COLUMNS)
        for w in waters:
            chain = ancestors(w["id"], by_id)
            par = w.get("parent")
            mouth, source = w.get("mouth") or ["", ""], w.get("source") or ["", ""]
            out.writerow([
                w["id"], w["name"], TYPE_DE[w["type"]], "historisch" if w.get("historic") else "",
                par or "", by_id[par]["name"] if par else "", len(chain) - 1,
                by_id[chain[-1]]["name"], w.get("length_km") or "", w.get("length_de_km") or "",
                w.get("area_km2") or "", {"L": "links", "R": "rechts"}.get(w.get("side"), ""),
                w.get("mouth_place") or "", mouth[0], mouth[1], source[0], source[1],
                " ".join(w.get("states") or []), COURSE_DE.get(src.get(w["id"]), ""),
                w.get("note") or "",
            ])
    print(f"{path.relative_to(DIST.parent)} ({len(waters)} rows)")


if __name__ == "__main__":
    main()
