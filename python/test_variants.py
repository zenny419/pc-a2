import random
import sys
from pathlib import Path

from astar_core import load_graph
from astar_variants import astar_pareto, astar_time_dependent, dominates, uncertain_experiment
from test_astar import make_grid

EPS = 1e-6

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PAIR_TXT = ROOT / "data" / "sample_pair.txt"

def brute_force_pareto(adj, ttime, s, d, limit=200000):
    out, stack, seen = [], [(s, (s,), 0.0, 0.0)], 0
    while stack:
        u, path, L, T = stack.pop()
        seen += 1
        if seen > limit:
            return None
        if u == d:
            out.append((L, T)); continue
        for v, w in adj[u].items():
            if v not in path:
                stack.append((v, path + (v,), L + w, T + ttime[u][v]))
    return sorted({c for c in out if not any(dominates(o, c) for o in out)})

def main():
    rnd = random.Random(7)
    if len(sys.argv) >= 3:
        coords, adj = load_graph(sys.argv[1], sys.argv[2])
    else:
        coords, adj = make_grid(40)
    nodes = list(adj)

    ok = 0; N = 100
    for _ in range(N):
        s, d = rnd.choice(nodes), rnd.choice(nodes)
        t0 = rnd.uniform(0, 19)
        ca, _, ea = astar_time_dependent(adj, coords, s, d, t0)
        cd, _, ed = astar_time_dependent(adj, coords, s, d, t0, use_h=False)
        ok += abs(ca - cd) < EPS or (ca == cd)
    print(f"(a) dynamic h: {ok}/{N} pairs match time-dependent Dijkstra")

    s, d = nodes[0], nodes[-1]
    if len(sys.argv) >= 3:
        s, d = map(int, open(SAMPLE_PAIR_TXT).read().split())
    res = uncertain_experiment(adj, coords, s, d, runs=20)
    for k, (mean_gap, max_gap) in res.items():
        print(f"(b) uncertain h, plan={k:6s}: gap vs optimal mean={mean_gap:.3f} min, max={max_gap:.3f} min (must be >= 0)")

    c2, a2 = make_grid(5, seed=3)
    tt = {u: {v: w / rnd.choice([300, 500, 700]) for v, w in nb.items()} for u, nb in a2.items()}
    for u in a2:
        for v in a2[u]:
            tt[v][u] = tt[u][v]
    good = 0; M = 10; n2 = list(a2)
    for _ in range(M):
        s, d = rnd.choice(n2), rnd.choice(n2)
        got = sorted({tuple(round(x, 6) for x in g) for g, _ in astar_pareto(a2, tt, c2, s, d, 700)})
        ref = brute_force_pareto(a2, tt, s, d)
        ref = sorted({tuple(round(x, 6) for x in g) for g in ref}) if ref is not None else None
        good += got == ref
        if got != ref:
            print("  mismatch", s, d, got, ref)
    print(f"(c) vector f: {good}/{M} Pareto sets equal brute force")

if __name__ == "__main__":
    main()
