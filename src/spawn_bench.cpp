#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>
#include <vector>

static double median(std::vector<double> v) {
    std::nth_element(v.begin(), v.begin() + v.size() / 2, v.end());
    return v[v.size() / 2];
}

static double spawn_us(int threads, int reps) {
    std::vector<double> us(reps);
    for (int r = 0; r < reps; ++r) {
        auto t0 = std::chrono::steady_clock::now();
        std::vector<std::thread> pool;
        for (int t = 0; t < threads; ++t) pool.emplace_back([] {});
        for (auto& th : pool) th.join();
        us[r] = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count();
    }
    return median(us);
}

static double wake_us(int threads, int reps) {
    std::mutex m;
    std::condition_variable cv, done_cv;
    long gen = 0;
    int done = 0;
    bool quit = false;
    std::vector<std::thread> pool;
    for (int t = 0; t < threads; ++t)
        pool.emplace_back([&] {
            long seen = 0;
            for (;;) {
                std::unique_lock<std::mutex> lk(m);
                cv.wait(lk, [&] { return gen != seen; });
                seen = gen;
                if (quit) return;
                if (++done == threads) done_cv.notify_one();
            }
        });
    std::vector<double> us(reps);
    for (int r = 0; r < reps; ++r) {
        auto t0 = std::chrono::steady_clock::now();
        {
            std::unique_lock<std::mutex> lk(m);
            done = 0;
            ++gen;
            cv.notify_all();
            done_cv.wait(lk, [&] { return done == threads; });
        }
        us[r] = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count();
    }
    {
        std::lock_guard<std::mutex> lk(m);
        quit = true;
        ++gen;
    }
    cv.notify_all();
    for (auto& th : pool) th.join();
    return median(us);
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: %s <threads> [reps=1000] [run]\n", argv[0]);
        return 1;
    }
    int threads = std::atoi(argv[1]);
    int reps = argc > 2 ? std::atoi(argv[2]) : 1000;
    int run = argc > 3 ? std::atoi(argv[3]) : 1;
    std::printf("variant,threads,run,reps,us_median\n");
    std::printf("spawn,%d,%d,%d,%.2f\n", threads, run, reps, spawn_us(threads, reps));
    std::printf("pool_wake,%d,%d,%d,%.2f\n", threads, run, reps, wake_us(threads, reps));
    return 0;
}
