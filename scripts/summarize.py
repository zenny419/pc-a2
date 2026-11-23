"""
summarize.py — aggregates repeated measurements: median, min, max, number of runs.
Every column other than the measured one is treated as "configuration" for grouping.

Example (5 runs of bench_list appended to the same file):
  python scripts/summarize.py results/dell-laptop/list.csv --value ops_per_sec
  python scripts/summarize.py results/dell-laptop/astar.csv --value ms --drop run
  -> writes <file>_summary.csv; use this file to plot charts with min-max bars.
"""
import argparse
import csv
import statistics
from collections import defaultdict

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--value", required=True, help="measured column, e.g. ops_per_sec or ms")
    ap.add_argument("--drop", nargs="*", default=[], help="columns ignored when grouping, e.g. run")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, newline="", encoding="utf-8")))
    keys = [c for c in rows[0] if c != a.value and c not in a.drop]
    groups = defaultdict(list)
    for r in rows:
        v = float(r[a.value])
        if v >= 0:                         # -1 = TIMEOUT (A1's bench_util.h) -> skip
            groups[tuple(r[k] for k in keys)].append(v)

    out = a.csv.rsplit(".", 1)[0] + "_summary.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(keys + ["n", "median", "min", "max"])
        for k, vs in sorted(groups.items()):
            w.writerow(list(k) + [len(vs), statistics.median(vs), min(vs), max(vs)])
    print(f"{len(groups)} configurations -> {out}")

if __name__ == "__main__":
    main()
