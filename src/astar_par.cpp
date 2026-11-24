#define ASTAR_SEQ_NO_MAIN
#include "astar_seq.cpp"
#include "lock.h"
#include "sorted_list.h"
#include <algorithm>
#include <atomic>
#include <condition_variable>
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
class ParEngine {
public:
    ParEngine(const Graph& g, int threads, StopRule rule, double h_scale)
        : g_(g), n_(g.n()), threads_(threads), rule_(rule), h_scale_(h_scale),
          gv_(new std::atomic<double>[g.n()]), prev_(new int[g.n()]), node_lock_(new lock_ttas[g.n()]) {
        for (int t = 0; t < threads_; ++t) pool_.emplace_back([this] { loop(); });
    }

    ~ParEngine() {
        {
            std::lock_guard<std::mutex> lk(m_);
            quit_ = true;
            ++gen_;
        }
        cv_.notify_all();
        for (auto& th : pool_) th.join();
    }

    ParResult solve(int s, int d) {
        const double INF = std::numeric_limits<double>::infinity();
        for (int i = 0; i < n_; ++i) {
            gv_[i].store(INF, std::memory_order_relaxed);
            prev_[i] = -1;
        }
        open_ = std::make_unique<Open>();
        s_ = s;
        d_ = d;
        best_.store(INF);
        pending_.store(0);
        stop_.store(false);
        expanded_.store(0);
        stale_.store(0);
        pruned_.store(0);
        in_list_.store(0);
        adds_.store(0);
        len_sum_.store(0);
        len_samples_.store(0);

        gv_[s].store(0.0);
        if (s == d) lower_best(0.0);
        else push(h_scale_ * g_.haversine(s, d), 0.0, s);

        {
            std::unique_lock<std::mutex> lk(m_);
            done_ = 0;
            ++gen_;
            cv_.notify_all();
            done_cv_.wait(lk, [this] { return done_ == threads_; });
        }

        ParResult r{best_.load(), {}, {}};
        if (r.cost < INF) {
            for (int x = d, steps = 0; x != -1 && steps <= n_; x = prev_[x], ++steps) r.path.push_back(x);
            std::reverse(r.path.begin(), r.path.end());
        }
        r.st.expanded = expanded_.load();
        r.st.stale_pops = stale_.load();
        r.st.pruned = pruned_.load();
        r.st.list_len_avg = len_samples_.load() ? double(len_sum_.load()) / len_samples_.load() : 0.0;
        return r;
    }

private:
    void loop() {
        long seen = 0;
        for (;;) {
            {
                std::unique_lock<std::mutex> lk(m_);
                cv_.wait(lk, [&] { return gen_ != seen; });
                seen = gen_;
                if (quit_) return;
            }
            work();
            {
                std::lock_guard<std::mutex> lk(m_);
                if (++done_ == threads_) done_cv_.notify_one();
            }
        }
    }

    void lower_best(double c) {
        double cur = best_.load();
        // CAS loop: best only ever decreases, even with many threads
        while (c < cur && !best_.compare_exchange_weak(cur, c)) {
        }
    }

    void push(double f, double gg, int v) {
        pending_.fetch_add(1);
        if (open_->add(ParKey{f, gg, v})) {
            long len = in_list_.fetch_add(1) + 1;
            if (adds_.fetch_add(1) % 1000 == 0) {
                len_sum_.fetch_add(len);
                len_samples_.fetch_add(1);
            }
        } else {
            pending_.fetch_sub(1);
        }
    }

    void work() {
        const int d = d_;
        while (!stop_.load() && pending_.load() > 0) {
            std::optional<ParKey> k = open_->remove_min();
            if (!k) {
                std::this_thread::yield();
                continue;
            }
            in_list_.fetch_sub(1);
            auto [f, gk, u] = *k;
            if (f >= best_.load()) {
                pruned_.fetch_add(1);
                pending_.fetch_sub(1);
                continue;
            }
            if (gk > gv_[u].load()) {
                stale_.fetch_add(1);
                pending_.fetch_sub(1);
                continue;
            }
            expanded_.fetch_add(1);
            for (const Edge& e : g_.adj[u]) {
                int v = e.to;
                double ng = gk + e.w;
                double hv = (v == d) ? 0.0 : h_scale_ * g_.haversine(v, d);
                if (ng + hv >= best_.load()) {
                    pruned_.fetch_add(1);
                    continue;
                }
                node_lock_[v].acquire();
                bool better = ng < gv_[v].load();
                if (better) {
                    gv_[v].store(ng);
                    prev_[v] = u;
                }
                node_lock_[v].release();
                if (!better) continue;
                if (v == d) {
                    lower_best(ng);
                    if (rule_ == StopRule::FirstTouch) stop_.store(true);
                    continue;
                }
                push(ng + hv, ng, v);
            }
            pending_.fetch_sub(1);
        }
    }

