#!/usr/bin/env python3
"""Match named rivers to the unnamed GSHHG/WDBII river network.

GSHHG gives ~80 000 accurately digitised river points for the region, but no
names. For every river (and canal) we know a source, a mouth and a length, so
we search the network for the path that best fits:

  1. Build a graph: consecutive points of a segment are joined with their real
     length; points of *different* segments closer than GAP_KM are joined by a
     "gap" edge whose weight is multiplied by GAP_PENALTY, so paths prefer real
     geometry and only jump where the digitising left holes.
  2. Anchor at whichever end (source or mouth) snaps closer to the network,
     run Dijkstra from there, and pick the node near the other end whose path
     length best matches the documented length (window 0.55–1.45 × length).
  3. Reject paths with too many gap jumps, detours outside an ellipse around
     source and mouth, or an untraced head/tail that is implausibly long.
     Partial matches are accepted when the untraced remainder is consistent
     with the missing length ("teil").

Rivers listed in data/geometry/via_points.json are traced leg by leg through
forced waypoints instead.

Output: data/generated/traced.json   (read by build_geometry.py)
        build/trace_report.json      (why each river was or was not matched)
Needs:  numpy, scipy (requirements-geo.txt) and raw/gshhs_rivers_f.json.
"""
from __future__ import annotations

import collections
import math

from common import BUILD, GENERATED, GEOMETRY_DIR, RAW, load_waters, read_json, write_json

try:
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    from scipy.spatial import cKDTree
except ImportError:  # pragma: no cover
    raise SystemExit("numpy/scipy missing: pip install -r requirements-geo.txt")

GAP_KM = 6.0
GAP_PENALTY = 8.0
LAT0 = 51.0
KX = 111.2 * math.cos(math.radians(LAT0))


def xy(p):
    """[lat, lon] -> planar km (good enough at German latitudes)."""
    return (p[1] * KX, p[0] * 111.2)


class Network:
    def __init__(self, segments):
        pts, segidx = [], []
        for si, s in enumerate(segments):
            for p in s:
                pts.append(xy(p))
                segidx.append(si)
        self.P = np.array(pts)
        n = len(self.P)
        edges = {}
        off = 0
        for s in segments:
            for i in range(len(s) - 1):
                d = math.dist(self.P[off + i], self.P[off + i + 1]) or 1e-6
                edges[(off + i, off + i + 1)] = (d, d, 0)
            off += len(s)
        self.tree = cKDTree(self.P)
        si = np.array(segidx)
        pairs = self.tree.query_pairs(GAP_KM, output_type="ndarray")
        for a, b in pairs[si[pairs[:, 0]] != si[pairs[:, 1]]]:
            a, b = int(a), int(b)
            if (a, b) not in edges and (b, a) not in edges:
                d = math.dist(self.P[a], self.P[b]) or 1e-6
                edges[(a, b)] = (d * GAP_PENALTY, d, 1)
        rows = np.fromiter((k[0] for k in edges), int, len(edges))
        cols = np.fromiter((k[1] for k in edges), int, len(edges))
        wgt = np.fromiter((v[0] for v in edges.values()), float, len(edges))
        self.G = coo_matrix((np.r_[wgt, wgt], (np.r_[rows, cols], np.r_[cols, rows])),
                            shape=(n, n)).tocsr()
        self.edge = {}
        for k, v in edges.items():
            self.edge[k] = v
            self.edge[(k[1], k[0])] = v
        print(f"network: {n} nodes, {len(edges)} edges")

    def latlon(self, i):
        return [round(float(self.P[i][1] / 111.2), 4), round(float(self.P[i][0] / KX), 4)]

    def path(self, pred, start, end):
        out = [end]
        while out[-1] != start:
            nxt = pred[out[-1]]
            if nxt < 0:
                return None
            out.append(int(nxt))
        return out                                   # end ... start

    def leg(self, A, B):
        ia = int(self.tree.query(xy(A))[1])
        ib = int(self.tree.query(xy(B))[1])
        dist, pred = dijkstra(self.G, directed=False, indices=ia, return_predecessors=True)
        if not np.isfinite(dist[ib]):
            return None
        p = self.path(pred, ia, ib)
        return p[::-1] if p else None


def trace_via(net, w, via):
    line = []
    for A, B in zip(via, via[1:]):
        p = net.leg(A, B)
        seg = [list(A), list(B)] if p is None else [net.latlon(j) for j in p]
        line += seg if not line else seg[1:]
    geo = sum(math.dist(xy(line[i]), xy(line[i + 1])) for i in range(len(line) - 1))
    return {"line": line, "head_km": 0, "tail_km": 0, "q": "voll",
            "traced_km": round(geo), "real_km": w.get("length_km"), "gap_km": 0}


