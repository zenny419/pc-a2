#pragma once
// =====================================================================
//  lock.h — mutex lock algorithms for Assignment 1, Part 1
//  Every lock has the same interface: acquire() and release()
//  -> the benchmark is a template, so switching locks needs no code change.
// =====================================================================
#include <atomic>
#include <chrono>
#include <cstddef>
#include <mutex>
#include <thread>
#if __has_include(<pthread.h>)          // macOS, Linux, MinGW/MSYS2 on Windows
#include <pthread.h>
#define HAVE_PTHREAD 1
#endif
#if defined(_MSC_VER)                     // Visual Studio on Windows
#include <intrin.h>
#endif
#ifdef _OPENMP
#include <omp.h>
#endif

// Cache line: 64 bytes on x86, 128 bytes on Apple Silicon (M1/M2/M3...).
// We use 128 to be safe: it avoids false sharing (two different variables in
// the same cache line make the cores fight over that line).
constexpr std::size_t CACHE_LINE = 128;

// Hint to the CPU "I am spinning" -> saves power, reduces pipeline contention.
inline void cpu_relax() {
#if defined(_MSC_VER) && (defined(_M_X64) || defined(_M_IX86))
    _mm_pause();                          // MSVC, Intel/AMD
#elif defined(_MSC_VER) && defined(_M_ARM64)
    __yield();                            // MSVC, Windows on ARM
#elif defined(__x86_64__) || defined(__i386__)
    __builtin_ia32_pause();
#elif defined(__aarch64__) || defined(__arm64__)
    asm volatile("yield" ::: "memory");
#endif
}

// ---------------------------------------------------------------------
//  Exponential backoff (assignment, page 2). Two strategies are compared:
//   - SLEEP: std::this_thread::sleep_for(ns) as suggested by the assignment. On macOS
//     the actual sleep is >= a few microseconds even when a few ns are requested.
//   - SPIN : wait by executing cpu_relax() 'delay' times -> more precise.
//  The report compares the two strategies.
// ---------------------------------------------------------------------
enum class BackoffKind { SLEEP, SPIN };

template <BackoffKind Kind, unsigned MinDelay = 16, unsigned MaxDelay = 4096>
class Backoff {
    unsigned delay = MinDelay;
public:
    void pause() {
        if constexpr (Kind == BackoffKind::SLEEP) {
            std::this_thread::sleep_for(std::chrono::nanoseconds(delay));
        } else {
            for (unsigned i = 0; i < delay; ++i) cpu_relax();
        }
        if (delay < MaxDelay) delay *= 2;   // double the waiting time
    }
};

// =====================================================================
//  1) TAS (Test-And-Set)
// =====================================================================
class lock_tas {
    // alignas: place the variable at the start of its own cache line.
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        // exchange(true) = test-and-set: writes true and returns the OLD value.
        // If the old value is true -> the lock is held -> try again.
        // memory_order_acquire: no read/write of the critical section
        // can be moved by the CPU/compiler before the lock is acquired.
        while (locked.exchange(true, std::memory_order_acquire)) {
            cpu_relax();
        }
    }
    void release() {
        // memory_order_release: every operation of the critical section must
        // complete before another thread sees the lock as free.
        locked.store(false, std::memory_order_release);
    }
};

// =====================================================================
//  2) TAS + exponential backoff
//  Like lock_tas, but the while loop calls bo.pause()
//  with a 'Backoff<Kind> bo;' declared locally in acquire().
// =====================================================================
template <BackoffKind Kind>
class lock_tas_backoff {
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        // Backoff is LOCAL: each acquire() starts again from a small delay.
        Backoff<Kind> bo;
        // Like TAS, but on failure WAIT (the delay doubles each time)
        // instead of retrying immediately -> fewer writes to the lock's cache line
        // -> less bus traffic / cache invalidation between cores.
        while (locked.exchange(true, std::memory_order_acquire)) {
            bo.pause();
        }
    }
    void release() {
        locked.store(false, std::memory_order_release);
    }
};

// =====================================================================
//  3) TTAS (Test-and-Test-And-Set)
//  Idea (lecture 03a): before the exchange, spin with a plain load()
//  (READ only -> served from the core's own cached copy, no bus
//  traffic). Only when locked == false do we try exchange(true).
//    while (true) {
//        while (locked.load(std::memory_order_relaxed)) cpu_relax();
//        if (!locked.exchange(true, std::memory_order_acquire)) return;
//    }
// =====================================================================
class lock_ttas {
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        while (true) {
            // Step 1 "test": READ only. While the lock is held, each core reads
            // its own cached copy -> no bus traffic.
            // relaxed is enough: this is only a peek, the lock is not taken yet.
            while (locked.load(std::memory_order_relaxed)) {
                cpu_relax();
            }
            // Step 2 "test-and-set": try the exchange only when the lock looks free.
            // Old value false -> we acquired the lock.
            if (!locked.exchange(true, std::memory_order_acquire)) {
                return;
            }
            // Lost the race (another thread exchanged first) -> back to step 1.
        }
    }
    void release() {
        locked.store(false, std::memory_order_release);
    }
};

