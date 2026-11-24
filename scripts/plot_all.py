import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def summarize_list(machine_dir, nproc):
    df = pd.read_csv(machine_dir / "list.csv")
    df = df[df["ops_per_sec"] > 0]
    s = df.groupby(["variant", "threads"])["ops_per_sec"].agg(["median", "min", "max", "count"]).reset_index()
    s.to_csv(machine_dir / "list_summary.csv", index=False)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    colors = {"coarse": "tab:blue", "fine": "tab:red", "lazy": "tab:green"}
    styles = {"std": ("-", "s"), "ttas": ("--", "o"), "ttas_bo": (":", "^")}
    for v, g in s.groupby("variant"):
        g = g.sort_values("threads")
        kind, lock = v.split("+")
        ls, mk = styles.get(lock, ("-", "o"))
        ax.errorbar(g["threads"], g["median"] / 1e6,
                    yerr=[(g["median"] - g["min"]) / 1e6, (g["max"] - g["median"]) / 1e6],
                    color=colors.get(kind, None), ls=ls, marker=mk, capsize=3, label=v)
    ax.axvline(nproc, color="grey", ls="--", lw=1)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(sorted(s["threads"].unique()))
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("threads")
    ax.set_ylabel("throughput (M ops/s, log)")
    ax.set_title(f"Concurrent sorted list, 80/10/10, 500 keys ({machine_dir.name})")
    ax.text(nproc, ax.get_ylim()[0] * 1.3, f" nproc={nproc}", color="grey", va="bottom")
    ax.legend(fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5))
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(machine_dir / "list_throughput.png", dpi=150)
    plt.close(fig)

    wide = s.pivot(index="variant", columns="threads", values="median").round(-3).astype("Int64")
    print("\nlist median ops/s")
    print(wide.to_string())


