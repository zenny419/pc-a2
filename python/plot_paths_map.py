import random
from pathlib import Path

import folium

from astar_core import load_graph, astar, path_length
from astar_variants import (SPEEDS, astar_time_dependent, edge_noise_levels,
                            scaled_problem)

ROOT = Path(__file__).resolve().parent.parent
NODES_CSV = ROOT / "data" / "nodes.csv"
EDGES_CSV = ROOT / "data" / "edges.csv"
SAMPLE_PAIR_TXT = ROOT / "data" / "sample_pair.txt"
OUT_HTML = ROOT / "results" / "paths_map.html"
NOISE = 0.2


def robust_plan(adj, coords, s, d, noise=NOISE, seed=0):
    level = edge_noise_levels(adj, noise, random.Random(seed))
    worst = {e: 1 - n for e, n in level.items()}
    r_adj, r_speeds = scaled_problem(adj, worst, 1 + 2 * noise,
                                     [sp * (1 - noise) for sp in SPEEDS])
    return astar_time_dependent(r_adj, coords, s, d, speeds=r_speeds)[1]


def main():
    coords, adj = load_graph(str(NODES_CSV), str(EDGES_CSV))
    s, d = map(int, SAMPLE_PAIR_TXT.read_text().split())
    paths = {
        "Shortest (A*, length)": ("blue", astar(adj, coords, s, d)[1]),
        "Fastest (time-dependent A*)": ("green", astar_time_dependent(adj, coords, s, d)[1]),
        "Robust plan (part b)": ("red", robust_plan(adj, coords, s, d)),
    }

    m = folium.Map(location=coords[s], zoom_start=14, tiles=None)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
                     attr="Tiles &copy; Esri", name="Esri streets").add_to(m)
    for i, (name, (color, path)) in enumerate(paths.items()):
        print(f"{name}: {len(path)} nodes, {path_length(adj, path) / 1000:.2f} km")
        layer = folium.FeatureGroup(name=name).add_to(m)
        folium.PolyLine([coords[v] for v in path], color=color, weight=8 - 2 * i,
                        opacity=0.8, tooltip=name).add_to(layer)
    folium.Marker(coords[s], tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(coords[d], tooltip="Destination", icon=folium.Icon(color="red")).add_to(m)
    folium.LayerControl().add_to(m)
    m.fit_bounds([coords[v] for _, p in paths.values() for v in p])

    OUT_HTML.parent.mkdir(exist_ok=True)
    m.save(str(OUT_HTML))
    same = paths["Shortest (A*, length)"][1] == paths["Fastest (time-dependent A*)"][1]
    print(f"shortest == fastest: {same} -> {OUT_HTML}")


if __name__ == "__main__":
    main()