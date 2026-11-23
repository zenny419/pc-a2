import heapq
import itertools
import math
import random

from astar_core import _rebuild, haversine

# Speed (metres/minute) for each minute, taken from the instructor's notebook. Wraps around at the end.
SPEEDS = [350, 350, 500, 500, 600, 600, 550, 500, 400, 300,
          600, 550, 500, 400, 300, 600, 550, 500, 400, 300]


# ---------------- (a) dynamic h ----------------
def edge_time(length, t, speeds=SPEEDS):
    start, remaining = t, length
    while True:
        k = math.floor(t)
        sp = speeds[k % len(speeds)]
        dt = (k + 1) - t                    # time left until the end of this minute
        if sp * dt >= remaining:
            return t + remaining / sp - start
        remaining -= sp * dt
        t = k + 1


def astar_time_dependent(adj, coords, s, d, t0=0.0, speeds=SPEEDS, use_h=True):
    vmax = max(speeds)
    target = coords[d]
    h = (lambda v: haversine(coords[v], target) / vmax) if use_h else (lambda v: 0.0)
    arr = {s: t0}                            # arrival time at each node
    prev, closed, ctr = {s: None}, set(), itertools.count()
    pq = [(t0 + h(s), next(ctr), s)]
    expanded = 0
    while pq:
        _, _, u = heapq.heappop(pq)
        if u in closed:
            continue
        if u == d:
            return arr[u] - t0, _rebuild(prev, d), expanded
        closed.add(u); expanded += 1
        for v, length in adj[u].items():
            if v in closed:
                continue
            a = arr[u] + edge_time(length, arr[u], speeds)   # t is computed SEPARATELY for each neighbour
            if a < arr.get(v, math.inf):
                arr[v], prev[v] = a, u
                heapq.heappush(pq, (a + h(v), next(ctr), v))
    return math.inf, None, expanded


# ---------------- (b) uncertain h ----------------
def noisy_speeds(rng, noise=0.2, speeds=SPEEDS):
    return [sp * rng.uniform(1 - noise, 1 + noise) for sp in speeds]

def edge_noise_levels(adj, noise, rng):
    return {(u, v): rng.uniform(0, 2 * noise) for u in adj for v in adj[u]}


def scaled_problem(adj, factor, fmax, speeds):
    new_adj = {u: {v: L * fmax / factor[(u, v)] for v, L in nbrs.items()}
               for u, nbrs in adj.items()}
    return new_adj, [sp * fmax for sp in speeds]


def uncertain_experiment(adj, coords, s, d, runs=30, noise=0.2, seed=0):
    assert 0 <= noise < 0.5, "need 1 - 2*noise > 0"
    rng = random.Random(seed)
    level = edge_noise_levels(adj, noise, rng)
    fmax = 1 + 2 * noise                      
    worst = {e: 1 - n for e, n in level.items()}
    r_adj, r_speeds = scaled_problem(adj, worst, fmax,
                                     [sp * (1 - noise) for sp in SPEEDS])
    plans = {
        "mean": astar_time_dependent(adj, coords, s, d)[1],
        "robust": astar_time_dependent(r_adj, coords, s, d, speeds=r_speeds)[1],
    }
    if plans["mean"] is None:
        return {k: (float("nan"), float("nan")) for k in plans}   
    gaps = {k: [] for k in plans}
    for _ in range(runs):
        sp = noisy_speeds(rng, noise)
        real = {e: rng.uniform(1 - n, 1 + n) for e, n in level.items()}
        o_adj, o_speeds = scaled_problem(adj, real, fmax, sp)
        best, _, _ = astar_time_dependent(o_adj, coords, s, d, speeds=o_speeds)
        for k, plan in plans.items():
            t = 0.0
            for u, v in zip(plan, plan[1:]):
                t += edge_time(o_adj[u][v], t, o_speeds)
            assert t >= best - 1e-9, "oracle must be optimal"
            gaps[k].append(t - best)
    return {k: (sum(g) / runs, max(g)) for k, g in gaps.items()}


# ---------------- (c) vector-valued f ----------------
def dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and a != b


def astar_pareto(adj, ttime, coords, s, d, vmax_mpm):
    target = coords[d]
    def h(v):
        x = haversine(coords[v], target)
        return (x, x / vmax_mpm)
    labels = {s: [(0.0, 0.0)]}               
    ctr = itertools.count()
    pq = [(h(s), next(ctr), (0.0, 0.0), s, (s,))]
    sols = []
    while pq:
        f, _, g, u, path = heapq.heappop(pq)  
        if any(dominates(sg, f) or sg == f for sg, _ in sols):
            continue                          
        if g not in labels.get(u, []):
            continue                          
        if u == d:
            sols.append((g, list(path)))
            continue
        for v, length in adj[u].items():
            if v in path:
                continue
            ng = (g[0] + length, g[1] + ttime[u][v])
            lv = labels.setdefault(v, [])
            if any(dominates(x, ng) or x == ng for x in lv):
                continue
            lv[:] = [x for x in lv if not dominates(ng, x)] + [ng]
            hv = h(v)
            heapq.heappush(pq, ((ng[0] + hv[0], ng[1] + hv[1]), next(ctr), ng, v, path + (v,)))
    return sols