def summarize_astar(machine_dir, nproc):
    df = pd.read_csv(machine_dir / "astar.csv")
    df["pair"] = df["src"].astype(str) + "-" + df["dst"].astype(str)
    per = df.groupby(["variant", "threads", "pair"]).agg(
        ms=("ms", "median"), ms_min=("ms", "min"), ms_max=("ms", "max"),
        cost=("cost_m", "first"), expanded=("expanded", "median"),
        stale=("stale_pops", "median"), pruned=("pruned", "median"),
        list_len=("list_len_avg", "median")).reset_index()

    seq = per[per["variant"] == "seq"].set_index("pair")
    par = per[per["variant"] == "par"].copy()
    par["seq_ms"] = par["pair"].map(seq["ms"])
    par["seq_cost"] = par["pair"].map(seq["cost"])
    par["seq_expanded"] = par["pair"].map(seq["expanded"])
    par["speedup"] = par["seq_ms"] / par["ms"]
    par["extra_expanded_pct"] = 100 * (par["expanded"] - par["seq_expanded"]) / par["seq_expanded"]
    both_inf = np.isinf(par["cost"]) & np.isinf(par["seq_cost"])
    par["cost_ok"] = both_inf | (np.abs(par["cost"] - par["seq_cost"]) <= 1e-6 * np.maximum(1, par["seq_cost"]))
    par.to_csv(machine_dir / "astar_per_pair.csv", index=False)

    agg = par.groupby("threads").agg(
        speedup_median=("speedup", "median"), speedup_min=("speedup", "min"), speedup_max=("speedup", "max"),
        ms_median=("ms", "median"), seq_ms_median=("seq_ms", "median"),
        extra_expanded_pct=("extra_expanded_pct", "median"), stale=("stale", "median"),
        pruned=("pruned", "median"), list_len=("list_len", "median"), cost_ok=("cost_ok", "mean")).reset_index()
    one = par[par["threads"] == 1].set_index("pair")["ms"]
    par["rel_speedup"] = par["pair"].map(one) / par["ms"]
    rel = par.groupby("threads")["rel_speedup"].median()
    agg["rel_speedup_median"] = agg["threads"].map(rel)
    agg.to_csv(machine_dir / "astar_summary.csv", index=False)
    print("\nastar per thread count (median over pairs)")
    print(agg.round(3).to_string(index=False))
    print(f"cost identical to astar_seq on all pairs/threads: {bool(par['cost_ok'].all())}")

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.errorbar(agg["threads"], agg["speedup_median"],
                yerr=[agg["speedup_median"] - agg["speedup_min"], agg["speedup_max"] - agg["speedup_median"]],
                marker="o", capsize=3, label="absolute: astar_seq / astar_par(p)")
    ax.plot(agg["threads"], agg["rel_speedup_median"], "s-", color="tab:orange",
            label="relative: astar_par(1) / astar_par(p)")
    t = np.array(sorted(agg["threads"]))
    ax.plot(t, t, "k--", lw=1, label="ideal (y = p)")
    ax.axhline(1, color="red", lw=1, label="break-even (= astar_seq)")
    ax.axvline(nproc, color="grey", ls=":", lw=1)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(t)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("threads p")
    ax.set_ylabel("speedup (log)")
    ax.set_title(f"Parallel A* speedup ({machine_dir.name})")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(machine_dir / "astar_speedup.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(agg["threads"], agg["ms_median"], marker="o", label="astar_par")
    ax.axhline(agg["seq_ms_median"].iloc[0], color="red", lw=1, label="astar_seq")
    ax.axvline(nproc, color="grey", ls=":", lw=1)
    ax.set_xscale("log", base=2)
    ax.set_xticks(t)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("threads")
    ax.set_ylabel("time per query (ms, median over pairs)")
    ax.set_title(f"Parallel A* time per query ({machine_dir.name})")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(machine_dir / "astar_time.png", dpi=150)
    plt.close(fig)


def summarize_variants(machine_dir, nproc):
    df = pd.read_csv(machine_dir / "astar.csv")
    if df["variant"].nunique() <= 2:
        return
    df["pair"] = df["src"].astype(str) + "-" + df["dst"].astype(str)
    per = df.groupby(["variant", "threads", "pair"])["ms"].median().reset_index()
    agg = per.groupby(["variant", "threads"])["ms"].agg(["median", "min", "max"]).reset_index()
    agg.to_csv(machine_dir / "astar_variants_summary.csv", index=False)
    seq_ms = agg.loc[agg["variant"] == "seq", "median"].iloc[0]
    print("\nastar variants: median ms per query (median over pairs)")
    print(agg[agg["variant"] != "seq"].pivot(index="variant", columns="threads", values="median").round(3).to_string())
    print(f"seq: {seq_ms:.3f} ms")

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    style = {"par": ("tab:red", "--", "o", "list, create"), "par_pool": ("tab:red", "-", "o", "list, pool"),
             "par_heap": ("tab:blue", "--", "s", "heap+mutex, create"),
             "par_heap_pool": ("tab:blue", "-", "s", "heap+mutex, pool")}
    for v, (c, ls, mk, lab) in style.items():
        g = agg[agg["variant"] == v].sort_values("threads")
        if g.empty:
            continue
        ax.plot(g["threads"], g["median"], color=c, ls=ls, marker=mk, label=lab)
    ax.axhline(seq_ms, color="black", lw=1.2, label="astar_seq")
    ax.axvline(nproc, color="grey", ls=":", lw=1)
    t = sorted(agg.loc[agg["variant"] != "seq", "threads"].unique())
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(t)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("threads")
    ax.set_ylabel("time per query (ms, log)")
    ax.set_title(f"Parallel A* variants ({machine_dir.name})")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(machine_dir / "astar_variants.png", dpi=150)
    plt.close(fig)


def summarize_batch(machine_dir, nproc):
    f = machine_dir / "batch.csv"
    if not f.exists():
        return
    df = pd.read_csv(f)
    base = df.loc[df["variant"] == "batch_seq", "qps"].median()
    par = df[df["variant"] == "batch"].copy()
    par["speedup"] = par["qps"] / base
    s = par.groupby("threads").agg(qps_median=("qps", "median"), speedup_median=("speedup", "median"),
                                   speedup_min=("speedup", "min"), speedup_max=("speedup", "max"),
                                   cost_match_min=("cost_match", "min"), n_queries=("n_queries", "first")).reset_index()
    s.to_csv(machine_dir / "batch_summary.csv", index=False)
    print(f"\nastar_batch: batch_seq median {base:.1f} qps")
    print(s.round(3).to_string(index=False))
    print(f"all queries match the reference: {bool((s['cost_match_min'] == s['n_queries']).all())}")

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.errorbar(s["threads"], s["speedup_median"],
                yerr=[s["speedup_median"] - s["speedup_min"], s["speedup_max"] - s["speedup_median"]],
                marker="o", capsize=3, label="qps(p) / qps(batch_seq)")
    t = np.array(sorted(s["threads"]))
    ax.plot(t, t, "k--", lw=1, label="ideal (y = p)")
    ax.axhline(1, color="red", lw=1, label="break-even")
    ax.axvline(nproc, color="grey", ls=":", lw=1)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log", base=2)
    ax.set_xticks(t)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("threads p")
    ax.set_ylabel("speedup (log2)")
    ax.set_title(f"Parallelism across queries, {int(s['n_queries'].iloc[0])} queries ({machine_dir.name})")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(machine_dir / "batch_speedup.png", dpi=150)
    plt.close(fig)


def summarize_spawn(machine_dir):
    f = machine_dir / "spawn.csv"
    if not f.exists():
        return
    df = pd.read_csv(f)
    s = df.groupby(["variant", "threads"])["us_median"].median().reset_index()
    s.to_csv(machine_dir / "spawn_summary.csv", index=False)
    print("\nthread start cost (us, median of runs)")
    print(s.pivot(index="variant", columns="threads", values="us_median").round(1).to_string())


def plot_weighted():
    f = RESULTS / "weighted_astar.csv"
    if not f.exists():
        return
    df = pd.read_csv(f)
    s = df.groupby("weight").agg(excess=("excess_pct", "mean"), expanded=("expanded", "mean")).reset_index()
    fig, ax1 = plt.subplots(figsize=(6, 4))
    ax1.plot(s["weight"], s["expanded"], "o-", color="tab:blue", label="nodes expanded")
    ax1.set_xlabel("weight w (f = g + w h)")
    ax1.set_ylabel("nodes expanded (mean)", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(s["weight"], s["excess"], "s-", color="tab:red", label="path excess")
    ax2.plot(s["weight"], 100 * (s["weight"] - 1), ":", color="tab:red", lw=1, label="bound (w-1)")
    ax2.set_ylim(0, max(15, s["excess"].max() * 1.3))
    ax2.set_ylabel("path longer than optimal (%)", color="tab:red")
    ax1.set_title("Weighted A*: quality vs work (50 pairs)")
    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.88), fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS / "weighted_astar.png", dpi=150)
    plt.close(fig)


