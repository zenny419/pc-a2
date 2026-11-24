#define ASTAR_SEQ_NO_MAIN
#include "astar_seq.cpp"
#include "lock.h"
#include "sorted_list.h"
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <fstream>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <tuple>

using ParKey = std::tuple<double, double, int>;

enum class StopRule { Correct, FirstTouch };

struct ParStats {
    long expanded = 0;
    long stale_pops = 0;
    long pruned = 0;
    double list_len_avg = 0;
};

struct ParResult {
    double cost;
    std::vector<int> path;
    ParStats st;
};

enum class OpenKind { List, Heap };

class OpenHeap {
    std::priority_queue<ParKey, std::vector<ParKey>, std::greater<ParKey>> pq_;
    std::mutex m_;

public:
    bool add(const ParKey& k) {
        std::lock_guard<std::mutex> lk(m_);
        pq_.push(k);
        return true;
    }
    std::optional<ParKey> remove_min() {
        std::lock_guard<std::mutex> lk(m_);
        if (pq_.empty()) return std::nullopt;
        ParKey k = pq_.top();
        pq_.pop();
        return k;
    }
};

template <class Open>
static ParResult astar_par_impl(const Graph& g, int s, int d, int threads, StopRule rule, double h_scale) {
    const double INF = std::numeric_limits<double>::infinity();
    const int n = g.n();
    std::unique_ptr<std::atomic<double>[]> gv(new std::atomic<double>[n]);
    std::unique_ptr<int[]> prev(new int[n]);
    std::unique_ptr<lock_ttas[]> node_lock(new lock_ttas[n]);
    for (int i = 0; i < n; ++i) {
        gv[i].store(INF, std::memory_order_relaxed);
        prev[i] = -1;
    }

    Open open;
    std::atomic<double> best{INF};
    std::atomic<long> pending{0};
    std::atomic<bool> stop{false};
    std::atomic<long> expanded{0}, stale{0}, pruned{0};
    std::atomic<long> in_list{0}, adds{0}, len_sum{0}, len_samples{0};

    auto lower_best = [&](double c) {
        double cur = best.load();
        while (c < cur && !best.compare_exchange_weak(cur, c)) {
        }
    };

    auto push = [&](double f, double gg, int v) {
        pending.fetch_add(1);
        if (open.add(ParKey{f, gg, v})) {
            long len = in_list.fetch_add(1) + 1;
            if (adds.fetch_add(1) % 1000 == 0) {
                len_sum.fetch_add(len);
                len_samples.fetch_add(1);
            }
        } else {
            pending.fetch_sub(1);
        }
    };

    gv[s].store(0.0);
    if (s == d) lower_best(0.0);
    else push(h_scale * g.haversine(s, d), 0.0, s);

    auto worker = [&]() {
        while (!stop.load() && pending.load() > 0) {
            std::optional<ParKey> k = open.remove_min();
            if (!k) {
                std::this_thread::yield();
                continue;
            }
            in_list.fetch_sub(1);
            auto [f, gk, u] = *k;
            if (f >= best.load()) {
                pruned.fetch_add(1);
                pending.fetch_sub(1);
                continue;
            }
            if (gk > gv[u].load()) {
                stale.fetch_add(1);
                pending.fetch_sub(1);
                continue;
            }
            expanded.fetch_add(1);
            for (const Edge& e : g.adj[u]) {
                int v = e.to;
                double ng = gk + e.w;
                double hv = (v == d) ? 0.0 : h_scale * g.haversine(v, d);
                if (ng + hv >= best.load()) {
                    pruned.fetch_add(1);
                    continue;
                }
                node_lock[v].acquire();
                bool better = ng < gv[v].load();
                if (better) {
                    gv[v].store(ng);
                    prev[v] = u;
                }
                node_lock[v].release();
                if (!better) continue;
                if (v == d) {
                    lower_best(ng);
                    if (rule == StopRule::FirstTouch) stop.store(true);
                    continue;
                }
                push(ng + hv, ng, v);
            }
            pending.fetch_sub(1);
        }
    };

    std::vector<std::thread> pool;
    for (int t = 0; t < threads; ++t) pool.emplace_back(worker);
    for (auto& th : pool) th.join();

    ParResult r{best.load(), {}, {}};
    if (r.cost < INF) {
        for (int x = d, steps = 0; x != -1 && steps <= n; x = prev[x], ++steps) r.path.push_back(x);
        std::reverse(r.path.begin(), r.path.end());
    }
    r.st.expanded = expanded.load();
    r.st.stale_pops = stale.load();
    r.st.pruned = pruned.load();
    r.st.list_len_avg = len_samples.load() ? double(len_sum.load()) / len_samples.load() : 0.0;
    return r;
}

