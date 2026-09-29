#!/usr/bin/env python3
"""Match named rivers to the HydroRIVERS network (HydroSHEDS, 15 arc-seconds).

HydroRIVERS is a routed network: every reach knows the reach it drains into
(NEXT_DOWN), and its vertices run downstream. It has no names. For every river
we know source, mouth and length, so the course is a downstream walk:

  1. Candidates: reaches with a vertex within R_SRC of the documented source.
  2. From each candidate vertex, follow NEXT_DOWN. Cut the walk where it
     enters the parent's traced course (the confluence) if that lies near the
     documented mouth; otherwise at the vertex closest to the documented mouth
     (parent not traced: sea, lake, coastal water, or no match).
  3. Keep the candidate whose walked length best fits LEN_FACTOR × length_km,
     with penalties for the distance between the documented and the found
     source and mouth, and for the river's own tributary mouths that lie off
     the course. If nothing fits, widen the source radius. Reject if the mouth
     is too far off or the length is implausible.

Parents are traced before their tributaries, so every tributary ends exactly on
its parent's course. Courses are simplified (Ramer–Douglas–Peucker, SIMPLIFY_KM).

Output: data/generated/hydro.json        (read by build_geometry.py)
        build/hydro_report.json          (per river: match or reason for rejection)
Needs:  pyshp (requirements-geo.txt) and raw/hydrosheds/HydroRIVERS_v10_eu.shp
"""
from __future__ import annotations

import collections
import math

from common import BUILD, GENERATED, GEOMETRY_DIR, RAW, kmd, load_waters, read_json, write_json

try:
    import shapefile                                  # pyshp
except ImportError:  # pragma: no cover
    raise SystemExit("pyshp missing: pip install -r requirements-geo.txt")

SHP = RAW / "hydrosheds" / "HydroRIVERS_v10_eu_shp" / "HydroRIVERS_v10_eu.shp"
BBOX = (2.5, 44.0, 19.5, 57.0)                        # lon0, lat0, lon1, lat1 — as for GSHHG
CELL = 0.05                                           # grid cell of the vertex index, degrees
SIMPLIFY_KM = 0.12
LEN_WINDOW = (0.6, 1.45)                              # walked length / length_km


LEN_FACTOR = 0.89                                     # median walked length / length_km:
                                                      # 15" lines cut the smallest meanders
TRIB_CAP_KM = 8.0                                     # cap per tributary mouth off the course
STUB_KM = 1.5                                         # join the documented source up to this distance
SRC_MAX_KM = 15.0                                     # reject a course starting further off
                                                      # (short rivers: 30 % of the length)


def r_src(L):
    return max(3.0, min(10.0, 0.08 * L))


def r_mouth(L):
    return max(5.0, min(15.0, 0.15 * L))


