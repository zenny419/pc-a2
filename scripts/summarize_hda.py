import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def per_query(df):
    df = df.copy()
    df["pair"] = df["src"].astype(str) + "->" + df["dst"].astype(str)
    return df


def main():
    machine = sys.argv[1] if len(sys.argv) > 1 else "dell-pc"
    out = RESULTS / machine
    ref = per_query(pd.read_csv(out / "astar_hda_ref.csv"))
    hda = per_query(pd.read_csv(out / "astar_hda.csv"))

    both = pd.concat([ref[["variant", "threads", "run", "pair", "cost_m", "expanded", "ms"]],
                      hda[["variant", "threads", "run", "pair", "cost_m", "expanded", "ms"]]])
    per = both.groupby(["variant", "threads", "pair"])[["ms", "expanded"]].median().reset_index()
    agg = per.groupby(["variant", "threads"])[["ms", "expanded"]].median().reset_index()
    seq = agg[agg["variant"] == "seq"].iloc[0]
    seq_ms, seq_exp = seq["ms"], seq["expanded"]
    rest = agg[agg["variant"] != "seq"].copy()
    rest["speedup"] = seq_ms / rest["ms"]
    rest["extra_expanded_pct"] = 100.0 * (rest["expanded"] / seq_exp - 1.0)

    print("astar, median ms per query (median over pairs); seq: %.3f ms, %.0f expanded nodes" % (seq_ms, seq_exp))
    print(rest.pivot(index="variant", columns="threads", values="ms").round(3).to_string())
    print("\nspeedup vs seq")
    print(rest.pivot(index="variant", columns="threads", values="speedup").round(3).to_string())
    print("\nextra expanded nodes vs seq (%)")
    print(rest.pivot(index="variant", columns="threads", values="extra_expanded_pct").round(1).to_string())

    h = hda.groupby(["variant", "threads"])[["remote_frac", "imbalance", "stale_pops"]].median()
    print("\nhda: remote message fraction, load imbalance (max/mean expanded per thread), stale pops (median)")
    print(h.round(3).to_string())

    costs = both.groupby("pair")["cost_m"].agg(lambda c: c.round(3).nunique())
    print("\ncost identical across all variants, threads and runs: %s (%d pairs)" % ((costs == 1).all(), len(costs)))
    print("rows: ref %d, hda %d" % (len(ref), len(hda)))


if __name__ == "__main__":
    main()
