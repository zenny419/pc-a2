import csv
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from astar_core import load_graph, load_travel_time, haversine
from astar_variants import astar_pareto

VMAX_MPM = 100 * 1000 / 60


def run_pair(adj, tt, coords, tag, s, d, writer, f):
    t0 = time.perf_counter()
    sols = astar_pareto(adj, tt, coords, s, d, vmax_mpm=VMAX_MPM)
    sec = time.perf_counter() - t0
    for g, p in sorted(sols):
        writer.writerow([tag, s, d, f"{haversine(coords[s], coords[d]):.0f}", f"{g[0]:.1f}", f"{g[1]:.3f}", len(p), f"{sec:.2f}"])
    f.flush()
    print(f"{tag} {s}->{d}: {len(sols)} Pareto paths, {sec:.1f} s", flush=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "teacher"
    coords, adj = load_graph(str(ROOT / "data" / "nodes.csv"), str(ROOT / "data" / "edges.csv"))
    tt = load_travel_time(str(ROOT / "data" / "edges.csv"))
    out = ROOT / "results" / f"pareto_{mode}.csv"
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["pair", "src", "dst", "crow_m", "length_m", "time_min", "n_nodes", "sec"])
        if mode == "teacher":
            s, d = map(int, open(ROOT / "data" / "sample_pair.txt").read().split())
            run_pair(adj, tt, coords, "teacher", s, d, writer, f)
        else:
            n_pairs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            lo = float(sys.argv[3]) if len(sys.argv) > 3 else 2000
            hi = float(sys.argv[4]) if len(sys.argv) > 4 else 5000
            rng = random.Random(7)
            nodes = sorted(adj)
            k = 0
            while k < n_pairs:
                s, d = rng.sample(nodes, 2)
                if lo <= haversine(coords[s], coords[d]) <= hi:
                    k += 1
                    run_pair(adj, tt, coords, f"r{k}", s, d, writer, f)
    print("saved", out)


if __name__ == "__main__":
    main()
