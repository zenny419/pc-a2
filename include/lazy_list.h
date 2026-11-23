#pragma once
#include <atomic>

template <class Key, class Lock>
class LazyList {
    struct Node {
        Key key{};
        std::atomic<Node*> next{nullptr};
        std::atomic<bool> marked{false};
        bool tail = false;
        Lock lock;
        Node* retired_next = nullptr;
    };

    Node head_;
    Node tail_;
    std::atomic<Node*> retired_{nullptr};

    static bool validate(Node* p, Node* c) {
        return !p->marked.load(std::memory_order_acquire) && !c->marked.load(std::memory_order_acquire) &&
               p->next.load(std::memory_order_acquire) == c;
    }

    void find(const Key& k, Node*& p, Node*& c) {
        p = &head_;
        c = p->next.load(std::memory_order_acquire);
        while (!c->tail && c->key < k) {
            p = c;
            c = c->next.load(std::memory_order_acquire);
        }
    }

    void retire(Node* n) {
        Node* old = retired_.load(std::memory_order_relaxed);
        do {
            n->retired_next = old;
        } while (!retired_.compare_exchange_weak(old, n, std::memory_order_release, std::memory_order_relaxed));
    }

public:
    LazyList() {
        tail_.tail = true;
        head_.next.store(&tail_);
    }

    LazyList(const LazyList&) = delete;
    LazyList& operator=(const LazyList&) = delete;

    ~LazyList() {
        Node* n = head_.next.load();
        while (!n->tail) {
            Node* nx = n->next.load();
            delete n;
            n = nx;
        }
        Node* r = retired_.load();
        while (r) {
            Node* nx = r->retired_next;
            delete r;
            r = nx;
        }
    }

    template <class F> void for_each(F f) {
        for (Node* n = head_.next.load(); !n->tail; n = n->next.load())
            if (!n->marked.load()) f(n->key);
    }

    bool contains(const Key& k) {
        Node* c = head_.next.load(std::memory_order_acquire);
        while (!c->tail && c->key < k) c = c->next.load(std::memory_order_acquire);
        return !c->tail && c->key == k && !c->marked.load(std::memory_order_acquire);
    }

    bool add(const Key& k) {
        while (true) {
            Node *p, *c;
            find(k, p, c);
            p->lock.acquire();
            c->lock.acquire();
            if (validate(p, c)) {
                bool ok = c->tail || !(c->key == k);
                if (ok) {
                    Node* n = new Node;
                    n->key = k;
                    n->next.store(c, std::memory_order_relaxed);
                    p->next.store(n, std::memory_order_release);
                }
                c->lock.release();
                p->lock.release();
                return ok;
            }
            c->lock.release();
            p->lock.release();
        }
    }

    bool remove(const Key& k) {
        while (true) {
            Node *p, *c;
            find(k, p, c);
            p->lock.acquire();
            c->lock.acquire();
            if (validate(p, c)) {
                bool ok = !c->tail && c->key == k;
                if (ok) {
                    c->marked.store(true, std::memory_order_release);
                    p->next.store(c->next.load(std::memory_order_acquire), std::memory_order_release);
                }
                c->lock.release();
                p->lock.release();
                if (ok) retire(c);
                return ok;
            }
            c->lock.release();
            p->lock.release();
        }
    }
};
