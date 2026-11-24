import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def main():
    machine = sys.argv[1] if len(sys.argv) > 1 else "dell-pc"
    df = pd.read_csv(RESULTS / machine / "astar.csv")
    df["pair"] = df["src"].astype(str) + "->" + df["dst"].astype(str)
    per = df.groupby(["variant", "threads", "pair"]).agg(ms=("ms", "median"), expanded=("expanded", "median")).reset_index()
    seq = per[per["variant"] == "seq"].set_index("pair")
    rows = []
    for pair, s in seq.iterrows():
        row = {"pair": pair, "expanded": int(s["expanded"]), "seq_ms": s["ms"]}
        for v in ["par", "par_heap_pool"]:
            p = per[(per["variant"] == v) & (per["pair"] == pair)]
            best = p.loc[p["ms"].idxmin()]
            row[v + "_best_ms"] = best["ms"]
            row[v + "_best_threads"] = int(best["threads"])
            row[v + "_speedup"] = s["ms"] / best["ms"]
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("expanded").reset_index(drop=True)
    out.to_csv(RESULTS / machine / "query_size.csv", index=False)
    print(out.round(3).to_string(index=False))
    corr = out[["expanded", "par_speedup", "par_heap_pool_speedup"]].corr(method="spearman")
    print("\nspearman(expanded, par_speedup) = %.2f" % corr.loc["expanded", "par_speedup"])
    print("spearman(expanded, par_heap_pool_speedup) = %.2f" % corr.loc["expanded", "par_heap_pool_speedup"])
    small = out[out["expanded"] < out["expanded"].median()]
    large = out[out["expanded"] >= out["expanded"].median()]
    for name, part in [("smaller half", small), ("larger half", large)]:
        print("%s: n=%d, expanded %d-%d, par speedup median %.3f, par_heap_pool speedup median %.3f" % (
            name, len(part), part["expanded"].min(), part["expanded"].max(),
            part["par_speedup"].median(), part["par_heap_pool_speedup"].median()))


if __name__ == "__main__":
    main()
