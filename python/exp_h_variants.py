import csv
import heapq
import itertools
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
sys.path.insert(0, str(ROOT / "python"))

from astar_core import astar, haversine, load_graph
from astar_variants import SPEEDS, astar_time_dependent

EPSILONS = [0.1, 0.2, 0.4]
MODES = ["under", "both"]
TOL = 1e-6


def astar_reopen(adj, s, d, h):
    g = {s: 0.0}
    ctr = itertools.count()
    pq = [(h(s), next(ctr), 0.0, s)]
    seen = set()
    expanded = reexpanded = 0
    while pq:
        _, _, gu, u = heapq.heappop(pq)
        if gu != g[u]:
            continue
        if u == d:
            return gu, expanded, reexpanded
        expanded += 1
        if u in seen:
            reexpanded += 1
        seen.add(u)
        for v, w in adj[u].items():
            ng = gu + w
            if ng < g.get(v, math.inf):
                g[v] = ng
                heapq.heappush(pq, (ng + h(v), next(ctr), ng, v))
    return math.inf, expanded, reexpanded


def noisy_h(coords, d, unit, eps, mode):
    target = coords[d]
    if mode == "under":
        return lambda v: haversine(coords[v], target) * (1 - eps * unit[v])
    return lambda v: haversine(coords[v], target) * (1 + eps * (2 * unit[v] - 1))


def sample_pairs(adj, coords, nodes, n_pairs, seed):
    rng = random.Random(seed)
    pairs = []
    while len(pairs) < n_pairs:
        s, d = rng.sample(nodes, 2)
        opt, _, exp = astar(adj, coords, s, d)
        if opt == math.inf or opt == 0:
            continue
        pairs.append((s, d, opt, exp))
    return pairs


def run_noisy(adj, coords, nodes, pairs, seed, writer):
    stats = {(m, e): {"excess": [], "exp": 0, "reexp": 0, "ok": 0} for m in MODES for e in EPSILONS}
    base_exp = 0
    base_same = 0
    for i, (s, d, opt, exp_ref) in enumerate(pairs):
        noise_rng = random.Random(seed * 100003 + i)
        unit = {v: noise_rng.random() for v in nodes}
        target = coords[d]
        cost0, exp0, _ = astar_reopen(adj, s, d, lambda v: haversine(coords[v], target))
        base_exp += exp0
        base_same += abs(cost0 - opt) <= TOL and exp0 == exp_ref
        for mode in MODES:
            for eps in EPSILONS:
                cost, exp, reexp = astar_reopen(adj, s, d, noisy_h(coords, d, unit, eps, mode))
                excess = 100 * (cost - opt) / opt
                bound = 0.0 if mode == "under" else 100 * eps
                st = stats[(mode, eps)]
                st["excess"].append(excess)
                st["exp"] += exp
                st["reexp"] += reexp
                st["ok"] += excess <= bound + TOL
                writer.writerow([s, d, mode, eps, f"{cost:.3f}", f"{opt:.3f}", f"{excess:.4f}", exp, reexp])
    n = len(pairs)
    print(f"noisy h on {n} pairs (seed {seed})")
    print(f"baseline eps=0: mean expanded {base_exp / n:.0f}, same cost and count as astar(): {base_same}/{n}")
    print("mode,eps,bound_pct,within_bound,mean_excess_pct,max_excess_pct,mean_expanded,vs_exact_pct,mean_reexpanded")
    all_ok = base_same == n
    for mode in MODES:
        for eps in EPSILONS:
            st = stats[(mode, eps)]
            bound = 0.0 if mode == "under" else 100 * eps
            mean_exp = st["exp"] / n
            print(f"{mode},{eps},{bound:.0f},{st['ok']}/{n},{sum(st['excess']) / n:.3f},{max(st['excess']):.3f},"
                  f"{mean_exp:.0f},{100 * (mean_exp / (base_exp / n) - 1):+.1f},{st['reexp'] / n:.0f}")
            all_ok = all_ok and st["ok"] == n
    return all_ok


def run_time_dependent(adj, coords, pairs):
    vmax = max(SPEEDS)
    match = 0
    exp_h = exp_0 = 0
    for s, d, _, _ in pairs:
        ca, _, ea = astar_time_dependent(adj, coords, s, d)
        cd, _, ed = astar_time_dependent(adj, coords, s, d, use_h=False)
        match += abs(ca - cd) <= TOL
        exp_h += ea
        exp_0 += ed
    n = len(pairs)
    print(f"time-dependent A* on the same {n} pairs, departure t0 = 0")
    print(f"cost equals time-dependent Dijkstra: {match}/{n}")
    print(f"mean expanded: h = haversine / {vmax} m/min: {exp_h / n:.0f}; h = 0: {exp_0 / n:.0f} "
          f"({100 * (exp_h / exp_0 - 1):+.1f}%)")
    s, d = map(int, open(DATA / "sample_pair.txt").read().split())
    ct, path, et = astar_time_dependent(adj, coords, s, d)
    c0, _, e0 = astar_time_dependent(adj, coords, s, d, use_h=False)
    length = sum(adj[u][v] for u, v in zip(path, path[1:]))
    print(f"teacher pair: travel time {ct:.2f} min (Dijkstra {c0:.2f}), {length:.1f} m, "
          f"expanded {et} with h, {e0} with h = 0")
    return match == n and abs(ct - c0) <= TOL


def main():
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    coords, adj = load_graph(str(DATA / "nodes.csv"), str(DATA / "edges.csv"))
    nodes = sorted(adj)
    rows = sum(1 for _ in open(DATA / "edges.csv")) - 1
    distinct = sum(len(nb) for nb in adj.values())
    print(f"graph: {len(nodes)} nodes, {rows} edge rows, {distinct} distinct (u, v) after merging parallel edges")
    pairs = sample_pairs(adj, coords, nodes, n_pairs, seed)
    out = RESULTS / "h_variants.csv"
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["src", "dst", "mode", "eps", "cost_m", "opt_m", "excess_pct", "expanded", "reexpanded"])
        ok_noisy = run_noisy(adj, coords, nodes, pairs, seed, writer)
    ok_td = run_time_dependent(adj, coords, pairs)
    print("saved", out)
    print("ALL AS EXPECTED" if ok_noisy and ok_td else "UNEXPECTED RESULT")


if __name__ == "__main__":
    main()
