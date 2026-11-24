#include "graph.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <queue>
#include <random>
#include <utility>
#include <vector>

struct Result { double cost; long expanded; std::vector<int> path; };

Result astar(const Graph& g, int s, int d, double h_scale = 1.0) {
    const double INF = std::numeric_limits<double>::infinity();
    std::vector<double> best(g.n(), INF);
    std::vector<int> prev(g.n(), -1);
    std::vector<char> closed(g.n(), 0);
    using Item = std::pair<double, int>;
    std::priority_queue<Item, std::vector<Item>, std::greater<Item>> open;
    best[s] = 0; open.push({h_scale * g.haversine(s, d), s});
    long expanded = 0;
    while (!open.empty()) {
        int u = open.top().second; open.pop();
        if (closed[u]) continue;
        if (u == d) {
            Result r{best[d], expanded, {}};
            for (int x = d; x != -1; x = prev[x]) r.path.push_back(x);
            return r;
        }
        closed[u] = 1; ++expanded;
        for (const Edge& e : g.adj[u]) {
            if (closed[e.to]) continue;
            double ng = best[u] + e.w;
            if (ng < best[e.to]) {
                best[e.to] = ng; prev[e.to] = u;
                open.push({ng + h_scale * g.haversine(e.to, d), e.to});
            }
        }
    }
    return {INF, expanded, {}};
}

#ifndef ASTAR_SEQ_NO_MAIN
int main(int argc, char** argv) {
    if (argc < 3) { std::fprintf(stderr, "usage: %s nodes.csv edges.csv [pairs] [seed]\n", argv[0]); return 1; }
    Graph g = load_graph(argv[1], argv[2]);
    int pairs = argc > 3 ? std::atoi(argv[3]) : 20;
    unsigned seed = argc > 4 ? std::atoi(argv[4]) : 42;
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> pick(0, g.n() - 1);
    std::printf("src,dst,cost_m,expanded,ms\n");
    for (int i = 0; i < pairs; ++i) {
        int s = pick(rng), d = pick(rng);
        auto t0 = std::chrono::steady_clock::now();
        Result r = astar(g, s, d);
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        std::printf("%lld,%lld,%.3f,%ld,%.3f\n", (long long)g.osm_id[s], (long long)g.osm_id[d], r.cost, r.expanded, ms);
    }
    return 0;
}
#endif
