#pragma once
#include <atomic>
#include <chrono>
#include <cstddef>
#include <mutex>
#include <thread>
#if __has_include(<pthread.h>)
#include <pthread.h>
#define HAVE_PTHREAD 1
#endif
#if defined(_MSC_VER)
#include <intrin.h>
#endif
#ifdef _OPENMP
#include <omp.h>
#endif

// 128 B covers Apple Silicon; avoids false sharing
constexpr std::size_t CACHE_LINE = 128;

// spin-wait hint, saves power while spinning
inline void cpu_relax() {
#if defined(_MSC_VER) && (defined(_M_X64) || defined(_M_IX86))
    _mm_pause();
#elif defined(_MSC_VER) && defined(_M_ARM64)
    __yield();
#elif defined(__x86_64__) || defined(__i386__)
    __builtin_ia32_pause();
#elif defined(__aarch64__) || defined(__arm64__)
    asm volatile("yield" ::: "memory");
#endif
}

enum class BackoffKind { SLEEP, SPIN };

template <BackoffKind Kind, unsigned MinDelay = 16, unsigned MaxDelay = 4096>
class Backoff {
    unsigned delay = MinDelay;
public:
    void pause() {
        if constexpr (Kind == BackoffKind::SLEEP) {
            std::this_thread::sleep_for(std::chrono::nanoseconds(delay)); // on macOS sleep_for(ns) actually sleeps a few us
        } else {
            for (unsigned i = 0; i < delay; ++i) cpu_relax();
        }
        if (delay < MaxDelay) delay *= 2;
    }
};

class lock_tas {
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        while (locked.exchange(true, std::memory_order_acquire)) {
            cpu_relax();
        }
    }
    void release() {
        locked.store(false, std::memory_order_release);
    }
};

template <BackoffKind Kind>
class lock_tas_backoff {
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        Backoff<Kind> bo;
        while (locked.exchange(true, std::memory_order_acquire)) {
            bo.pause();
        }
    }
    void release() {
        locked.store(false, std::memory_order_release);
    }
};

class lock_ttas {
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        while (true) {
            while (locked.load(std::memory_order_relaxed)) {
                cpu_relax();
            }
            if (!locked.exchange(true, std::memory_order_acquire)) {
                return;
            }
        }
    }
    void release() {
        locked.store(false, std::memory_order_release);
    }
};

template <BackoffKind Kind>
class lock_ttas_backoff {
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        Backoff<Kind> bo;
        while (true) {
            while (locked.load(std::memory_order_relaxed)) {
                cpu_relax();
            }
            if (!locked.exchange(true, std::memory_order_acquire)) {
                return;
            }
            bo.pause();
        }
    }
    void release() {
        locked.store(false, std::memory_order_release);
    }
};

struct alignas(CACHE_LINE) mcs_node {
    std::atomic<mcs_node*> next{nullptr};
    std::atomic<bool>      locked{false};
};

class lock_mcs {
    using Node = mcs_node;
    alignas(CACHE_LINE) std::atomic<Node*> tail{nullptr};
    static inline thread_local Node me;
public:
    void acquire() {
        me.next.store(nullptr, std::memory_order_relaxed);
        me.locked.store(true, std::memory_order_relaxed);

        Node* pred = tail.exchange(&me, std::memory_order_acq_rel);

        if (pred != nullptr) {
            pred->next.store(&me, std::memory_order_release);
            while (me.locked.load(std::memory_order_acquire)) {
                cpu_relax();
            }
        }
    }
    void release() {
        Node* succ = me.next.load(std::memory_order_acquire);
        if (succ == nullptr) {
            Node* expected = &me;
            if (tail.compare_exchange_strong(expected, nullptr,
                                             std::memory_order_acq_rel)) {
                return;
            }
            while ((succ = me.next.load(std::memory_order_acquire)) == nullptr) {
                cpu_relax();
            }
        }
        succ->locked.store(false, std::memory_order_release);
    }
};

class lock_std {
    std::mutex m;
public:
    void acquire() { m.lock(); }
    void release() { m.unlock(); }
};

#if defined(HAVE_PTHREAD)
class lock_pthread {
    pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
public:
    ~lock_pthread() { pthread_mutex_destroy(&m); }
    void acquire() { pthread_mutex_lock(&m); }
    void release() { pthread_mutex_unlock(&m); }
};
#endif

#ifdef _OPENMP
class lock_omp {
    omp_lock_t l;
public:
    lock_omp()  { omp_init_lock(&l); }
    ~lock_omp() { omp_destroy_lock(&l); }
    void acquire() { omp_set_lock(&l); }
    void release() { omp_unset_lock(&l); }
};
#endif