def plot_pareto():
    f = RESULTS / "pareto_teacher.csv"
    if not f.exists():
        return
    df = pd.read_csv(f).sort_values("length_m")
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(df["length_m"] / 1000, df["time_min"], "o-", ms=4)
    ax.set_xlabel("length (km)")
    ax.set_ylabel("travel time (min)")
    ax.set_title(f"Pareto set, teacher pair ({len(df)} non-dominated paths)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS / "pareto_teacher.png", dpi=150)
    plt.close(fig)


def main():
    machine = sys.argv[1] if len(sys.argv) > 1 else "dell-pc"
    machine_dir = RESULTS / machine
    nproc = 0
    info = machine_dir / "sysinfo.txt"
    if info.exists():
        for line in info.read_text().splitlines():
            if line.startswith("nproc:"):
                nproc = int(line.split(":")[1])
    summarize_list(machine_dir, nproc)
    summarize_astar(machine_dir, nproc)
    summarize_variants(machine_dir, nproc)
    summarize_batch(machine_dir, nproc)
    summarize_spawn(machine_dir)
    plot_weighted()
    plot_pareto()
    print("\nsaved:", ", ".join(p.name for p in sorted(machine_dir.glob("*.png"))),
          "+ results/weighted_astar.png, results/pareto_teacher.png")


if __name__ == "__main__":
    main()
