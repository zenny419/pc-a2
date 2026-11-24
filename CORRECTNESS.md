# Correctness evidence — Parallel Computing Assignment 2

Duong Hoang Yen. Report: `DHY_Parallel_Computing_Assignment_2.pdf`. Code: this archive and https://github.com/zenny419/pc-a2.

## Map: assignment part → files → report section

| Part | Requirement | Files | Report |
|---|---|---|---|
| 1 | Sequential A* on a real road network | `python/export_graph.py`, `python/astar_core.py` | 2.1 |
| 1 | Dynamic / uncertain h | `python/astar_variants.py`, `python/exp_uncertain.py` | 2.2, 2.3 |
| 1 | Vector-valued f (Pareto) | `python/astar_variants.py`, `python/exp_pareto.py` | 2.4 |
| 1 | Correctness | `python/test_astar.py`, `python/test_variants.py`, `python/check_seq.py` | 2.5 |
| 2 | Two (here three) list variants, locks from A1 | `include/sorted_list.h`, `include/lazy_list.h`, `include/lock.h` | 3.1 |
| 2 | Correctness | `src/test_list.cpp`, `include/test_util.h` | 3.2 |
| 2 | Performance in a chosen scenario | `src/bench_list.cpp`, `include/bench_util.h` | 5.1, 5.2 |
| 3 | Sequential + parallel A* in C++ | `include/graph.h`, `src/astar_seq.cpp`, `src/astar_par.cpp` | 4.1–4.3 |
| 3 | Correctness | `src/test_astar_par.cpp` | 4.4 |
| 3 | Performance and scalability, all versions, all machines | `src/astar_batch.cpp`, `src/spawn_bench.cpp`, `scripts/run_all.sh`, `scripts/plot_all.py`, `results/<machine>/` | 5.3–5.5, 5.7 |
| 4 | Other optimizations (optional) | `src/astar_par.cpp` (pruning, heap, pool), `src/astar_batch.cpp`, `python/exp_weighted.py`, `python/exp_alt.py`, `python/exp_ch.py` | 5.6 |

## How to re-run all checks

```
make all && make test && make tsan             # Part 2
make test_astar && make tsan_astar             # Part 3
python python/test_astar.py data/nodes.csv data/edges.csv 100
python python/test_variants.py data/nodes.csv data/edges.csv
python python/exp_alt.py 50 42 4,8,16           # Part 4: ALT
python python/exp_ch.py 50 42 50                # Part 4: contraction hierarchies
```
Expected output: `ALL AS EXPECTED` for every C++ test, no `WARNING: ThreadSanitizer` line, `FAIL: 0` for the Python tests. `scripts/run_all.sh <machine>` repeats the C++ tests before every measurement run and stores the logs in `results/<machine>/`.

## Part 1 — Sequential A* (Python)

| | |
|---|---|
| Property | Optimal cost (scalar and time-dependent A*), exact Pareto set, and identical cost for the C++ `astar_seq`. |
| Method | Cost compared with Dijkstra; Pareto set compared with brute-force enumeration. Negative control: inflated heuristic (×3) must give wrong costs. |
| Configuration | Real graph (32,895 nodes): 100 random pairs (A*, time-dependent), 20 pairs (C++ vs Python); 40×40 grid (time-dependent); 5×5 grid, 10 cases (Pareto). |
| Result | A* 100/100; control wrong on 97/100 (bug detected); time-dependent 100/100 on both graphs; Pareto 10/10; `astar_seq` 20/20 (max difference 0.0000 m); ALT (Part 4, 50 pairs, seed 42) 50/50 with 4, 8 and 16 landmarks, control ×3 wrong on 48–49/50; contraction hierarchies (Part 4, same 50 pairs) 50/50, unpacked paths 50/50, control "stop at first meeting node" wrong on 17/50. |
| Limitations | Random pairs do not cover all cases; brute force only on a tiny grid; the uncertain-cost model has no exact reference. |

## Part 2 — Concurrent sorted list (C++)

| | |
|---|---|
| Property | Final contents equal the union of the per-thread shadow sets of successful operations; list strictly increasing (sorted, no duplicates); no hang; no data race. |
| Method | `test_list`: concurrent random `add`/`remove`/`contains`; ThreadSanitizer build (`make tsan`); watchdog from Assignment 1. Negative control: `racy` list without locks must fail. |
| Configuration | 12 threads × 20,000 ops × 5 repetitions; 24 threads × 200 ops × 2 repetitions (oversubscribed). |
| Result | Coarse, fine and lazy variants PASS in every repetition; `racy`: BUG DETECTED; TSan: no warnings. |
| Limitations | Testing cannot prove linearizability. `fine+ttas` with 24 threads × 2,000 ops exceeds the watchdog because of a lock convoy (slow, not wrong). |

## Part 3 — Parallel A* (C++)

| | |
|---|---|
| Property | Returned cost equals the Dijkstra optimum; returned path is valid (starts at s, ends at d, existing edges, sums to the cost); no data race. Same for all six variants (sorted list / heap / lazy list × threads per query / pool) and for `astar_batch`. |
| Method | `test_astar_par` against a C++ Dijkstra; ThreadSanitizer build (`make tsan_astar`). Negative control: heuristic ×3 must give wrong costs. Termination argued in report Section 4.2 (`pending` counter). |
| Configuration | Real graph; 50 random pairs (seed 7); six variants at 1/2/4/8/12 threads. Benchmarks: 11 pairs × 5 runs, every variant and thread count; `astar_batch`: 500 pairs vs `batch_seq`. |
| Result | 50/50 correct for every variant and thread count; control: 42–49 of 50 wrong (BUG DETECTED); TSan clean; all benchmark costs equal to `astar_seq`; `astar_batch` 500/500 equal to `batch_seq`. |
| Limitations | On a road network a wrong stopping rule rarely changes the cost, so the stopping rule is also supported by an argument (report Section 4.2), not only by tests. |
