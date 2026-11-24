#!/usr/bin/env python3
import csv, glob, os, statistics
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter, ScalarFormatter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(PLOTS, exist_ok=True)

LIBRARY = {"std", "pthread", "omp", "lock_std", "lock_pthread", "lock_omp"}

PALETTE = list(plt.get_cmap("tab10").colors) + ["#000000", "#b8860b", "#00008b"]


def load(pattern):
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*", pattern))):
        with open(f, newline="") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def aggregate(rows, name_col, x_col, y_col, group_cols=()):
    vals = defaultdict(list)
    hw = {}
    for r in rows:
        key = (r["machine"],) + tuple(r[g] for g in group_cols)
        hw[r["machine"]] = int(r["hw_threads"])
        y = float(r[y_col])
        vals[(key, r[name_col], int(r[x_col]))].append(y)
    out = defaultdict(lambda: defaultdict(dict))
    for (key, name, x), ys in vals.items():
        good = [y for y in ys if float(y) > 0]
        out[key][name][x] = statistics.median(good) if good else None
    return out, hw


def plot(agg, hw, title, ylabel, fname, group_filter=None, logy=True):
    keys = sorted(k for k in agg if group_filter is None or k[1:] == group_filter)
    if not keys:
        return
    fig, axes = plt.subplots(1, len(keys), figsize=(5.2 * len(keys) + 2, 4.6),
                             squeeze=False, sharey=True)
    names = sorted({n for k in keys for n in agg[k]})
    color = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(names)}
    for ax, key in zip(axes[0], keys):
        machine = key[0]
        xs_all = sorted({x for n in agg[key] for x in agg[key][n]})
        for name in sorted(agg[key]):
            pts = sorted((x, y) for x, y in agg[key][name].items() if y is not None)
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.plot(xs, ys, marker="o", ms=4, color=color[name],
                    ls="--" if name in LIBRARY else "-", label=name)
        ax.axvline(hw[machine], color="grey", ls=":", lw=1)
        ax.text(hw[machine], ax.get_ylim()[1], f" {hw[machine]} hardware threads",
                fontsize=7, color="grey", va="top")
        ax.set_title(machine)
        ax.set_xlabel("Number of threads")
        if ax is axes[0][0]:
            ax.set_ylabel(ylabel)
        ax.set_xscale("log", base=2)
        ax.set_xticks(xs_all)
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.xaxis.set_minor_formatter(NullFormatter())
        if logy:
            ax.set_yscale("log")
        ax.grid(alpha=0.3, which="both")
    handles, labels = {}, []
    for ax in axes[0]:
        for h, l in zip(*ax.get_legend_handles_labels()):
            handles.setdefault(l, h)
    fig.legend([handles[l] for l in sorted(handles)], sorted(handles), fontsize=8,
               loc="center left", bbox_to_anchor=(1.0, 0.5), title="dashed = library implementation",
               title_fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    path = os.path.join(PLOTS, fname)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  plotted", os.path.relpath(path, ROOT))


def summary(agg, fname, name_label, group_label=None):
    path = os.path.join(ROOT, fname)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["machine"] + ([group_label] if group_label else []) +
                   [name_label, "threads", "median"])
        for key in sorted(agg):
            for name in sorted(agg[key]):
                for x in sorted(agg[key][name]):
                    y = agg[key][name][x]
                    w.writerow(list(key) + [name, x, "TIMEOUT" if y is None else f"{y:.6g}"])
    print("  wrote", os.path.relpath(path, ROOT))


rows = load("part1_locks.csv")
if rows:
    print("Part 1 – Mutex locks")
    agg, hw = aggregate(rows, "lock", "threads", "seconds", ("outside_work",))
    for ow in sorted({k[1] for k in agg}, key=int):
        plot(agg, hw, f"Part 1 – Total program runtime (OUTSIDE_WORK = {ow})",
             "Time (seconds, log)", f"part1_time_ow{ow}.png", group_filter=(ow,))
    summary(agg, "summary_part1_locks.csv", "lock", "outside_work")

rows = load("part2_barriers.csv")
if rows:
    print("Part 2 – Barrier")
    agg, hw = aggregate(rows, "barrier", "threads", "episodes_per_sec")
    plot(agg, hw, "Part 2 – Barrier episodes completed per second (higher = better)",
         "Episodes / second (log)", "part2_episodes_per_sec.png")
    summary(agg, "summary_part2_barriers.csv", "barrier")

rows = load("part3_counters.csv")
if rows:
    print("Part 3 – Counters")
    agg, hw = aggregate(rows, "counter", "threads", "seconds")
    agg_ns, _ = aggregate(
        [dict(r, ns_per_op=str(float(r["seconds"]) / int(r["total_ops"]) * 1e9
                               if float(r["seconds"]) > 0 else -1)) for r in rows],
        "counter", "threads", "ns_per_op")
    plot(agg_ns, hw, "Part 3 – Average time per inc() (lower = better)",
         "ns / operation (log)", "part3_ns_per_op.png")
    summary(agg_ns, "summary_part3_counters_ns_per_op.csv", "counter")
    summary(agg, "summary_part3_counters_seconds.csv", "counter")

print("Done. Plots in results/plots/")
