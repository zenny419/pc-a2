"""
export_graph.py — downloads the HCMC road network from OpenStreetMap and saves 2 CSV files shared by Python and C++.
Idea taken from HW_Q2's run.py, but:
  - the download area must contain the instructor's 2 sample points (Thu Thiem -> Thu Duc), not just HCMUT - Ben Thanh;
  - it saves an EDGE LIST + COORDINATES (A* needs coordinates to compute h), not an adjacency matrix.
Run (in WSL, venv with osmnx installed):  python python/export_graph.py
(works from any directory: all paths are built from ROOT)
"""
import csv
from pathlib import Path

import osmnx as ox

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
NODES_CSV = DATA_DIR / "nodes.csv"
EDGES_CSV = DATA_DIR / "edges.csv"
SAMPLE_PAIR_TXT = DATA_DIR / "sample_pair.txt"

SRC = (10.768856, 106.725019)
DST = (10.839613, 106.845798)

CENTER = ((SRC[0] + DST[0]) / 2, (SRC[1] + DST[1]) / 2)
DIST_M = 10_000

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading OSM drive network ... (a few minutes)")
    G = ox.graph_from_point(CENTER, dist=DIST_M, network_type="drive")
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    s = ox.distance.nearest_nodes(G, X=SRC[1], Y=SRC[0])
    d = ox.distance.nearest_nodes(G, X=DST[1], Y=DST[0])

    with open(NODES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "x", "y"])
        for n, a in G.nodes(data=True):
            w.writerow([n, a["x"], a["y"]])

    with open(EDGES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["u", "v", "length", "travel_time_min"])
        for u, v, a in G.edges(data=True):
            w.writerow([u, v, round(a["length"], 3), round(a["travel_time"] / 60, 5)])

    with open(SAMPLE_PAIR_TXT, "w") as f:
        f.write(f"{s} {d}\n")

    print(f"Nodes: {G.number_of_nodes()}  Edges: {G.number_of_edges()}")
    print(f"Sample pair (instructor): {s} -> {d}  (saved to {SAMPLE_PAIR_TXT})")

if __name__ == "__main__":
    main()
