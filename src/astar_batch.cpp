#define ASTAR_SEQ_NO_MAIN
#include "astar_seq.cpp"
#include <atomic>
#include <thread>

static std::vector<std::pair<int, int>> batch_pairs(const Graph& g, int count, unsigned seed) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> pick(0, g.n() - 1);
    std::vector<std::pair<int, int>> pairs;
    pairs.reserve(count);
    for (int i = 0; i < count; ++i) {
        int s = pick(rng), d = pick(rng);
        pairs.push_back({s, d});
    }
    return pairs;
}

static void run_batch(const Graph& g, const std::vector<std::pair<int, int>>& pairs, int threads,
                      std::vector<double>& cost) {
    if (threads == 0) {
        for (size_t i = 0; i < pairs.size(); ++i) cost[i] = astar(g, pairs[i].first, pairs[i].second).cost;
        return;
    }
    std::atomic<size_t> next{0};
    auto worker = [&]() {
        for (size_t i = next.fetch_add(1); i < pairs.size(); i = next.fetch_add(1))
            cost[i] = astar(g, pairs[i].first, pairs[i].second).cost;
    };
    std::vector<std::thread> pool;
    for (int t = 0; t < threads; ++t) pool.emplace_back(worker);
    for (auto& th : pool) th.join();
}

int main(int argc, char** argv) {
    if (argc < 6) {
        std::fprintf(stderr, "usage: %s nodes.csv edges.csv <n_queries> <seed> <threads> [run]\n", argv[0]);
        std::fprintf(stderr, "threads = 0 runs all queries in the main thread (baseline)\n");
        return 1;
    }
    Graph g = load_graph(argv[1], argv[2]);
    int n_queries = std::atoi(argv[3]);
    unsigned seed = (unsigned)std::atoi(argv[4]);
    int threads = std::atoi(argv[5]);
    int run = argc > 6 ? std::atoi(argv[6]) : 1;

    auto pairs = batch_pairs(g, n_queries, seed);
    std::vector<double> ref(pairs.size()), cost(pairs.size(), -1.0);
    run_batch(g, pairs, 0, ref);

    auto t0 = std::chrono::steady_clock::now();
    run_batch(g, pairs, threads, cost);
    double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();

    size_t match = 0;
    for (size_t i = 0; i < pairs.size(); ++i)
        if (cost[i] == ref[i]) ++match;

    std::printf("variant,threads,run,n_queries,ms_total,qps,cost_match\n");
    std::printf("%s,%d,%d,%zu,%.3f,%.1f,%zu\n", threads == 0 ? "batch_seq" : "batch", threads, run, pairs.size(),
                ms, pairs.size() * 1000.0 / ms, match);
    return match == pairs.size() ? 0 : 2;
}
