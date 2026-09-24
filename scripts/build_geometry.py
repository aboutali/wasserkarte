#!/usr/bin/env python3
"""Decide the drawn course of every river and canal -> data/generated/geometry.json.

Priority per water (first match wins), recorded in geometry.json["src"]:

  kanal   documented canal route           data/geometry/canal_routes.json
  gshhs   traced GSHHG course              data/generated/traced.json
          (rhein: Alpenrhein head from manual_courses; elbe: estuary tail)
  ne      Natural Earth line (+ manual)    data/generated/ne_rivers.json + manual_courses.json
  schema  schematic: source -> own tributaries' mouths -> mouth; a 2-point
          course gets an S-curve whose amplitude follows the sinuosity
          (documented length / straight-line distance)

Afterwards every mouth is snapped onto the drawn course of its parent (so the
map is topologically identical to the tree), and points outside the drawing
box are clipped.

Stdlib only — runs without the heavy geo stack once traced.json and
ne_rivers.json exist (both are committed).
"""
from __future__ import annotations

import collections
import math

from common import GENERATED, GEOMETRY_DIR, kmd, load_waters, read_json, write_json


def chain_segments(segs, start):
    """Greedily chain Natural Earth segments into one polyline beginning near `start`."""
    segs = [list(s) for s in segs if len(s) > 1]
    if not segs:
        return []
    i, e = min(((i, e) for i, s in enumerate(segs) for e in (0, -1)),
               key=lambda t: kmd(segs[t[0]][t[1]], start))
    out = segs.pop(i)
    if e == -1:
        out.reverse()
    while segs:
        j, e2 = min(((j, e2) for j, s in enumerate(segs) for e2 in (0, -1)),
                    key=lambda t: kmd(segs[t[0]][t[1]], out[-1]))
        if kmd(segs[j][e2], out[-1]) > 45:
            break
        nxt = segs.pop(j)
        if e2 == -1:
            nxt.reverse()
        out += nxt[1:]
    return out


def clip_start(line, src, tol=40):
    if not line:
        return line
    k = min(range(len(line)), key=lambda i: kmd(line[i], src))
    return line if kmd(line[k], src) > tol else [list(src)] + line[k + 1:]


def clip_end(line, mouth, tol=60):
    if not line:
        return line
    k = min(range(len(line)), key=lambda i: kmd(line[i], mouth))
    return line if kmd(line[k], mouth) > tol else line[:k + 1] + [list(mouth)]


def thin(line, eps_km=1.2):
    """Drop points closer than eps_km to the previously kept one."""
    if len(line) < 3:
        return line
    out = [line[0]]
    for p in line[1:-1]:
        if kmd(out[-1], p) >= eps_km:
            out.append(p)
    out.append(line[-1])
    return out


def nearest_on(line, p):
    best, bp = 1e9, None
    c = math.cos(math.radians(p[0]))
    for a, b in zip(line, line[1:]):
        ax, bx, px = a[1] * c, b[1] * c, p[1] * c
        dx, dy = bx - ax, b[0] - a[0]
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (p[0] - a[0]) * dy) / L))
        q = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
        d = kmd(q, p)
        if d < best:
            best, bp = d, q
    return best, bp


def schematic(w, children, by_id):
    """Straight course refined with the confluences of the river's own tributaries."""
    src, mth = w["source"], w["mouth"]
    L = kmd(src, mth)
    cs = math.cos(math.radians(src[0]))
    dy, dx = mth[0] - src[0], (mth[1] - src[1]) * cs
    L2 = dy * dy + dx * dx
    pts = []
    for cid in children.get(w["id"], []):
        c = by_id[cid]
        if c["type"] != "river" or not c.get("mouth") or L2 == 0:
            continue
        p = c["mouth"]
        t = ((p[0] - src[0]) * dy + (p[1] - src[1]) * cs * dx) / L2
        perp = kmd(p, (src[0] + t * dy, src[1] + t * (mth[1] - src[1])))
        if 0.03 < t < 0.97 and perp < max(18, 0.30 * L):
            pts.append((t, list(p)))
    pts.sort()
    return [list(src)] + [p for _, p in pts] + [list(mth)]


def s_curve(wid, a, b, length_km):
    """Deterministic S-shaped course for a 2-point schematic river."""
    straight = kmd(a, b) or 1
    sinu = max(1.0, min(2.4, length_km / straight if length_km else 1.25))
    h = sum(ord(ch) * (k + 1) for k, ch in enumerate(wid))
    s = 1 if h % 2 else -1
    f = max(0.05, min(0.30, (sinu - 1) * 0.55 + 0.05))
    dy, dx = b[0] - a[0], b[1] - a[1]

    def at(t, o):
        return [round(a[0] + t * dy - o * dx, 4), round(a[1] + t * dx + o * dy, 4)]

    return [a, at(0.28, s * f), at(0.62, -s * f * 0.55), at(0.85, s * f * 0.20), b]


