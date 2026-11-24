import csv
import heapq
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from astar_core import load_graph, astar, dijkstra, haversine

INF = math.inf
TOL = 1e-6


def reverse_graph(adj):
    radj = {u: {} for u in adj}
    for u, nbrs in adj.items():
        for v, w in nbrs.items():
            radj[v][u] = w
    return radj


def sssp(adj, src):
    dist = {src: 0.0}
    done = set()
    pq = [(0.0, src)]
    while pq:
        g, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        for v, w in adj[u].items():
            ng = g + w
            if ng < dist.get(v, INF):
                dist[v] = ng
                heapq.heappush(pq, (ng, v))
    return dist


def build_landmarks(adj, radj, nodes, k):
    t0 = time.perf_counter()
    start = sssp(adj, nodes[0])
    current = max(start, key=start.get)
    min_dist = {v: INF for v in nodes}
    landmarks, fwd, bwd, prep_s = [], [], [], []
    for i in range(k):
        dist_from = sssp(adj, current)
        dist_to = sssp(radj, current)
        landmarks.append(current)
        fwd.append(dist_from)
        bwd.append(dist_to)
        prep_s.append(time.perf_counter() - t0)
        if i == k - 1:
            break
        for v, d in dist_from.items():
            if d < min_dist[v]:
                min_dist[v] = d
        current = max((v for v in nodes if min_dist[v] < INF), key=min_dist.get)
    return landmarks, fwd, bwd, prep_s


def make_alt_h(coords, fwd, bwd, m, t):
    target = coords[t]
    terms = [(fwd[i], bwd[i], fwd[i].get(t, INF), bwd[i].get(t, INF)) for i in range(m)]

    def h(v):
        best = haversine(coords[v], target)
        for dist_from, dist_to, d_lt, d_tl in terms:
            if d_tl < INF:
                d_vl = dist_to.get(v, INF)
                if d_vl < INF and d_vl - d_tl > best:
                    best = d_vl - d_tl
            if d_lt < INF:
                d_lv = dist_from.get(v, INF)
                if d_lv < INF and d_lt - d_lv > best:
                    best = d_lt - d_lv
        return best

    return h


def timed(fn):
    t0 = time.perf_counter()
    res = fn()
    return res, (time.perf_counter() - t0) * 1000


def main():
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    ks = sorted(int(x) for x in sys.argv[3].split(",")) if len(sys.argv) > 3 else [16]
    coords, adj = load_graph(str(ROOT / "data" / "nodes.csv"), str(ROOT / "data" / "edges.csv"))
    radj = reverse_graph(adj)
    nodes = sorted(adj)
    n_nodes = len(nodes)
    landmarks, fwd, bwd, prep_s = build_landmarks(adj, radj, nodes, max(ks))
    print("landmarks", landmarks)
    rng = random.Random(seed)
    out = ROOT / "results" / "alt.csv"
    stats = {k: {"dij_exp": 0, "hav_exp": 0, "alt_exp": 0, "dij_ms": 0.0, "hav_ms": 0.0,
                 "alt_ms": 0.0, "ok": 0, "x3_wrong": 0} for k in ks}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n_landmarks", "prep_s", "table_entries", "src", "dst",
                    "dijkstra_m", "astar_m", "alt_m", "alt_x3_m",
                    "dijkstra_exp", "astar_exp", "alt_exp",
                    "dijkstra_ms", "astar_ms", "alt_ms"])
        done = 0
        while done < n_pairs:
            s, d = rng.sample(nodes, 2)
            (opt, _, dij_exp), dij_ms = timed(lambda: dijkstra(adj, s, d))
            if opt == INF or opt == 0:
                continue
            (hav_cost, _, hav_exp), hav_ms = timed(lambda: astar(adj, coords, s, d))
            for k in ks:
                def run_alt():
                    h = make_alt_h(coords, fwd, bwd, k, d)
                    return astar(adj, coords, s, d, h=h)
                (alt_cost, _, alt_exp), alt_ms = timed(run_alt)
                h = make_alt_h(coords, fwd, bwd, k, d)
                x3_cost, _, _ = astar(adj, coords, s, d, h=lambda v: 3 * h(v))
                st = stats[k]
                st["dij_exp"] += dij_exp
                st["hav_exp"] += hav_exp
                st["alt_exp"] += alt_exp
                st["dij_ms"] += dij_ms
                st["hav_ms"] += hav_ms
                st["alt_ms"] += alt_ms
                st["ok"] += abs(alt_cost - opt) <= TOL
                st["x3_wrong"] += x3_cost > opt + TOL
                w.writerow([k, f"{prep_s[k - 1]:.3f}", 2 * k * n_nodes, s, d,
                            f"{opt:.6f}", f"{hav_cost:.6f}", f"{alt_cost:.6f}", f"{x3_cost:.6f}",
                            dij_exp, hav_exp, alt_exp,
                            f"{dij_ms:.3f}", f"{hav_ms:.3f}", f"{alt_ms:.3f}"])
            done += 1
    n = n_pairs
    print("k,prep_s,table_entries,MB_float64,alt_correct,x3_wrong,"
          "exp_dijkstra,exp_astar,exp_alt,reduction_vs_astar_pct,ms_dijkstra,ms_astar,ms_alt")
    for k in ks:
        st = stats[k]
        entries = 2 * k * n_nodes
        red = 100 * (1 - st["alt_exp"] / st["hav_exp"])
        print(f"{k},{prep_s[k - 1]:.2f},{entries},{entries * 8 / 1e6:.2f},{st['ok']}/{n},{st['x3_wrong']}/{n},"
              f"{st['dij_exp'] / n:.0f},{st['hav_exp'] / n:.0f},{st['alt_exp'] / n:.0f},{red:.1f},"
              f"{st['dij_ms'] / n:.2f},{st['hav_ms'] / n:.2f},{st['alt_ms'] / n:.2f}")
    print("saved", out)


if __name__ == "__main__":
    main()
