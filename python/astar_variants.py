"""
astar_variants.py — Part 1, the special cases required by the assignment:
  (a) dynamic h: speed changes over time (as in the instructor's notebook)
  (b) uncertain h: speeds have random noise
  (c) vector-valued f: optimise (length, time) simultaneously -> Pareto set
"""
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
    """
    Time (minutes) to traverse an edge of `length` metres when departing at time t.
    Speed changes every minute -> integrate piecewise (guarantees FIFO: leaving earlier never arrives later).
    The instructor's notebook only uses speeds[floor(t)] for the whole edge and raises IndexError when t >= 20.
    """
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
    """
    Cost = travel time to the destination (minutes) when departing at t0.
    h(v) = straight-line distance / max(speeds)  -> always <= true time -> admissible.
    use_h=False -> time-dependent Dijkstra (used as the reference answer).
    """
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
    """Each minute the speed varies by ±noise around the base value (simulates unpredictable traffic)."""
    return [sp * rng.uniform(1 - noise, 1 + noise) for sp in speeds]


def uncertain_experiment(adj, coords, s, d, runs=30, noise=0.2, seed=0):
    """
    Compare 2 planning strategies when the real speeds have ±noise:
      - "mean"  : plan with the base (average) speeds
      - "robust": plan with the worst-case speeds (base x (1 - noise))
    Each run: follow the plan under the real (noisy) speeds and compare with the optimal cost
    had the real speeds been known in advance. Returns {strategy: (mean gap, max gap)}.
    """
    rng = random.Random(seed)
    plans = {
        "mean": astar_time_dependent(adj, coords, s, d)[1],
        "robust": astar_time_dependent(adj, coords, s, d,
                                       speeds=[sp * (1 - noise) for sp in SPEEDS])[1],
    }
    if plans["mean"] is None:
        return {k: (float("nan"), float("nan")) for k in plans}   # no path s -> d
    gaps = {k: [] for k in plans}
    for _ in range(runs):
        sp = noisy_speeds(rng, noise)
        best, _, _ = astar_time_dependent(adj, coords, s, d, speeds=sp)
        for k, plan in plans.items():
            t = 0.0
            for u, v in zip(plan, plan[1:]):
                t += edge_time(adj[u][v], t, sp)
            gaps[k].append(t - best)
    return {k: (sum(g) / runs, max(g)) for k, g in gaps.items()}


# ---------------- (c) vector-valued f ----------------
def dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and a != b


def astar_pareto(adj, ttime, coords, s, d, vmax_mpm):
    """
    Multi-objective A* (NAMOA* idea): cost g = (length in m, time in minutes).
    Each node keeps several non-dominated labels. Result: a SET of Pareto paths, not a single path.
    h = (straight-line, straight-line / vmax) -> admissible in both components.
    """
    target = coords[d]
    def h(v):
        x = haversine(coords[v], target)
        return (x, x / vmax_mpm)
    labels = {s: [(0.0, 0.0)]}               # non-dominated labels seen so far at each node
    ctr = itertools.count()
    pq = [(h(s), next(ctr), (0.0, 0.0), s, (s,))]
    sols = []
    while pq:
        f, _, g, u, path = heapq.heappop(pq)  # the heap compares vectors lexicographically
        if any(dominates(sg, f) or sg == f for sg, _ in sols):
            continue                          # a better solution already exists -> prune
        if g not in labels.get(u, []):
            continue                          # this label has been discarded
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
