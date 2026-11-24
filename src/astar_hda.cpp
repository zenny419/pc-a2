#define ASTAR_PAR_NO_MAIN
#include "astar_par.cpp"

enum class HdaStop { Correct, IgnoreInflight };

struct HdaStats {
    long expanded = 0;
    long stale_pops = 0;
    long pruned = 0;
    long remote_msgs = 0;
    long local_relax = 0;
    long max_thread_expanded = 0;
};

struct HdaResult {
    double cost;
    std::vector<int> path;
    HdaStats st;
};

struct HdaMsg {
    int v;
    int parent;
    double g;
    double h;
};

struct alignas(CACHE_LINE) HdaWorker {
    using Item = std::tuple<double, double, int>;
    std::priority_queue<Item, std::vector<Item>, std::greater<Item>> heap;
    lock_ttas inbox_lock;
    std::vector<HdaMsg> inbox;
    alignas(CACHE_LINE) std::atomic<int> inbox_n{0};
    std::vector<HdaMsg> drained;
    std::vector<std::vector<HdaMsg>> outbuf;
    HdaStats st;
};

class HdaEngine {
public:
    HdaEngine(const Graph& g, int threads, int batch, HdaStop rule, double h_scale)
        : g_(g), n_(g.n()), threads_(threads), batch_(batch < 1 ? 1 : batch), rule_(rule), h_scale_(h_scale),
          gv_(new double[g.n()]), prev_(new int[g.n()]), owner_(new int[g.n()]), workers_(threads) {
        for (int v = 0; v < n_; ++v) owner_[v] = (int)(((uint64_t)(uint32_t)v * 0x9E3779B97F4A7C15ull >> 32) % threads_);
        for (auto& w : workers_) w.outbuf.resize(threads_);
        for (int t = 0; t < threads_; ++t) pool_.emplace_back([this, t] { loop(t); });
    }

    ~HdaEngine() {
        {
            std::lock_guard<std::mutex> lk(m_);
            quit_ = true;
            ++gen_;
        }
        cv_.notify_all();
        for (auto& th : pool_) th.join();
    }

    HdaResult solve(int s, int d) {
        const double INF = std::numeric_limits<double>::infinity();
        for (int i = 0; i < n_; ++i) {
            gv_[i] = INF;
            prev_[i] = -1;
        }
        for (auto& w : workers_) {
            w.heap = {};
            w.inbox.clear();
            w.inbox_n.store(0);
            for (auto& b : w.outbuf) b.clear();
            w.st = HdaStats{};
        }
        d_ = d;
        best_.store(INF);
        work_.store(threads_);
        gv_[s] = 0.0;
        if (s == d) best_.store(0.0);
        else workers_[owner_[s]].heap.push({h_scale_ * g_.haversine(s, d), 0.0, s});

        {
            std::unique_lock<std::mutex> lk(m_);
            done_ = 0;
            ++gen_;
            cv_.notify_all();
            done_cv_.wait(lk, [this] { return done_ == threads_; });
        }

        HdaResult r{best_.load(), {}, {}};
        if (r.cost < INF) {
            for (int x = d, steps = 0; x != -1 && steps <= n_; x = prev_[x], ++steps) r.path.push_back(x);
            std::reverse(r.path.begin(), r.path.end());
        }
        for (auto& w : workers_) {
            r.st.expanded += w.st.expanded;
            r.st.stale_pops += w.st.stale_pops;
            r.st.pruned += w.st.pruned;
            r.st.remote_msgs += w.st.remote_msgs;
            r.st.local_relax += w.st.local_relax;
            r.st.max_thread_expanded = std::max(r.st.max_thread_expanded, w.st.expanded);
        }
        return r;
    }

private:
    void loop(int t) {
        long seen = 0;
        for (;;) {
            {
                std::unique_lock<std::mutex> lk(m_);
                cv_.wait(lk, [&] { return gen_ != seen; });
                seen = gen_;
                if (quit_) return;
            }
            work(t);
            {
                std::lock_guard<std::mutex> lk(m_);
                if (++done_ == threads_) done_cv_.notify_one();
            }
        }
    }

    void lower_best(double c) {
        double cur = best_.load();
        while (c < cur && !best_.compare_exchange_weak(cur, c)) {
        }
    }

    void relax(HdaWorker& w, int v, int parent, double ng, double hv) {
        if (!(ng < gv_[v])) return;
        gv_[v] = ng;
        prev_[v] = parent;
        if (v == d_) {
            lower_best(ng);
            return;
        }
        double f = ng + hv;
        if (f >= best_.load()) {
            ++w.st.pruned;
            return;
        }
        w.heap.push({f, ng, v});
    }

    void flush(int dest, HdaWorker& w) {
        auto& buf = w.outbuf[dest];
        if (buf.empty()) return;
        long k = (long)buf.size();
        if (rule_ == HdaStop::Correct) work_.fetch_add(k);
        HdaWorker& to = workers_[dest];
        to.inbox_lock.acquire();
        to.inbox.insert(to.inbox.end(), buf.begin(), buf.end());
        to.inbox_lock.release();
        to.inbox_n.fetch_add((int)k);
        buf.clear();
    }

    void flush_all(HdaWorker& w) {
        for (int dest = 0; dest < threads_; ++dest) flush(dest, w);
    }

