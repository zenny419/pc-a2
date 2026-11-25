import csv
import random
import sys
from pathlib import Path

from astar_core import load_graph
from astar_variants import uncertain_experiment

ROOT = Path(__file__).resolve().parent.parent
NODES_CSV = ROOT / "data" / "nodes.csv"
EDGES_CSV = ROOT / "data" / "edges.csv"
OUT_CSV = ROOT / "results" / "uncertain_pairs.csv"


def main():
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    out_csv = OUT_CSV if runs == 20 else OUT_CSV.with_name(f"uncertain_pairs_{runs}.csv")
    coords, adj = load_graph(str(NODES_CSV), str(EDGES_CSV))
    rnd = random.Random(11)
    nodes = list(adj)
    rows = []
    while len(rows) < n_pairs:
        s, d = rnd.choice(nodes), rnd.choice(nodes)
        if s == d:
            continue
        res = uncertain_experiment(adj, coords, s, d, runs=runs, seed=len(rows))
        if res["mean"][0] != res["mean"][0]:
            continue
        row = [s, d, *res["mean"], *res["robust"]]
        rows.append(row)
        print("%d -> %d | mean %.3f / %.3f | robust %.3f / %.3f" % tuple(row))

    out_csv.parent.mkdir(exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["s", "d", "mean_avg", "mean_max", "robust_avg", "robust_max"])
        w.writerows(rows)

    avg = [sum(r[i] for r in rows) / len(rows) for i in range(2, 6)]
    print("average | mean %.3f / %.3f | robust %.3f / %.3f" % tuple(avg))
    k = sum(r[5] < r[3] for r in rows)
    print(f"robust has a smaller max gap in {k}/{len(rows)} pairs, {runs} trips per pair -> {out_csv}")


if __name__ == "__main__":
    main()
