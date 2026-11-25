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
        if v >= 0:
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