// TTAS + exponential backoff: when the exchange fails, call bo.pause()
template <BackoffKind Kind>
class lock_ttas_backoff {
    alignas(CACHE_LINE) std::atomic<bool> locked{false};
public:
    void acquire() {
        Backoff<Kind> bo;
        while (true) {
            while (locked.load(std::memory_order_relaxed)) {   // test
                cpu_relax();
            }
            if (!locked.exchange(true, std::memory_order_acquire)) {  // test-and-set
                return;
            }
            // a failed exchange = high contention (several threads saw the lock
            // free and rushed in together) -> back off, the delay doubles.
            bo.pause();
        }
    }
    void release() {
        locked.store(false, std::memory_order_release);
    }
};

// =====================================================================
//  4) MCS lock (Mellor-Crummey & Scott)
//  Each thread has its own node; the nodes form a FIFO queue.
//  Each thread spins on the 'locked' flag OF ITS OWN NODE -> no contention.
//  Because acquire()/release() take no parameters, each thread's node
//  is stored in a thread_local variable.
//
//  acquire():
//    me.next = nullptr; me.locked = true;
//    pred = tail.exchange(&me, acq_rel);     // append myself to the queue
//    if (pred != nullptr) {                  // someone is ahead of me
//        pred->next.store(&me, release);     // tell my predecessor
//        while (me.locked.load(acquire)) cpu_relax();  // wait to be called
//    }
//  release():
//    succ = me.next.load(acquire);
//    if (succ == nullptr) {
//        // nobody behind me: try to set tail = nullptr with a CAS
//        Node* expected = &me;
//        if (tail.compare_exchange_strong(expected, nullptr, acq_rel)) return;
//        // CAS failed = someone just enqueued but has not set next yet -> wait
//        while ((succ = me.next.load(acquire)) == nullptr) cpu_relax();
//    }
//    succ->locked.store(false, release);     // hand the lock to the successor
//
//  Note: thread_local static -> each thread can use only ONE lock_mcs
//  at a time (enough for this assignment; listed as a limitation in the report).
// =====================================================================
struct alignas(CACHE_LINE) mcs_node {      // one node of the MCS queue
    std::atomic<mcs_node*> next{nullptr};
    std::atomic<bool>      locked{false};
};

class lock_mcs {
    using Node = mcs_node;
    alignas(CACHE_LINE) std::atomic<Node*> tail{nullptr};
    static inline thread_local Node me;   // each thread's own node
public:
    void acquire() {
        // Prepare my node: nobody behind me yet, and I have to wait.
        me.next.store(nullptr, std::memory_order_relaxed);
        me.locked.store(true, std::memory_order_relaxed);

        // Append myself at the END of the queue (a single atomic operation) and
        // get the node ahead of me (pred).
        // acq_rel: release -> later arrivals see my node initialised;
        //          acquire -> I see pred's node initialised.
        Node* pred = tail.exchange(&me, std::memory_order_acq_rel);

        if (pred != nullptr) {
            // Someone is ahead: tell them I am behind them...
            pred->next.store(&me, std::memory_order_release);
            // ...then spin on MY OWN flag (own cache line)
            // -> waiting threads do not share one cache line as in TAS/TTAS.
            // acquire: when the lock is handed over, I see all writes made in
            // the predecessor's critical section.
            while (me.locked.load(std::memory_order_acquire)) {
                cpu_relax();
            }
        }
        // pred == nullptr: the queue was empty -> lock acquired immediately.
    }
    void release() {
        Node* succ = me.next.load(std::memory_order_acquire);
        if (succ == nullptr) {
            // Nobody behind me. Try to "close the queue": if tail is still me,
            // set tail = nullptr and finish.
            Node* expected = &me;
            if (tail.compare_exchange_strong(expected, nullptr,
                                             std::memory_order_acq_rel)) {
                return;
            }
            // CAS failed: a thread has exchanged tail (it is enqueued) but has
            // NOT yet set pred->next to its node. Wait until it does.
            while ((succ = me.next.load(std::memory_order_acquire)) == nullptr) {
                cpu_relax();
            }
        }
        // Hand the lock directly to the successor (FIFO).
        // release: the successor sees all writes made in the critical section.
        succ->locked.store(false, std::memory_order_release);
    }
};

// =====================================================================
//  Library locks used for COMPARISON (required by the assignment)
// =====================================================================
class lock_std {                       // C++ std::mutex
    std::mutex m;
public:
    void acquire() { m.lock(); }
    void release() { m.unlock(); }
};

#if defined(HAVE_PTHREAD)
class lock_pthread {                   // POSIX pthread_mutex
    pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
public:
    ~lock_pthread() { pthread_mutex_destroy(&m); }
    void acquire() { pthread_mutex_lock(&m); }
    void release() { pthread_mutex_unlock(&m); }
};
#endif

#ifdef _OPENMP
class lock_omp {                       // OpenMP lock (build with: make OMP=1)
    omp_lock_t l;
public:
    lock_omp()  { omp_init_lock(&l); }
    ~lock_omp() { omp_destroy_lock(&l); }
    void acquire() { omp_set_lock(&l); }
    void release() { omp_unset_lock(&l); }
};
#endif
