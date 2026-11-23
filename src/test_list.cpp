// =====================================================================
//  test_list.cpp — Part 2: correctness test for the concurrent sorted list
//  [Frame 1] Properties: (S) after the parallel run, the list = exactly the expected
//            set of elements, strictly increasing, no duplicates; (L) no deadlock.
//  [Frame 2] Method: each thread only adds/removes its "own" keys
//            (key % T == tid), but the keys are INTERLEAVED in the list, so threads
//            keep modifying neighbouring nodes. Each thread keeps a sequential
//            std::set as a shadow. At the end: list must == union of all shadows.
//            Every returned value (true/false) must also match the shadow.
//            Negative control: an UNLOCKED list must be caught by the test.
//  Run: ./test_list <threads> <ops_per_thread> <repeats>
// =====================================================================
#include "sorted_list.h"
#include "test_util.h"
#include <cstdio>
#include <cstdlib>
#include <random>
#include <set>
#include <thread>
#include <vector>

class RacyList {
    struct Node { long key; Node* next; bool tail; };
    Node tail_{0, nullptr, true}, head_{0, &tail_, false};
    lock_std m_;
    void find(long k, Node*& p, Node*& c) {
        m_.acquire();
        p = &head_; c = head_.next;
        while (!c->tail && c->key < k) { p = c; c = c->next; }
        m_.release();
        std::this_thread::yield();                   // widen the race window
    }
public:
    bool add(long k) { Node *p, *c; find(k, p, c); m_.acquire();
        bool ok = c->tail || c->key != k; if (ok) p->next = new Node{k, c, false}; m_.release(); return ok; }
    bool remove(long k) { Node *p, *c; find(k, p, c); m_.acquire();
        bool ok = !c->tail && c->key == k; if (ok) p->next = c->next; m_.release(); return ok; }
    bool contains(long k) { Node *p, *c; find(k, p, c); return !c->tail && c->key == k; }
    template <class F> void for_each(F f) { for (Node* n = head_.next; !n->tail; n = n->next) f(n->key); }
};

template <class List>
TestResult run_once(int T, int ops, unsigned seed) {
    List list;
    std::vector<std::set<long>> shadow(T);
    std::vector<int> mismatch(T, 0);
    const long RANGE = 512;                      // few keys -> high contention
    std::vector<std::thread> th;
    for (int t = 0; t < T; ++t)
        th.emplace_back([&, t] {
            std::mt19937 rng(seed * 131 + t);
            for (int i = 0; i < ops; ++i) {
                long k = (long)(rng() % RANGE) * T + t;   // a key owned by thread t
                int op = rng() % 3;
                bool got, exp;
                if (op == 0)      { got = list.add(k);      exp = shadow[t].insert(k).second; }
                else if (op == 1) { got = list.remove(k);   exp = shadow[t].erase(k) == 1; }
                else              { got = list.contains(k); exp = shadow[t].count(k) == 1; }
                if (got != exp) ++mismatch[t];
            }
        });
    for (auto& x : th) x.join();

    TestResult r;
    std::set<long> expected;
    for (auto& s : shadow) expected.insert(s.begin(), s.end());
    std::vector<long> got;
    list.for_each([&](long k) { got.push_back(k); });
    long bad_ret = 0; for (int m : mismatch) bad_ret += m;
    bool sorted = true;
    for (size_t i = 1; i < got.size(); ++i) if (!(got[i - 1] < got[i])) sorted = false;
    r.observed = (long)got.size(); r.expected = (long)expected.size();
    if (bad_ret)                                   { r.ok = false; r.why = "return value != shadow"; }
    else if (!sorted)                              { r.ok = false; r.why = "not strictly increasing"; }
    else if (std::vector<long>(expected.begin(), expected.end()) != got)
                                                   { r.ok = false; r.why = "final set != shadow union"; }
    return r;
}

template <class List>
bool test(const char* name, bool control, int T, int ops, int reps, Watchdog& wd) {
    int pass = 0; TestResult first_bad;
    wd.arm(name, 60);
    for (int i = 0; i < reps; ++i) {
        TestResult r = run_once<List>(T, ops, i + 1);
        if (r.ok) ++pass; else if (first_bad.ok) first_bad = r;
    }
    wd.disarm();
    return print_row(name, control, pass, reps, first_bad);
}

int main(int argc, char** argv) {
    int T    = argc > 1 ? std::atoi(argv[1]) : 4;
    int ops  = argc > 2 ? std::atoi(argv[2]) : 20000;
    int reps = argc > 3 ? std::atoi(argv[3]) : 5;
    std::printf("[Frame 3 – Configuration] threads=%d ops/thread=%d repeats=%d\n", T, ops, reps);
    Watchdog wd;
    bool all = true;
    all &= test<CoarseList<long, lock_ttas>>("coarse+ttas", false, T, ops, reps, wd);
    all &= test<CoarseList<long, lock_std>>("coarse+std", false, T, ops, reps, wd);
    all &= test<FineList<long, lock_ttas>>("fine+ttas", false, T, ops, reps, wd);
    all &= test<FineList<long, lock_std>>("fine+std", false, T, ops, reps, wd);
// #endif
    // The racy list has an intentional data race (negative control).
    // Under ThreadSanitizer it would always be reported, so skip it there;
    // the normal build (make test) still runs it.
#if !defined(__SANITIZE_THREAD__)
    all &= test<RacyList>("racy (control)", true, T, ops, reps, wd);
#else
    std::printf("racy (control): skipped under ThreadSanitizer (intentional race)\n");
#endif
    std::printf(all ? "ALL AS EXPECTED\n" : "SOMETHING FAILED\n");
    return all ? 0 : 1;
}
