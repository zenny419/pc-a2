#pragma once
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>

#if defined(__SANITIZE_THREAD__)
#  define UNDER_TSAN 1
#elif defined(__has_feature)
#  if __has_feature(thread_sanitizer)
#    define UNDER_TSAN 1
#  endif
#endif
#ifndef UNDER_TSAN
#  define UNDER_TSAN 0
#endif

class Watchdog {
    std::atomic<long long>   deadline_ms{0};
    std::atomic<const char*> label{""};
    std::atomic<bool>        stop{false};
    std::thread              th;

    static long long now_ms() {
        using namespace std::chrono;
        return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
    }
public:
    Watchdog() {
        th = std::thread([this] {
            while (!stop.load()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
                long long d = deadline_ms.load();
                if (d != 0 && now_ms() > d) {
                    std::printf("\n  !!! TIMEOUT: '%s' exceeded the time limit"
                                " -> DEADLOCK, or abnormally slow (e.g. MCS when threads > cores:\n"
                                "      the next thread in the queue is descheduled by the OS -> the whole queue waits).\n"
                                "      Retry with smaller iters to tell the two cases apart.\n", label.load());
                    std::fflush(stdout);
                    std::_Exit(3);
                }
            }
        });
    }
    ~Watchdog() { stop = true; th.join(); }
    void arm(const char* name, int seconds) {
        label = name;
        deadline_ms = now_ms() + seconds * 1000LL;
    }
    void disarm() { deadline_ms = 0; }
};

struct TestResult {
    bool ok = true;
    long observed = 0;
    long expected = 0;
    const char* why = "";
};

inline bool print_row(const char* name, bool is_control, int pass, int repeats,
                      const TestResult& first_bad) {
    bool good;
    if (!is_control) {
        good = (pass == repeats);
        std::printf("  %-18s %-8s %-22s", name, "real",
                    good ? "PASS" : "FAIL");
    } else {
        good = (pass < repeats);
        std::printf("  %-18s %-8s %-22s", name, "control",
                    good ? "BUG DETECTED (ok)" : "NOT DETECTED (!)");
    }
    std::printf(" %2d/%-2d correct", pass, repeats);
    if (pass < repeats)
        std::printf("   | first failure: %s, observed=%ld, expected=%ld",
                    first_bad.why, first_bad.observed, first_bad.expected);
    std::printf("\n");
    return good;
}

inline void print_header(const char* title, const char* config) {
    std::printf("=====================================================================\n");
    std::printf(" %s\n", title);
    std::printf(" [Frame 3 – Configuration] %s, hw_threads=%u%s\n", config,
                std::thread::hardware_concurrency(),
                UNDER_TSAN ? ", ThreadSanitizer=ON (negative controls skipped)" : "");
    std::printf(" [Frame 4 – Results]\n");
    std::printf("  %-18s %-8s %-22s %s\n", "name", "type", "result", "runs");
    std::printf("---------------------------------------------------------------------\n");
}