def main() -> None:
    waters = load_waters()
    by_id = {w["id"]: w for w in waters}
    cfg = read_json(GEOMETRY_DIR / "config.json")
    manual_cfg = read_json(GEOMETRY_DIR / "manual_courses.json")
    manual, prepend = manual_cfg["courses"], set(manual_cfg["prepend"])
    canals = read_json(GEOMETRY_DIR / "canal_routes.json")["routes"]
    traced = read_json(GENERATED / "traced.json")
    ne = read_json(GENERATED / "ne_rivers.json")
    aliases, ne_clip_end, draw_end = cfg["ne_aliases"], cfg["ne_clip_end"], cfg["draw_end"]

    children = collections.defaultdict(list)
    for w in waters:
        children[w.get("parent")].append(w["id"])

    geo, src_of = {}, {}
    for w in waters:
        if w["type"] in ("sea", "coastal", "lake") or not w.get("source") or not w.get("mouth"):
            continue
        wid, src, mth = w["id"], w["source"], w["mouth"]

        if w["type"] == "canal" and wid in canals:
            geo[wid], src_of[wid] = [list(p) for p in canals[wid]], "kanal"
            continue

        if wid in traced:
            line = [list(p) for p in traced[wid]["line"]]
            if wid == "rhein":                       # Alpenrhein head (GSHHG stops at the Bodensee)
                head = manual["rhein"]
                k = min(range(len(head)), key=lambda i: kmd(head[i], line[0]))
                line = [list(p) for p in head[:k]] + line[1:]
            if wid == "elbe":                        # estuary tail to Cuxhaven
                tail = manual["elbe"]
                k = min(range(len(line)), key=lambda i: kmd(line[i], tail[0]))
                line = line[:k] + [list(p) for p in tail]
            geo[wid], src_of[wid] = thin(line, 0.6), "gshhs"
            continue

        ne_line = chain_segments([s for n in aliases.get(wid, []) for s in ne.get(n, [])], src)
        ne_line = clip_start(ne_line, src)
        ne_line = clip_end(ne_line, ne_clip_end.get(wid, mth))
        man = [list(p) for p in manual.get(wid, [])]
        if ne_line and man:
            line = man + ne_line if wid in prepend else ne_line + man
        else:
            line = ne_line or man or schematic(w, children, by_id)
        src_of[wid] = "ne" if (ne_line or man) else "schema"
        if len(line) >= 2:
            line[0] = list(src)
            line[-1] = list(draw_end.get(wid, mth))
        geo[wid] = thin(line)

    # --- snap every mouth onto the drawn course of its parent, parents first
    def level(wid):
        d, seen = 0, set()
        while wid and wid in by_id and wid not in seen:
            seen.add(wid)
            wid = by_id[wid].get("parent")
            d += 1
        return d

    snapped = 0
    for wid in sorted(geo, key=level):
        par = by_id[wid].get("parent")
        if par not in geo or len(geo[par]) < 2:
            continue
        d, q = nearest_on(geo[par], geo[wid][-1])
        tol = cfg["snap_km"]["canal" if by_id[wid]["type"] == "canal" else "default"]
        if q and d < tol:
            geo[wid][-1] = [round(q[0], 4), round(q[1], 4)]
            snapped += 1

    # --- schematic 2-point courses become S-curves
    for wid, line in geo.items():
        if src_of.get(wid) == "schema" and len(line) == 2:
            geo[wid] = s_curve(wid, line[0], line[1], by_id[wid].get("length_km") or 0)

    # --- clip to the drawing box
    (la0, la1), (lo0, lo1) = cfg["draw_bbox"]["lat"], cfg["draw_bbox"]["lon"]

    def bbox_clip(line):
        out = []
        for p in line:
            if la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1:
                out.append(p)
            elif out:
                break
        return out if len(out) >= 2 else line

    lines = {k: [[round(p[0], 4), round(p[1], 4)] for p in bbox_clip(v)] for k, v in geo.items()}
    write_json(GENERATED / "geometry.json", {"lines": lines, "src": src_of}, compact=True)
    print(f"geometry.json  {len(lines)} courses, {sum(len(v) for v in lines.values())} points, "
          f"{snapped} mouths snapped, {dict(collections.Counter(src_of.values()))}")


if __name__ == "__main__":
    main()