ParResult astar_par(const Graph& g, int s, int d, int threads, StopRule rule = StopRule::Correct,
                    double h_scale = 1.0, OpenKind kind = OpenKind::List) {
    if (kind == OpenKind::Heap) return astar_par_impl<OpenHeap>(g, s, d, threads, rule, h_scale);
    return astar_par_impl<FineList<ParKey, lock_ttas>>(g, s, d, threads, rule, h_scale);
}

std::vector<std::pair<int, int>> make_pairs(const Graph& g, const std::string& nodes_csv,
                                            const std::string& pairs_arg, unsigned seed) {
    std::vector<std::pair<int, int>> pairs;
    if (pairs_arg == "teacher") {
        std::string dir = nodes_csv.substr(0, nodes_csv.find_last_of('/') + 1);
        std::ifstream f(dir + "sample_pair.txt");
        long long a = 0, b = 0;
        if (!(f >> a >> b)) throw std::runtime_error("cannot read " + dir + "sample_pair.txt");
        pairs.push_back({g.index.at(a), g.index.at(b)});
    } else {
        int count = std::stoi(pairs_arg);
        std::mt19937 rng(seed);
        std::uniform_int_distribution<int> pick(0, g.n() - 1);
        for (int i = 0; i < count; ++i) {
            int s = pick(rng), d = pick(rng);
            pairs.push_back({s, d});
        }
    }
    return pairs;
}

#ifndef ASTAR_PAR_NO_MAIN
int main(int argc, char** argv) {
    if (argc < 6) {
        std::fprintf(stderr, "usage: %s nodes.csv edges.csv <pairs|teacher> <seed> <threads> [run][list|heap]\n", argv[0]);
        std::fprintf(stderr, "threads = 0 runs astar_seq on the same pairs\n");
        return 1;
    }
    Graph g = load_graph(argv[1], argv[2]);
    auto pairs = make_pairs(g, argv[1], argv[3], (unsigned)std::atoi(argv[4]));
    int threads = std::atoi(argv[5]);
    int run = argc > 6 ? std::atoi(argv[6]) : 1;
    std::string open_arg = argc > 7 ? argv[7] : "list";
    OpenKind kind = open_arg == "heap" ? OpenKind::Heap : OpenKind::List;
    const char* variant = kind == OpenKind::Heap ? "par_heap" : "par";
    std::printf("variant,threads,run,src,dst,cost_m,expanded,stale_pops,pruned,list_len_avg,ms\n");
    for (auto [s, d] : pairs) {
        auto t0 = std::chrono::steady_clock::now();
        if (threads == 0) {
            Result r = astar(g, s, d);
            double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
            std::printf("seq,0,%d,%lld,%lld,%.3f,%ld,0,0,0,%.3f\n", run, (long long)g.osm_id[s],
                        (long long)g.osm_id[d], r.cost, r.expanded, ms);
        } else {
            ParResult r = astar_par(g, s, d, threads, StopRule::Correct, 1.0, kind);
            double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
            std::printf("%s,%d,%d,%lld,%lld,%.3f,%ld,%ld,%ld,%.1f,%.3f\n", variant, threads, run, (long long)g.osm_id[s],
                        (long long)g.osm_id[d], r.cost, r.st.expanded, r.st.stale_pops, r.st.pruned,
                        r.st.list_len_avg, ms);;
        }
        std::fflush(stdout);
    }
    return 0;
}
#endif
