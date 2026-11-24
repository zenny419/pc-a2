import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def main():
    machine = sys.argv[1] if len(sys.argv) > 1 else "dell-pc"
    out = RESULTS / machine

    pq = pd.read_csv(out / "list_pq.csv")
    pq = pq[pq["ops_per_sec"] > 0]
    wide = pq.groupby(["variant", "threads"])["ops_per_sec"].median().unstack("threads").round(-3).astype("Int64")
    print("list, priority-queue mix (remove_min + add), median ops/s")
    print(wide.to_string())

    df = pd.read_csv(out / "astar_extra.csv")
    df["pair"] = df["src"].astype(str) + "->" + df["dst"].astype(str)
    per = df.groupby(["variant", "threads", "pair"])["ms"].median().reset_index()
    agg = per.groupby(["variant", "threads"])["ms"].median().reset_index()
    seq_ms = agg.loc[agg["variant"] == "seq", "ms"].iloc[0]
    print("\nastar, median ms per query (median over pairs); seq: %.3f ms" % seq_ms)
    print(agg[agg["variant"] != "seq"].pivot(index="variant", columns="threads", values="ms").round(3).to_string())
    costs = df.groupby("pair")["cost_m"].agg(lambda c: c.round(3).nunique())
    print("\ncost identical across all variants, threads and runs: %s (%d pairs)" % ((costs == 1).all(), len(costs)))
    print("rows: list_pq %d, astar_extra %d" % (len(pq), len(df)))


if __name__ == "__main__":
    main()
