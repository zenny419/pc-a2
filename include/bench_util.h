#pragma once
// =====================================================================
//  bench_util.h — utilities shared by the 3 benchmark programs
//  (bench_lock, bench_barrier, bench_counter).
//
//  Time limit per run: some configurations can be abnormally slow
//  (e.g. MCS when threads > cores; *_bo_sleep on Windows because
//  sleep_for() sleeps at least ~1 ms). Instead of hanging the whole session, after the
//  limit we print one CSV line with seconds = -1 (meaning TIMEOUT) and exit.
//  Default limit 30 seconds; change it with the environment variable BENCH_TIMEOUT (seconds).
// =====================================================================
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>

inline void start_bench_timeout(const std::string& timeout_csv_line) {
    double limit = 30.0;
    if (const char* s = std::getenv("BENCH_TIMEOUT")) limit = std::atof(s);
    if (limit <= 0) return;                       // BENCH_TIMEOUT=0 -> disabled
    std::thread([limit, timeout_csv_line] {
        std::this_thread::sleep_for(std::chrono::duration<double>(limit));
        std::printf("%s\n", timeout_csv_line.c_str());
        std::fflush(stdout);
        std::_Exit(2);                            // exit code 2 = TIMEOUT
    }).detach();
}
