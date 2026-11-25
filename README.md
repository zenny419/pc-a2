# Parallel Computing – Assignment 2

Sequential and parallel A* on the Ho Chi Minh City road network, built on a concurrent sorted list.

## What is where

| Folder | Contents |
|---|---|
| `python/` | Part 1: A*, Dijkstra, dynamic/uncertain h, Pareto (vector f), and the Part 4 experiments (weighted A*, ALT, contraction hierarchies, noisy h) |
| `include/` | Shared C++ headers: locks from Assignment 1, sorted lists (coarse, fine, lazy), graph loader |
| `src/` | Part 2 list tests and benchmark; Part 3 sequential A*, parallel A* (six variants), HDA*, batch mode, and their tests |
| `scripts/` | Benchmark runners and plotting/summary scripts |
| `data/` | The road graph (`nodes.csv`, `edges.csv`: 32,895 nodes, 75,882 edges) and the lecturer's sample pair |
| `results/` | Raw CSVs, logs and plots per machine: `dell-pc/`, `dell-laptop/`, `mac-arm/` |

`CORRECTNESS.md` maps each part of the assignment to its files and tests.

## Requirements

- Linux or macOS (the x86 runs used WSL2 Ubuntu), `g++` 15 or Apple clang, `make`
- Python 3 with `pandas` and `matplotlib`; `osmnx` only if you want to re-download the map

The graph is already in `data/`, so nothing needs to be downloaded.

## Quick check

```bash
make all
make test && make tsan                 # Part 2: concurrent lists
make test_astar && make tsan_astar     # Part 3: parallel A*
make test_hda && make tsan_hda         # Part 3: HDA*
python python/test_astar.py data/nodes.csv data/edges.csv 100
python python/test_variants.py data/nodes.csv data/edges.csv
```

Each test prints `ALL AS EXPECTED` (or `FAIL: 0`). Every test also runs a deliberately broken version as a negative control, which must report `BUG DETECTED`.

## Reproducing the measurements

```bash
bash scripts/run_all.sh <machine>      # lists, A*, batch, thread spawn
bash scripts/run_extra.sh <machine>    # priority-queue workload, lazy open list
bash scripts/run_hda.sh <machine>      # HDA*
python scripts/plot_all.py <machine> > results/<machine>/summary.txt
python scripts/summarize_extra.py <machine>
python scripts/summarize_hda.py <machine>
```

Each script repeats every configuration 5 times and the summaries take the median. Speedup is always measured against `astar_seq` from the same run.

Part 1 and Part 4 experiments:

```bash
python python/exp_weighted.py 50
python python/exp_pareto.py teacher
python python/exp_uncertain.py 8 200
python python/exp_h_variants.py 50 42
python python/exp_alt.py 50 42 4,8,16
python python/exp_ch.py 50 42 50
```

## Running a single query

```bash
./build/astar_par data/nodes.csv data/edges.csv teacher 42 8 1 lazy pool
./build/astar_hda data/nodes.csv data/edges.csv teacher 42 8 1 1 pool
```

Arguments: `<pairs|teacher> <seed> <threads> [run] ...`. With `threads = 0`, `astar_par` runs the sequential baseline. Optional arguments for `astar_par`: `[list|heap|lazy] [create|pool]`; for `astar_hda`: `[batch] [create|pool]`.
