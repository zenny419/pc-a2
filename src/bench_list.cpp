#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <numeric>
#include <random>
#include <string>
#include <thread>
#include <vector>
#include "lock.h"
#include "sorted_list.h"
#include "lazy_list.h"
#include "bench_util.h"

using namespace std::chrono;

constexpr int KEY_RANGE = 1000;
constexpr int INIT_SIZE = 500;
constexpr int PCT_CONTAINS = 80;
constexpr int PCT_ADD = 10;
// results are summed here, otherwise -O2 drops the list traversal
static volatile long g_sink = 0;

struct alignas(64) PaddedCount {
    long value = 0;
    long hits = 0;
};

template <class List>
double run(int num_threads, double seconds, unsigned seed) {
    List list;
    std::vector<int> keys(KEY_RANGE);
    std::iota(keys.begin(), keys.end(), 0);
    std::mt19937 init_rng(seed);
    std::shuffle(keys.begin(), keys.end(), init_rng);
    for (int i = 0; i < INIT_SIZE; ++i) list.add(keys[i]);

    std::atomic<bool> go{false};
    std::atomic<bool> stop{false};
    std::vector<PaddedCount> counts(num_threads);

    auto worker = [&](int id) {
        std::mt19937 rng(seed * 1000 + id + 1);
        std::uniform_int_distribution<int> key_dist(0, KEY_RANGE - 1);
        std::uniform_int_distribution<int> op_dist(0, 99);
        long done = 0;
        long hits = 0;
        while (!go.load(std::memory_order_acquire)) cpu_relax();
        while (!stop.load(std::memory_order_relaxed)) {
            int k = key_dist(rng);
            int op = op_dist(rng);
            if (op < PCT_CONTAINS) hits += list.contains(k);
            else if (op < PCT_CONTAINS + PCT_ADD) hits += list.add(k);
            else hits += list.remove(k);
            ++done;
        }
        counts[id].value = done;
        counts[id].hits = hits;
    };

    std::vector<std::thread> ts;
    for (int t = 0; t < num_threads; ++t) ts.emplace_back(worker, t);

    auto start = steady_clock::now();
    go.store(true, std::memory_order_release);
    std::this_thread::sleep_for(duration<double>(seconds));
    stop.store(true, std::memory_order_relaxed);
    for (auto& t : ts) t.join();
    double secs = duration<double>(steady_clock::now() - start).count();

    long total = 0, hit_sum = 0;
    for (auto& c : counts) { total += c.value; hit_sum += c.hits; }
    g_sink = hit_sum;
    return total / secs;
}

template <class T> struct list_tag { using type = T; };

template <class F>
bool with_list_type(const std::string& name, F&& f) {
    using bo = lock_ttas_backoff<BackoffKind::SPIN>;
    if (name == "coarse+ttas")    { f(list_tag<CoarseList<int, lock_ttas>>{}); return true; }
    if (name == "coarse+ttas_bo") { f(list_tag<CoarseList<int, bo>>{});        return true; }
    if (name == "coarse+std")     { f(list_tag<CoarseList<int, lock_std>>{});  return true; }
    if (name == "fine+ttas")      { f(list_tag<FineList<int, lock_ttas>>{});   return true; }
    if (name == "fine+ttas_bo")   { f(list_tag<FineList<int, bo>>{});          return true; }
    if (name == "fine+std")       { f(list_tag<FineList<int, lock_std>>{});    return true; }
    if (name == "lazy+ttas")      { f(list_tag<LazyList<int, lock_ttas>>{}); return true; }
    if (name == "lazy+ttas_bo")   { f(list_tag<LazyList<int, bo>>{});        return true; }
    return false;
}

int main(int argc, char** argv) {
    if (argc < 4 || argc > 5) {
        std::fprintf(stderr, "Usage: %s <variant> <threads> <seconds> [run]\n", argv[0]);
        return 1;
    }
    std::string name = argv[1];
    int threads = std::atoi(argv[2]);
    double seconds = std::atof(argv[3]);
    int run_id = argc == 5 ? std::atoi(argv[4]) : 1;

    char prefix[128];
    std::snprintf(prefix, sizeof prefix, "%s,%d,%d", name.c_str(), threads, run_id);
    start_bench_timeout(std::string(prefix) + ",-1");

    double ops_per_sec = 0;
    bool ok = with_list_type(name, [&](auto tag) {
        using L = typename decltype(tag)::type;
        ops_per_sec = run<L>(threads, seconds, 42u + run_id);
    });
    if (!ok) {
        std::fprintf(stderr, "Unknown variant: %s\n", name.c_str());
        return 1;
    }
    std::printf("%s,%.0f\n", prefix, ops_per_sec);
    return 0;
}