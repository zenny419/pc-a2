import csv
import heapq
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from astar_core import load_graph, astar, dijkstra, path_length

INF = math.inf
TOL = 1e-6


def witness_dists(out, src, skip, max_cost, settle_limit):
    dist = {src: 0.0}
    done = set()
    pq = [(0.0, src)]
    while pq and len(done) < settle_limit:
        g, u = heapq.heappop(pq)
        if u in done:
            continue
        if g > max_cost:
            break
        done.add(u)
        for v, w in out[u].items():
            if v == skip:
                continue
            ng = g + w
            if ng < dist.get(v, INF):
                dist[v] = ng
                heapq.heappush(pq, (ng, v))
    return dist


def needed_shortcuts(out, inn, v, settle_limit):
    result = []
    if not inn[v] or not out[v]:
        return result
    max_out = max(out[v].values())
    for u, w_uv in inn[v].items():
        dist = witness_dists(out, u, v, w_uv + max_out, settle_limit)
        for x, w_vx in out[v].items():
            if x == u:
                continue
            c = w_uv + w_vx
            if dist.get(x, INF) > c:
                result.append((u, x, c))
    return result


def priority(out, inn, v, deleted, settle_limit):
    sc = needed_shortcuts(out, inn, v, settle_limit)
    return len(sc) - len(inn[v]) - len(out[v]) + deleted[v]


def build_ch(adj, settle_limit):
    t0 = time.perf_counter()
    out = {u: dict(nbrs) for u, nbrs in adj.items()}
    inn = {u: {} for u in adj}
    for u, nbrs in adj.items():
        for v, w in nbrs.items():
            inn[v][u] = w
    mid = {}
    deleted = {u: 0 for u in adj}
    rank = {}
    up_fwd = {u: [] for u in adj}
    up_bwd = {u: [] for u in adj}
    pq = [(priority(out, inn, v, deleted, settle_limit), v) for v in adj]
    heapq.heapify(pq)
    n_shortcuts = 0
    while pq:
        _, v = heapq.heappop(pq)
        if v in rank:
            continue
        p = priority(out, inn, v, deleted, settle_limit)
        if pq and p > pq[0][0]:
            heapq.heappush(pq, (p, v))
            continue
        for u, x, c in needed_shortcuts(out, inn, v, settle_limit):
            if c < out[u].get(x, INF):
                if x not in out[u]:
                    n_shortcuts += 1
                out[u][x] = c
                inn[x][u] = c
                mid[(u, x)] = v
        rank[v] = len(rank)
        for x, w in out[v].items():
            up_fwd[v].append((x, w))
            del inn[x][v]
            deleted[x] += 1
        for u, w in inn[v].items():
            up_bwd[v].append((u, w))
            del out[u][v]
            deleted[u] += 1
        out[v] = {}
        inn[v] = {}
    return up_fwd, up_bwd, mid, rank, n_shortcuts, time.perf_counter() - t0


def ch_query(up_fwd, up_bwd, s, d, first_meet=False):
    dist = ({s: 0.0}, {d: 0.0})
    parent = ({s: None}, {d: None})
    done = (set(), set())
    pqs = ([(0.0, s)], [(0.0, d)])
    graphs = (up_fwd, up_bwd)
    best, meet = INF, None
    settled = 0
    side = 0
    while pqs[0] or pqs[1]:
        if not pqs[side] or (pqs[1 - side] and pqs[1 - side][0][0] < pqs[side][0][0]):
            side = 1 - side
        if pqs[side][0][0] >= best:
            if not pqs[1 - side] or pqs[1 - side][0][0] >= best:
                break
            side = 1 - side
            continue
        g, u = heapq.heappop(pqs[side])
        if u in done[side]:
            continue
        done[side].add(u)
        settled += 1
        if u in dist[1 - side] and g + dist[1 - side][u] < best:
            best = g + dist[1 - side][u]
            meet = u
        if first_meet and u in done[1 - side]:
            break
        for v, w in graphs[side][u]:
            ng = g + w
            if ng < dist[side].get(v, INF):
                dist[side][v] = ng
                parent[side][v] = u
                heapq.heappush(pqs[side], (ng, v))
    if meet is None:
        return INF, None, settled
    left, n = [], meet
    while n is not None:
        left.append(n)
        n = parent[0][n]
    right, n = [], parent[1][meet]
    while n is not None:
        right.append(n)
        n = parent[1][n]
    return best, left[::-1] + right, settled


