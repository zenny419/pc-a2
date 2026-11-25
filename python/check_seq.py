import csv
import sys
import time

from astar_core import load_graph, dijkstra, astar


def first(x):
    return x[0] if isinstance(x, tuple) else x


def main():
    nodes_csv, edges_csv, seq_csv = sys.argv[1:4]
    tol = 0.01
    coords, adj = load_graph(nodes_csv, edges_csv)

    rows = list(csv.DictReader(open(seq_csv)))
    match = 0
    max_diff = 0.0
    cpp_ms = py_ms = 0.0
    cpp_exp = py_exp = 0
    for r in rows:
        s, d = int(r["src"]), int(r["dst"])
        c_cpp = float(r["cost_m"])
        c_ref = first(dijkstra(adj, s, d))
        t0 = time.perf_counter()
        res = astar(adj, coords, s, d)
        py_ms += (time.perf_counter() - t0) * 1000
        diff = abs(c_cpp - c_ref)
        max_diff = max(max_diff, diff)
        ok = diff <= tol
        match += ok
        cpp_ms += float(r["ms"])
        cpp_exp += int(r["expanded"])
        if isinstance(res, tuple) and len(res) >= 3:
            py_exp += res[2]
        if not ok:
            print(f"MISMATCH {s}->{d}: cpp={c_cpp:.3f} dijkstra={c_ref:.3f}")

    n = len(rows)
    print(f"pairs: {n}  MATCH: {match}/{n}  max |diff|: {max_diff:.4f} m")
    print(f"avg time  C++ astar_seq: {cpp_ms / n:.3f} ms   Python astar: {py_ms / n:.3f} ms   ratio: {py_ms / cpp_ms:.1f}x")
    print(f"avg expanded  C++: {cpp_exp / n:.0f}   Python: {py_exp / n:.0f}")
    print("RESULT:", "PASS" if match == n else "FAIL")
    sys.exit(0 if match == n else 1)


if __name__ == "__main__":
    main()