    const Graph& g_;
    const int n_;
    const int threads_;
    const StopRule rule_;
    const double h_scale_;
    std::unique_ptr<std::atomic<double>[]> gv_;
    std::unique_ptr<int[]> prev_;
    std::unique_ptr<lock_ttas[]> node_lock_;
    std::unique_ptr<Open> open_;
    int s_ = 0, d_ = 0;
    std::atomic<double> best_{0.0};
    // open-list items + nodes being expanded; search is done when it reaches 0
    std::atomic<long> pending_{0};
    std::atomic<bool> stop_{false};
    std::atomic<long> expanded_{0}, stale_{0}, pruned_{0};
    std::atomic<long> in_list_{0}, adds_{0}, len_sum_{0}, len_samples_{0};

    std::vector<std::thread> pool_;
    std::mutex m_;
    std::condition_variable cv_, done_cv_;
    long gen_ = 0;
    int done_ = 0;
    bool quit_ = false;
};

ParResult astar_par(const Graph& g, int s, int d, int threads, StopRule rule = StopRule::Correct,
                    double h_scale = 1.0, OpenKind kind = OpenKind::List) {
    if (kind == OpenKind::Heap) {
        ParEngine<OpenHeap> eng(g, threads, rule, h_scale);
        return eng.solve(s, d);
    }
    ParEngine<FineList<ParKey, lock_ttas>> eng(g, threads, rule, h_scale);
    return eng.solve(s, d);
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
template <class Open>
static void run_pool(const Graph& g, const std::vector<std::pair<int, int>>& pairs, int threads, int run,
                     const char* variant) {
    ParEngine<Open> eng(g, threads, StopRule::Correct, 1.0);
    for (auto [s, d] : pairs) {
        auto t0 = std::chrono::steady_clock::now();
        ParResult r = eng.solve(s, d);
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        std::printf("%s,%d,%d,%lld,%lld,%.3f,%ld,%ld,%ld,%.1f,%.3f\n", variant, threads, run, (long long)g.osm_id[s],
                    (long long)g.osm_id[d], r.cost, r.st.expanded, r.st.stale_pops, r.st.pruned,
                    r.st.list_len_avg, ms);
        std::fflush(stdout);
    }
}

int main(int argc, char** argv) {
    if (argc < 6) {
        std::fprintf(stderr,
                     "usage: %s nodes.csv edges.csv <pairs|teacher> <seed> <threads> [run] [list|heap] [create|pool]\n",
                     argv[0]);
        std::fprintf(stderr, "threads = 0 runs astar_seq on the same pairs\n");
        return 1;
    }
    Graph g = load_graph(argv[1], argv[2]);
    auto pairs = make_pairs(g, argv[1], argv[3], (unsigned)std::atoi(argv[4]));
    int threads = std::atoi(argv[5]);
    int run = argc > 6 ? std::atoi(argv[6]) : 1;
    std::string open_arg = argc > 7 ? argv[7] : "list";
    std::string mode_arg = argc > 8 ? argv[8] : "create";
    OpenKind kind = open_arg == "heap" ? OpenKind::Heap : OpenKind::List;
    bool pool = mode_arg == "pool";
    const char* variant = kind == OpenKind::Heap ? (pool ? "par_heap_pool" : "par_heap") : (pool ? "par_pool" : "par");
    std::printf("variant,threads,run,src,dst,cost_m,expanded,stale_pops,pruned,list_len_avg,ms\n");
    if (threads > 0 && pool) {
        if (kind == OpenKind::Heap) run_pool<OpenHeap>(g, pairs, threads, run, variant);
        else run_pool<FineList<ParKey, lock_ttas>>(g, pairs, threads, run, variant);
        return 0;
    }
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
                        r.st.list_len_avg, ms);
        }
        std::fflush(stdout);
    }
    return 0;
}
#endif
