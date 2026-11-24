#pragma once
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>

inline void start_bench_timeout(const std::string& timeout_csv_line) {
    double limit = 30.0;
    if (const char* s = std::getenv("BENCH_TIMEOUT")) limit = std::atof(s);
    if (limit <= 0) return;
    std::thread([limit, timeout_csv_line] {
        std::this_thread::sleep_for(std::chrono::duration<double>(limit));
        std::printf("%s\n", timeout_csv_line.c_str());
        std::fflush(stdout);
        std::_Exit(2);
    }).detach();
}
