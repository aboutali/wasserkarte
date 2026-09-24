#!/usr/bin/env python3
"""Assemble the data bundle and render the HTML outputs.

    dist/index.html      interactive page (tree + map), single self-contained file
    dist/gewaesser.json  the bundle the page embeds (waters + geometry + base layers)
    build/poster.html    A0 print page, rendered to PDF by `node scripts/render.mjs poster`

Templates live in web/. They contain `__DATA__` (replaced by the bundle JSON)
and `{{name}}` placeholders for counts shown in the copy (see stats()).
Stdlib only.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from collections import Counter

from common import BUILD, DIST, GENERATED, WEB, ancestors, load_waters, read_json, strip_private

ORDER_WORDS = {1: "ersten", 2: "zweiten", 3: "dritten", 4: "vierten", 5: "fünften",
               6: "sechsten", 7: "siebten"}


def bundle() -> dict:
    waters = load_waters()
    by_id = {w["id"]: w for w in waters}
    out = []
    for w in waters:
        r = strip_private(w)
        r["sea"] = ancestors(w["id"], by_id)[-1]
        out.append(r)
    geo = read_json(GENERATED / "geometry.json")
    return {"waters": out, "lines": geo["lines"], "src": geo["src"],
            "states": read_json(GENERATED / "states.json"), "base": read_json(GENERATED / "base.json")}


def stats(b: dict) -> dict:
    W = b["waters"]
    by_id = {w["id"]: w for w in W}
    types = Counter(w["type"] for w in W)
    seas = Counter(w["sea"] for w in W)
    src = b["src"]
    return {
        "n_waters": len(W),
        "n_river": types["river"], "n_lake": types["lake"], "n_coastal": types["coastal"],
        "n_canal": types["canal"], "n_sea": types["sea"],
        "n_nordsee": seas["nordsee"], "n_ostsee": seas["ostsee"],
        "n_schwarzes_meer": seas["schwarzes_meer"],
        "n_surveyed": sum(1 for i, s in src.items() if s in ("gshhs", "ne") and by_id[i]["type"] == "river"),
        "n_schematic": sum(1 for s in src.values() if s == "schema"),
        "n_canal_routes": sum(1 for s in src.values() if s == "kanal"),
        "n_cities": len(b["base"]["cities"]),
        "max_order_word": ORDER_WORDS.get(max(len(ancestors(w["id"], by_id)) - 1 for w in W), "n-ten"),
        "year": str(datetime.date.today().year),
    }


def render(template: str, b: dict, st: dict) -> str:
    data = json.dumps(b, ensure_ascii=False, separators=(",", ":"))
    if "</script" in data.lower():
        sys.exit("bundle contains '</script' — would break the page")
    html = re.sub(r"\{\{(\w+)\}\}", lambda m: str(st[m.group(1)]), template)
    leftover = re.findall(r"\{\{\w+\}\}", html)
    if leftover:
        sys.exit(f"unfilled placeholders: {leftover}")
    return html.replace("__DATA__", data)


def main() -> None:
    b = bundle()
    st = stats(b)
    DIST.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    (DIST / "gewaesser.json").write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")),
                                         encoding="utf-8")
    page = render((WEB / "index.template.html").read_text(encoding="utf-8"), b, st)
    (DIST / "index.html").write_text(page, encoding="utf-8")
    poster = render((WEB / "poster.template.html").read_text(encoding="utf-8"), b, st)
    (BUILD / "poster.html").write_text(poster, encoding="utf-8")
    print(f"dist/index.html ({len(page) // 1024} KB), build/poster.html, dist/gewaesser.json — "
          f"{st['n_waters']} waters, {st['n_surveyed']} surveyed, {st['n_schematic']} schematic")


if __name__ == "__main__":
    main()
