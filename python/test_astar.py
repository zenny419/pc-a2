"""
test_astar.py — A* correctness test: compares costs with Dijkstra on N random node pairs.
Run:  python python/test_astar.py data/nodes.csv data/edges.csv 100
No arguments -> builds a small grid graph to test on.
"""
import random
import sys
import time

from astar_core import astar, dijkstra, load_graph, path_length

EPS = 1e-6

def make_grid(n=40, seed=1):
    from astar_core import haversine
    rnd = random.Random(seed)
    coords = {i * n + j: (10.75 + i * 0.001, 106.65 + j * 0.001) for i in range(n) for j in range(n)}
    adj = {k: {} for k in coords}
    for i in range(n):
        for j in range(n):
            u = i * n + j
            for di, dj in ((0, 1), (1, 0)):
                if i + di < n and j + dj < n and rnd.random() > 0.1:
                    v = (i + di) * n + (j + dj)
                    w = haversine(coords[u], coords[v]) * rnd.uniform(1.0, 1.5)
                    adj[u][v] = adj[v][u] = w
    return coords, adj

def main():
    if len(sys.argv) >= 3:
        coords, adj = load_graph(sys.argv[1], sys.argv[2])
        pairs = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    else:
        coords, adj = make_grid()
        pairs = 200
    nodes = list(adj)
    rnd = random.Random(42)
    ok = fail = 0
    exp_a = exp_d = 0
    t_a = t_d = 0.0
    for _ in range(pairs):
        s, d = rnd.choice(nodes), rnd.choice(nodes)
        t0 = time.perf_counter(); cd, pd, ed = dijkstra(adj, s, d); t1 = time.perf_counter()
        ca, pa, ea = astar(adj, coords, s, d);                     t2 = time.perf_counter()
        t_d += t1 - t0; t_a += t2 - t1; exp_d += ed; exp_a += ea
        same = (pd is None and pa is None) or (
            pa is not None and abs(ca - cd) < EPS and abs(path_length(adj, pa) - ca) < EPS
            and pa[0] == s and pa[-1] == d)
        ok += same; fail += not same
        if not same:
            print(f"FAIL {s}->{d}: dijkstra={cd:.3f} astar={ca:.3f}")
    print(f"Pairs: {pairs}  PASS: {ok}  FAIL: {fail}")
    print(f"Avg expanded  Dijkstra: {exp_d/pairs:.0f}   A*: {exp_a/pairs:.0f}")
    print(f"Avg time (ms) Dijkstra: {1000*t_d/pairs:.2f}   A*: {1000*t_a/pairs:.2f}")

    bad = 0
    for _ in range(pairs):
        s, d = rnd.choice(nodes), rnd.choice(nodes)
        cd, _, _ = dijkstra(adj, s, d)
        cb, _, _ = astar(adj, coords, s, d, weight=3.0)
        bad += cb > cd + EPS
    print(f"Negative control (weight=3): {bad} pairs with non-optimal cost "
          f"-> {'test CAN detect bugs' if bad else 'WARNING: test did not detect anything'}")
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
