#define ASTAR_PAR_NO_MAIN
#include "astar_par.cpp"
#include <cmath>

static bool same_cost(double a, double b) {
    if (std::isinf(a) || std::isinf(b)) return std::isinf(a) && std::isinf(b);
    return std::fabs(a - b) <= 1e-6 * std::max(1.0, b);
}

static bool path_ok(const Graph& g, int s, int d, const ParResult& r) {
    if (std::isinf(r.cost)) return r.path.empty();
    if (r.path.empty() || r.path.front() != s || r.path.back() != d) return false;
    double sum = 0;
    for (size_t i = 0; i + 1 < r.path.size(); ++i) {
        double w = -1;
        for (const Edge& e : g.adj[r.path[i]])
            if (e.to == r.path[i + 1]) { w = e.w; break; }
        if (w < 0) return false;
        sum += w;
    }
    return same_cost(sum, r.cost);
}

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: %s nodes.csv edges.csv [pairs=50] [seed=7] [max_threads=8]\n", argv[0]);
        return 1;
    }
    Graph g = load_graph(argv[1], argv[2]);
    int npairs = argc > 3 ? std::atoi(argv[3]) : 50;
    unsigned seed = argc > 4 ? std::atoi(argv[4]) : 7;
    int max_t = argc > 5 ? std::atoi(argv[5]) : 8;

    auto pairs = make_pairs(g, argv[1], std::to_string(npairs), seed);
    std::vector<double> ref;
    for (auto [s, d] : pairs) ref.push_back(astar(g, s, d, 0.0).cost);

    std::vector<int> tlist;
    for (int t = 1; t <= max_t; t *= 2) tlist.push_back(t);
    if (tlist.back() != max_t) tlist.push_back(max_t);

    bool all_ok = true;
    std::printf("%-12s %8s %10s %s\n", "mode", "threads", "result", "status");
    for (int t : tlist) {
        int good = 0;
        for (size_t i = 0; i < pairs.size(); ++i) {
            auto [s, d] = pairs[i];
            ParResult r = astar_par(g, s, d, t);
            if (same_cost(r.cost, ref[i]) && path_ok(g, s, d, r)) ++good;
            else std::printf("  mismatch threads=%d pair=%zu par=%.3f dijkstra=%.3f\n", t, i, r.cost, ref[i]);
        }
        bool ok = good == (int)pairs.size();
        all_ok = all_ok && ok;
        std::printf("%-12s %8d %6d/%-3zu %s\n", "correct", t, good, pairs.size(), ok ? "PASS" : "FAIL");
        std::fflush(stdout);
    }
    for (int t : tlist) {
        int wrong = 0;
        for (size_t i = 0; i < pairs.size(); ++i) {
            auto [s, d] = pairs[i];
            ParResult r = astar_par(g, s, d, t, StopRule::FirstTouch);
            if (!same_cost(r.cost, ref[i])) ++wrong;
        }
        std::printf("%-12s %8d %6d/%-3zu %s\n", "first-touch", t, wrong, pairs.size(),
                    wrong > 0 ? "wrong costs (info)" : "no wrong cost (info)");
        std::fflush(stdout);
    }
    for (int t : tlist) {
        int wrong = 0;
        for (size_t i = 0; i < pairs.size(); ++i) {
            auto [s, d] = pairs[i];
            ParResult r = astar_par(g, s, d, t, StopRule::Correct, 3.0);
            if (!same_cost(r.cost, ref[i])) ++wrong;
        }
        bool detected = wrong > 0;
        all_ok = all_ok && detected;
        std::printf("%-12s %8d %6d/%-3zu %s\n", "h x 3", t, wrong, pairs.size(),
                    detected ? "BUG DETECTED (ok)" : "NOT DETECTED (test too weak)");
        std::fflush(stdout);
    }
    std::printf("%s\n", all_ok ? "ALL AS EXPECTED" : "UNEXPECTED RESULT");
    return all_ok ? 0 : 1;
}
