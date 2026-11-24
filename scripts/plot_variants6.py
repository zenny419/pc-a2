import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

STYLE = {
    "par": ("tab:red", "--", "o", "sorted list, create"),
    "par_pool": ("tab:red", "-", "o", "sorted list, pool"),
    "par_heap": ("tab:blue", "--", "s", "heap+mutex, create"),
    "par_heap_pool": ("tab:blue", "-", "s", "heap+mutex, pool"),
    "par_lazy": ("tab:green", "--", "^", "lazy list, create"),
    "par_lazy_pool": ("tab:green", "-", "^", "lazy list, pool"),
}


def main():
    machine = sys.argv[1] if len(sys.argv) > 1 else "dell-pc"
    out = RESULTS / machine
    nproc = int(sys.argv[2]) if len(sys.argv) > 2 else None
    df = pd.read_csv(out / "astar_extra.csv")
    df["pair"] = df["src"].astype(str) + "->" + df["dst"].astype(str)
    per = df.groupby(["variant", "threads", "pair"])["ms"].median().reset_index()
    agg = per.groupby(["variant", "threads"])["ms"].median().reset_index()
    seq_ms = agg.loc[agg["variant"] == "seq", "ms"].iloc[0]

    fig, ax = plt.subplots(figsize=(8, 4.2))
    for v, (c, ls, mk, lab) in STYLE.items():
        g = agg[agg["variant"] == v].sort_values("threads")
        if g.empty:
            continue
        ax.plot(g["threads"], g["ms"], color=c, ls=ls, marker=mk, label=lab)
    ax.axhline(seq_ms, color="black", lw=1.2, label=f"astar_seq ({seq_ms:.3f} ms)")
    if nproc:
        ax.axvline(nproc, color="grey", ls=":", lw=1)
    t = sorted(agg.loc[agg["variant"] != "seq", "threads"].unique())
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(t)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("threads")
    ax.set_yticks([1, 2, 3, 4, 6, 8, 10, 15, 20])
    ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.get_yaxis().set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_ylabel("time per query (ms, log)")
    ax.set_title(f"Parallel A*, six variants, second run ({machine})")
    ax.legend(fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5))
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(out / "astar_variants6.png", dpi=150)
    plt.close(fig)
    print(agg[agg["variant"] != "seq"].pivot(index="variant", columns="threads", values="ms").round(3).to_string())
    print("saved", out / "astar_variants6.png")


if __name__ == "__main__":
    main()