def trace(net, w, draw_end, exempt):
    L, src = w.get("length_km"), w.get("source")
    mth = draw_end.get(w["id"]) or w.get("mouth")
    if not L or not src or not mth:
        return None
    S, M = xy(src), xy(mth)
    straight = math.dist(S, M)
    if straight < 3:
        return "zu_kurz"
    ds, ai = net.tree.query(S)
    dm, bi = net.tree.query(M)
    lim = min(130.0, max(18.0, 0.55 * L))
    if min(ds, dm) > lim:
        return "kein_treffer"
    if ds <= dm:
        anchor, other = int(ai), M
    else:
        anchor, other = int(bi), S
    asnap = min(ds, dm)
    dist, pred = dijkstra(net.G, directed=False, indices=anchor, return_predecessors=True)
    best, best_score = None, 1e18
    for c in net.tree.query_ball_point(other, lim):
        dd = dist[c]
        if not np.isfinite(dd):
            continue
        snap = math.dist(net.P[c], other)
        total = dd + snap + asnap
        if total < 0.55 * L or total > 1.45 * L:
            continue
        score = abs(total - L) + 0.8 * snap
        if score < best_score:
            best_score, best = score, c
    if best is None:
        return "kein_lauf"
    path = net.path(pred, anchor, best)               # best ... anchor
    if path is None:
        return "getrennt"
    geo = gap = 0.0
    for i in range(len(path) - 1):
        _, gl, is_gap = net.edge[(path[i], path[i + 1])]
        geo += gl
        gap += gl * is_gap
    if gap > 0.25 * geo:
        return "luecken"
    ellipse = max(1.9 * L, straight + 90)
    for i in path[::max(1, len(path) // 50)]:
        if math.dist(S, net.P[i]) + math.dist(net.P[i], M) > ellipse:
            return "umweg"
    if ds <= dm:
        path = path[::-1]                             # orient source -> mouth
    line = [net.latlon(i) for i in path]
    hs, he = math.dist(xy(line[0]), S), math.dist(xy(line[-1]), M)
    quality = "voll"
    if w["id"] not in exempt:
        hcap = min(85.0, max(25.0, 0.45 * straight))
        full = geo >= 0.50 * L and hs <= hcap and he <= hcap and hs + he <= 0.45 * L
        if not full:
            miss = max(1.0, L - geo)
            if not (geo >= 0.35 * L and hs + he <= 0.85 * miss and hs <= 0.85 * miss
                    and he <= 0.85 * miss):
                return "kein_teilstueck"
            quality = "teil"
    if hs > 2:
        line = [[round(src[0], 4), round(src[1], 4)]] + line
    if he > 2:
        line = line + [[round(mth[0], 4), round(mth[1], 4)]]
    return {"line": line, "head_km": round(hs), "tail_km": round(he), "q": quality,
            "traced_km": round(geo), "real_km": L, "gap_km": round(gap)}


def main() -> None:
    waters = load_waters()
    cfg = read_json(GEOMETRY_DIR / "config.json")
    via = {k: [list(p) for p in v] for k, v in read_json(GEOMETRY_DIR / "via_points.json")["via"].items()}
    draw_end = cfg["draw_end"]
    exempt = set(cfg["trace_full_course_exempt"])
    net = Network(read_json(RAW / "gshhs_rivers_f.json"))

    traced, report = {}, {}
    for w in sorted(waters, key=lambda x: -(x.get("length_km") or 0)):
        if w["type"] not in ("river", "canal"):
            continue
        r = trace_via(net, w, via[w["id"]]) if w["id"] in via else trace(net, w, draw_end, exempt)
        if isinstance(r, dict):
            traced[w["id"]] = r
            report[w["id"]] = f"{r['q']}: {r['traced_km']} of {r['real_km']} km, head {r['head_km']} km"
        elif r:
            report[w["id"]] = r
    write_json(GENERATED / "traced.json", dict(sorted(traced.items())), compact=True)
    write_json(BUILD / "trace_report.json", dict(sorted(report.items())))
    fails = collections.Counter(v for v in report.values() if ":" not in v)
    print(f"traced {len(traced)} "
          f"({collections.Counter(t['q'] for t in traced.values())}); not matched: {dict(fails)}")


if __name__ == "__main__":
    main()
