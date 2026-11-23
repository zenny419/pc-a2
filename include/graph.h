#pragma once
// =====================================================================
//  graph.h — reads data/nodes.csv + data/edges.csv (produced by export_graph.py)
//  Shared by astar_seq, astar_par and the tests.
//  OSM IDs are huge (e.g. 11640279650) -> remap them to indices 0..n-1 for arrays.
// =====================================================================
#include <cmath>
#include <cstdint>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

struct Edge { int to; double w; };          // w = length (metres)

struct Graph {
    std::vector<int64_t> osm_id;             // index -> OSM ID
    std::vector<double>  lat, lon;
    std::vector<std::vector<Edge>> adj;
    std::unordered_map<int64_t, int> index;  // OSM ID -> index

    int n() const { return (int)adj.size(); }

    // Straight-line (great-circle) distance in metres: the A* h, admissible because a real road is never shorter.
    double haversine(int a, int b) const {
        constexpr double R = 6371000.0, D2R = M_PI / 180.0;
        double dlat = (lat[b] - lat[a]) * D2R, dlon = (lon[b] - lon[a]) * D2R;
        double h = std::sin(dlat / 2) * std::sin(dlat / 2) +
                   std::cos(lat[a] * D2R) * std::cos(lat[b] * D2R) * std::sin(dlon / 2) * std::sin(dlon / 2);
        return 2 * R * std::asin(std::sqrt(h));
    }
};

inline Graph load_graph(const std::string& nodes_csv, const std::string& edges_csv) {
    Graph g;
    std::ifstream fn(nodes_csv);
    if (!fn) throw std::runtime_error("cannot open " + nodes_csv);
    std::string line;
    std::getline(fn, line);                                  // skip header: id,x,y
    while (std::getline(fn, line)) {
        if (line.empty()) continue;
        std::stringstream ss(line); std::string a, x, y;
        std::getline(ss, a, ','); std::getline(ss, x, ','); std::getline(ss, y, ',');
        int64_t id = std::stoll(a);
        g.index[id] = (int)g.osm_id.size();
        g.osm_id.push_back(id); g.lon.push_back(std::stod(x)); g.lat.push_back(std::stod(y));
    }
    g.adj.resize(g.osm_id.size());
    std::ifstream fe(edges_csv);
    if (!fe) throw std::runtime_error("cannot open " + edges_csv);
    std::getline(fe, line);                                  // u,v,length[,travel_time_min]
    while (std::getline(fe, line)) {
        if (line.empty()) continue;
        std::stringstream ss(line); std::string u, v, w;
        std::getline(ss, u, ','); std::getline(ss, v, ','); std::getline(ss, w, ',');
        int iu = g.index.at(std::stoll(u)), iv = g.index.at(std::stoll(v));
        double len = std::stod(w);
        bool found = false;                                  // parallel edges: keep the shortest one
        for (auto& e : g.adj[iu]) if (e.to == iv) { if (len < e.w) e.w = len; found = true; break; }
        if (!found) g.adj[iu].push_back({iv, len});
    }
    return g;
}
