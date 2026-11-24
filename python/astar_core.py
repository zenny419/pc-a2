"""
astar_core.py — Part 1: sequential A* + reference Dijkstra.
The graph is read from data/nodes.csv (id,x,y) and data/edges.csv (u,v,length).
x = longitude, y = latitude (osmnx convention). length is in metres.
"""
import csv
import heapq
import itertools
import math

def load_graph(nodes_csv, edges_csv):
    coords, adj = {}, {}
    with open(nodes_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            n = int(r["id"])
            coords[n] = (float(r["y"]), float(r["x"]))
            adj[n] = {}
    with open(edges_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            u, v, w = int(r["u"]), int(r["v"]), float(r["length"])
            if v not in adj[u] or w < adj[u][v]:
                adj[u][v] = w
    return coords, adj


def load_travel_time(edges_csv):
    tt = {}
    with open(edges_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            u, v, t = int(r["u"]), int(r["v"]), float(r["travel_time_min"])
            if v not in tt.setdefault(u, {}) or t < tt[u][v]:
                tt[u][v] = t
    return tt


R_EARTH = 6_371_000.0

def haversine(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def dijkstra(adj, s, d):
    dist, prev = {s: 0.0}, {s: None}
    done, ctr = set(), itertools.count()
    pq = [(0.0, next(ctr), s)]
    expanded = 0
    while pq:
        g, _, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        expanded += 1
        if u == d:
            return g, _rebuild(prev, d), expanded
        for v, w in adj[u].items():
            ng = g + w
            if ng < dist.get(v, math.inf):
                dist[v], prev[v] = ng, u
                heapq.heappush(pq, (ng, next(ctr), v))
    return math.inf, None, expanded


def astar(adj, coords, s, d, h=None, weight=1.0):
    if h is None:
        target = coords[d]
        h = lambda v: haversine(coords[v], target)
    g = {s: 0.0}
    prev = {s: None}
    closed = set()
    ctr = itertools.count()
    open_pq = [(weight * h(s), next(ctr), s)]
    expanded = 0
    while open_pq:
        f, _, u = heapq.heappop(open_pq)
        if u in closed:
            continue
        if u == d:
            return g[u], _rebuild(prev, d), expanded
        closed.add(u)
        expanded += 1
        for v, w in adj[u].items():
            if v in closed:
                continue
            ng = g[u] + w
            if ng < g.get(v, math.inf):
                g[v], prev[v] = ng, u
                heapq.heappush(open_pq, (ng + weight * h(v), next(ctr), v))
    return math.inf, None, expanded


def _rebuild(prev, d):
    path, n = [], d
    while n is not None:
        path.append(n)
        n = prev[n]
    return path[::-1]


def path_length(adj, path):
    return sum(adj[u][v] for u, v in zip(path, path[1:]))