def unpack(path, mid):
    result = [path[0]]
    stack = []
    for a, b in zip(path, path[1:]):
        stack.append((a, b))
        while stack:
            u, x = stack.pop()
            m = mid.get((u, x))
            if m is None:
                result.append(x)
            else:
                stack.append((m, x))
                stack.append((u, m))
    return result


def timed(fn):
    t0 = time.perf_counter()
    res = fn()
    return res, (time.perf_counter() - t0) * 1000


def main():
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    settle_limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    coords, adj = load_graph(str(ROOT / "data" / "nodes.csv"), str(ROOT / "data" / "edges.csv"))
    nodes = sorted(adj)
    n_edges = sum(len(nbrs) for nbrs in adj.values())
    up_fwd, up_bwd, mid, rank, n_shortcuts, prep_s = build_ch(adj, settle_limit)
    n_up = sum(len(e) for e in up_fwd.values()) + sum(len(e) for e in up_bwd.values())
    rng = random.Random(seed)
    out = ROOT / "results" / "ch.csv"
    tot = {"dij_exp": 0, "hav_exp": 0, "ch_settled": 0, "dij_ms": 0.0, "hav_ms": 0.0, "ch_ms": 0.0,
           "ok": 0, "path_ok": 0, "fm_wrong": 0}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "dijkstra_m", "astar_m", "ch_m", "ch_first_meet_m", "unpacked_path_ok",
                    "dijkstra_exp", "astar_exp", "ch_settled", "dijkstra_ms", "astar_ms", "ch_ms"])
        done = 0
        while done < n_pairs:
            s, d = rng.sample(nodes, 2)
            (opt, _, dij_exp), dij_ms = timed(lambda: dijkstra(adj, s, d))
            if opt == INF or opt == 0:
                continue
            (hav_cost, _, hav_exp), hav_ms = timed(lambda: astar(adj, coords, s, d))
            (ch_cost, up_path, ch_settled), ch_ms = timed(lambda: ch_query(up_fwd, up_bwd, s, d))
            fm_cost, _, _ = ch_query(up_fwd, up_bwd, s, d, first_meet=True)
            full = unpack(up_path, mid) if up_path else None
            path_ok = bool(full) and full[0] == s and full[-1] == d and \
                all(b in adj[a] for a, b in zip(full, full[1:])) and \
                abs(path_length(adj, full) - opt) <= TOL
            tot["dij_exp"] += dij_exp
            tot["hav_exp"] += hav_exp
            tot["ch_settled"] += ch_settled
            tot["dij_ms"] += dij_ms
            tot["hav_ms"] += hav_ms
            tot["ch_ms"] += ch_ms
            tot["ok"] += abs(ch_cost - opt) <= TOL
            tot["path_ok"] += path_ok
            tot["fm_wrong"] += fm_cost > opt + TOL
            w.writerow([s, d, f"{opt:.6f}", f"{hav_cost:.6f}", f"{ch_cost:.6f}", f"{fm_cost:.6f}", int(path_ok),
                        dij_exp, hav_exp, ch_settled, f"{dij_ms:.3f}", f"{hav_ms:.3f}", f"{ch_ms:.3f}"])
            done += 1
    n = n_pairs
    print("settle_limit,prep_s,nodes,edges,shortcuts,upward_edges,ch_correct,unpacked_path_ok,first_meet_wrong,"
          "exp_dijkstra,exp_astar,settled_ch,reduction_vs_astar_pct,ms_dijkstra,ms_astar,ms_ch")
    red = 100 * (1 - tot["ch_settled"] / tot["hav_exp"])
    print(f"{settle_limit},{prep_s:.2f},{len(nodes)},{n_edges},{n_shortcuts},{n_up},"
          f"{tot['ok']}/{n},{tot['path_ok']}/{n},{tot['fm_wrong']}/{n},"
          f"{tot['dij_exp'] / n:.0f},{tot['hav_exp'] / n:.0f},{tot['ch_settled'] / n:.0f},{red:.1f},"
          f"{tot['dij_ms'] / n:.2f},{tot['hav_ms'] / n:.2f},{tot['ch_ms'] / n:.3f}")
    print("saved", out)


if __name__ == "__main__":
    main()