class Network:
    def __init__(self, path):
        lon0, lat0, lon1, lat1 = BBOX
        sf = shapefile.Reader(str(path))
        names = [f[0] for f in sf.fields[1:]]
        i_id, i_next = names.index("HYRIV_ID"), names.index("NEXT_DOWN")
        i_up = names.index("UPLAND_SKM")
        self.pts, self.next, self.up = {}, {}, {}
        for sr in sf.iterShapeRecords():
            b = sr.shape.bbox
            if b[2] < lon0 or b[0] > lon1 or b[3] < lat0 or b[1] > lat1:
                continue
            rec = sr.record
            rid = rec[i_id]
            self.pts[rid] = [(round(y, 5), round(x, 5)) for x, y in sr.shape.points]
            self.next[rid] = rec[i_next]
            self.up[rid] = rec[i_up]
        self.grid = collections.defaultdict(list)
        for rid, pts in self.pts.items():
            for k, p in enumerate(pts):
                self.grid[(int(p[0] // CELL), int(p[1] // CELL))].append((rid, k))
        print(f"HydroRIVERS: {len(self.pts)} reaches, "
              f"{sum(len(p) for p in self.pts.values())} vertices in the window")

    def near(self, p, radius_km):
        """(distance, reach, vertex index) of the closest vertex per reach within radius."""
        dlat = radius_km / 111.2
        dlon = radius_km / (111.2 * math.cos(math.radians(p[0])))
        best = {}
        for i in range(int((p[0] - dlat) // CELL), int((p[0] + dlat) // CELL) + 1):
            for j in range(int((p[1] - dlon) // CELL), int((p[1] + dlon) // CELL) + 1):
                for rid, k in self.grid.get((i, j), ()):
                    d = kmd(self.pts[rid][k], p)
                    if d <= radius_km and (rid not in best or d < best[rid][0]):
                        best[rid] = (d, rid, k)
        return sorted(best.values())

    def walk(self, rid, k, max_km):
        """Downstream from vertex k of reach rid: list of (reach, vertex index, cum km)."""
        out, km, prev = [], 0.0, None
        while rid and rid in self.pts and km <= max_km:
            pts = self.pts[rid]
            for kk in range(k, len(pts)):
                if prev is not None:
                    km += kmd(prev, pts[kk])
                out.append((rid, kk, km))
                prev = pts[kk]
            rid, k = self.next.get(rid), 1            # vertex 0 repeats the previous end
        return out


def rdp(pts, eps_km):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        A, B = pts[a], pts[b]
        c = math.cos(math.radians(A[0]))
        ax, ay, bx, by = A[1] * c * 111.2, A[0] * 111.2, B[1] * c * 111.2, B[0] * 111.2
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        dmax, imax = 0.0, None
        for i in range(a + 1, b):
            px, py = pts[i][1] * c * 111.2, pts[i][0] * 111.2
            t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
            d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > dmax:
                dmax, imax = d, i
        if imax is not None and dmax > eps_km:
            keep[imax] = True
            stack += [(a, imax), (imax, b)]
    return [p for p, k in zip(pts, keep) if k]


def trace(net, w, mouth, tribs, free_length, parent_reaches):
    """Best downstream walk for w, or a string with the reason for rejection.

    tribs: mouths of w's own tributaries — the course should pass them all.
    free_length: the course is drawn to a point short of the real mouth (draw_end),
    so the length only has an upper bound.
    parent_reaches: HydroRIVERS reaches of the parent's course, if the parent is traced.
    """
    L = w["length_km"]
    for radius in (r_src(L), 2.5 * r_src(L), 4 * r_src(L)):
        r = best_walk(net, w, mouth, tribs, free_length, parent_reaches, radius)
        if isinstance(r, dict):
            r["radius"] = radius
            return r
    return r


def best_walk(net, w, mouth, tribs, free_length, parent_reaches, radius):
    L, S = w["length_km"], w["source"]
    best, seen = None, set()
    for ds, rid, k in net.near(S, radius):
        steps = net.walk(rid, k, LEN_WINDOW[1] * L + 30)
        if not steps:
            continue
        pts = [net.pts[r][kk] for r, kk, _ in steps]
        cut = min(range(len(pts)), key=lambda i: kmd(pts[i], mouth))
        # prefer the confluence: the last vertex before the walk enters the parent's course
        j = next((i for i, st in enumerate(steps) if st[0] in parent_reaches), None)
        if j == 0:
            continue                                  # starts on the parent itself
        if j is not None and kmd(pts[j - 1], mouth) <= r_mouth(L):
            cut = j - 1
        key = (steps[cut][0], steps[cut][1], steps[min(cut, 1)][0])
        if key in seen:
            continue
        seen.add(key)
        dm = kmd(pts[cut], mouth)
        if dm > 3 * r_mouth(L) and not (cut == len(pts) - 1 and not net.next.get(steps[cut][0])):
            continue
        # a walk from further upstream may pass the documented source: start there
        h = min(range(cut + 1), key=lambda i: kmd(pts[i], w["source"]))
        dh = kmd(pts[h], w["source"])
        if dh >= ds:
            h, dh = 0, ds
        walked = steps[cut][2] - steps[h][2] + dh
        course = pts[h:cut + 1:3] + [pts[cut]]
        miss = sum(min(TRIB_CAP_KM, min(kmd(t, p) for p in course)) for t in tribs)
        dlen = 0 if free_length and walked <= LEN_FACTOR * L else abs(walked - LEN_FACTOR * L)
        score = dlen + 2.0 * dm + 1.0 * dh + 3.0 * miss
        if best is None or score < best["score"]:
            best = {"steps": steps[h:cut + 1], "ds": dh, "dm": dm, "km": walked, "score": score,
                    "miss": miss, "outlet": cut == len(pts) - 1 and not net.next.get(steps[cut][0])}
    if best is None:
        return "kein_lauf"
    ratio = best["km"] / L
    if best["dm"] > r_mouth(L) and not best["outlet"]:
        return f"muendung_abseits: {best['dm']:.1f} km, {best['km']:.0f} of {L} km"
    if best["ds"] > min(SRC_MAX_KM, max(3.0, 0.3 * L)):
        return f"quelle_abseits: {best['ds']:.1f} km"
    if best["dm"] > 120:
        return f"muendung_abseits: {best['dm']:.1f} km from the network outlet"
    ends_hit = best["ds"] <= 2.5 and best["dm"] <= 2.5
    if ratio > LEN_WINDOW[1] or (ratio < LEN_WINDOW[0] and not free_length and not ends_hit):
        return f"laenge: {best['km']:.0f} of {L} km, mouth off {best['dm']:.1f} km"
    if tribs and best["miss"] > 0.5 * TRIB_CAP_KM * len(tribs):
        return f"zuflüsse_abseits: {best['miss']:.0f} km summed over {len(tribs)} tributaries"
    return best


def level(wid, by_id):
    d, seen = 0, set()
    while wid and wid in by_id and wid not in seen:
        seen.add(wid)
        wid = by_id[wid].get("parent")
        d += 1
    return d


def main() -> None:
    waters = load_waters()
    by_id = {w["id"]: w for w in waters}
    cfg = read_json(GEOMETRY_DIR / "config.json")
    draw_end = cfg["draw_end"]
    net = Network(SHP)

    children = collections.defaultdict(list)
    for w in waters:
        children[w.get("parent")].append(w)
    reaches = {}                                   # id -> HydroRIVERS reaches of its course
    out, report = {}, {}
    rivers = [w for w in waters if w["type"] == "river"]
    for w in sorted(rivers, key=lambda x: (level(x["id"], by_id), -(x.get("length_km") or 0))):
        wid = w["id"]
        if not w.get("length_km") or not w.get("source") or not w.get("mouth"):
            report[wid] = "keine_daten"
            continue
        mouth = draw_end.get(wid) or w["mouth"]
        tribs = [c["mouth"] for c in children[wid] if c["type"] == "river" and c.get("mouth")
                 and kmd(c["mouth"], w["source"]) > 2 and kmd(c["mouth"], mouth) > 2]
        r = trace(net, w, mouth, tribs, wid in draw_end, reaches.get(w.get("parent"), set()))
        if isinstance(r, str):
            report[wid] = r
            continue
        # the first reach may belong to a head stream (Werra above the Weser's source)
        reaches[wid] = {st[0] for st in r["steps"] if st[0] != r["steps"][0][0]}
        line = [list(net.pts[rid][k]) for rid, k, _ in r["steps"]]
        if 0.3 < r["ds"] <= STUB_KM:                   # further off: a straight stub looks wrong
            line = [list(w["source"])] + line
        if r["outlet"] and r["dm"] > 0.3:              # estuary: HydroRIVERS ends at its coastline
            line.append(list(mouth))
        line = [[round(p[0], 4), round(p[1], 4)] for p in rdp(line, SIMPLIFY_KM)]
        out[wid] = {"line": line, "km": round(r["km"]), "src_off": round(r["ds"], 1),
                    "mouth_off": round(r["dm"], 1), "trib_off": round(r["miss"], 1),
                    "radius": round(r["radius"], 1)}
        report[wid] = (f"ok: {r['km']:.0f} of {w['length_km']} km, source off {r['ds']:.1f} km, "
                       f"mouth off {r['dm']:.1f} km, tributaries off {r['miss']:.1f} km, "
                       f"{len(line)} points")
    write_json(GENERATED / "hydro.json", dict(sorted(out.items())), compact=True)
    write_json(BUILD / "hydro_report.json", dict(sorted(report.items())))
    fails = collections.Counter(v.split(":")[0] for v in report.values() if not v.startswith("ok"))
    print(f"traced {len(out)} of {len(rivers)} rivers, "
          f"{sum(len(v['line']) for v in out.values())} points; not matched: {dict(fails)}")


if __name__ == "__main__":
    main()