    void drain(HdaWorker& w) {
        if (w.inbox_n.load() == 0) return;
        w.inbox_lock.acquire();
        w.drained.swap(w.inbox);
        int k = (int)w.drained.size();
        w.inbox_lock.release();
        w.inbox_n.fetch_sub(k);
        for (const HdaMsg& m : w.drained) relax(w, m.v, m.parent, m.g, m.h);
        w.drained.clear();
        if (rule_ == HdaStop::Correct && k > 0) work_.fetch_sub(k);
    }

    bool expand_one(int t, HdaWorker& w) {
        while (!w.heap.empty()) {
            auto [f, gk, u] = w.heap.top();
            if (f >= best_.load()) {
                w.st.pruned += (long)w.heap.size();
                w.heap = {};
                return false;
            }
            w.heap.pop();
            if (gk > gv_[u]) {
                ++w.st.stale_pops;
                continue;
            }
            ++w.st.expanded;
            for (const Edge& e : g_.adj[u]) {
                int v = e.to;
                double ng = gk + e.w;
                double hv = (v == d_) ? 0.0 : h_scale_ * g_.haversine(v, d_);
                if (ng + hv >= best_.load()) {
                    ++w.st.pruned;
                    continue;
                }
                int o = owner_[v];
                if (o == t) {
                    ++w.st.local_relax;
                    relax(w, v, u, ng, hv);
                } else {
                    ++w.st.remote_msgs;
                    w.outbuf[o].push_back({v, u, ng, hv});
                    if ((int)w.outbuf[o].size() >= batch_) flush(o, w);
                }
            }
            return true;
        }
        return false;
    }

    void work(int t) {
        HdaWorker& w = workers_[t];
        for (;;) {
            drain(w);
            if (expand_one(t, w)) continue;
            flush_all(w);
            if (w.inbox_n.load() > 0) continue;
            work_.fetch_sub(1);
            for (;;) {
                if (w.inbox_n.load() > 0) {
                    work_.fetch_add(1);
                    break;
                }
                if (work_.load() <= 0) return;
                std::this_thread::yield();
            }
        }
    }

    const Graph& g_;
    const int n_;
    const int threads_;
    const int batch_;
    const HdaStop rule_;
    const double h_scale_;
    std::unique_ptr<double[]> gv_;
    std::unique_ptr<int[]> prev_;
    std::unique_ptr<int[]> owner_;
    std::vector<HdaWorker> workers_;
    int d_ = 0;
    std::atomic<double> best_{0.0};
    alignas(CACHE_LINE) std::atomic<long> work_{0};

    std::vector<std::thread> pool_;
    std::mutex m_;
    std::condition_variable cv_, done_cv_;
    long gen_ = 0;
    int done_ = 0;
    bool quit_ = false;
};

#ifndef ASTAR_HDA_NO_MAIN
static void print_row(const char* variant, int threads, int run, const Graph& g, int s, int d, const HdaResult& r,
                      double ms) {
    long msgs = r.st.remote_msgs + r.st.local_relax;
    double remote_frac = msgs ? double(r.st.remote_msgs) / msgs : 0.0;
    double imbalance = r.st.expanded ? double(r.st.max_thread_expanded) * threads / r.st.expanded : 0.0;
    std::printf("%s,%d,%d,%lld,%lld,%.3f,%ld,%ld,%ld,%ld,%.3f,%.3f,%.3f\n", variant, threads, run,
                (long long)g.osm_id[s], (long long)g.osm_id[d], r.cost, r.st.expanded, r.st.stale_pops, r.st.pruned,
                r.st.remote_msgs, remote_frac, imbalance, ms);
    std::fflush(stdout);
}

int main(int argc, char** argv) {
    if (argc < 6) {
        std::fprintf(stderr, "usage: %s nodes.csv edges.csv <pairs|teacher> <seed> <threads> [run] [batch] [create|pool]\n",
                     argv[0]);
        return 1;
    }
    Graph g = load_graph(argv[1], argv[2]);
    auto pairs = make_pairs(g, argv[1], argv[3], (unsigned)std::atoi(argv[4]));
    int threads = std::atoi(argv[5]);
    int run = argc > 6 ? std::atoi(argv[6]) : 1;
    int batch = argc > 7 ? std::atoi(argv[7]) : 1;
    bool pool = (argc > 8 ? std::string(argv[8]) : std::string("pool")) == "pool";
    if (threads < 1 || batch < 1) {
        std::fprintf(stderr, "threads and batch must be >= 1\n");
        return 1;
    }
    std::string name = batch == 1 ? "hda" : "hda_b" + std::to_string(batch);
    if (pool) name += "_pool";
    std::printf("variant,threads,run,src,dst,cost_m,expanded,stale_pops,pruned,remote_msgs,remote_frac,imbalance,ms\n");
    std::unique_ptr<HdaEngine> shared;
    if (pool) shared = std::make_unique<HdaEngine>(g, threads, batch, HdaStop::Correct, 1.0);
    for (auto [s, d] : pairs) {
        auto t0 = std::chrono::steady_clock::now();
        HdaResult r;
        if (pool) {
            r = shared->solve(s, d);
        } else {
            HdaEngine eng(g, threads, batch, HdaStop::Correct, 1.0);
            r = eng.solve(s, d);
        }
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        print_row(name.c_str(), threads, run, g, s, d, r, ms);
    }
    return 0;
}
#endif
