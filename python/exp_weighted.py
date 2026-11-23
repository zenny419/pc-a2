import csv
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from astar_core import load_graph, astar

WEIGHTS = [1.0, 1.2, 1.5, 2.0, 3.0]


def main():
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    coords, adj = load_graph(str(ROOT / "data" / "nodes.csv"), str(ROOT / "data" / "edges.csv"))
    nodes = sorted(adj)
    rng = random.Random(seed)
    out = ROOT / "results" / "weighted_astar.csv"
    sums = {wt: [0.0, 0.0, 0] for wt in WEIGHTS}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "weight", "cost_m", "opt_m", "excess_pct", "expanded", "ms"])
        done = 0
        while done < n_pairs:
            s, d = rng.sample(nodes, 2)
            opt, _, _ = astar(adj, coords, s, d)
            if opt == float("inf") or opt == 0:
                continue
            for wt in WEIGHTS:
                t0 = time.perf_counter()
                cost, _, exp = astar(adj, coords, s, d, weight=wt)
                ms = (time.perf_counter() - t0) * 1000
                excess = 100 * (cost - opt) / opt
                w.writerow([s, d, wt, f"{cost:.3f}", f"{opt:.3f}", f"{excess:.4f}", exp, f"{ms:.3f}"])
                sums[wt][0] += excess
                sums[wt][1] += exp
                sums[wt][2] += 1
            done += 1
    print("weight,mean_excess_pct,mean_expanded")
    for wt in WEIGHTS:
        e, x, n = sums[wt]
        print(f"{wt},{e / n:.3f},{x / n:.0f}")
    print("saved", out)


if __name__ == "__main__":
    main()
