#pragma once
// =====================================================================
//  sorted_list.h — Part 2: concurrent set = sorted linked list
//  Two variants: CoarseList (one lock for the whole list) and FineList
//  (one lock per node, hand-over-hand). Locks come from Assignment 1's
//  lock.h (acquire/release).
//  Key: any type with operator< and operator== (Part 2 uses long,
//  Part 3 uses the pair (f, id) so nodes with equal f still get distinct keys).
//  The list has 2 sentinel nodes (head, tail), so no -inf/+inf values are needed.
// =====================================================================
#include "lock.h"
#include <optional>

template <class Key, class Lock>
class CoarseList {
    struct Node { Key key{}; Node* next = nullptr; bool tail = false; };
    Node head_, tail_;
    Lock lock_;
    // Find the pair (pred, curr) with pred.key < key <= curr.key. Call only while HOLDING the lock.
    void find(const Key& k, Node*& pred, Node*& curr) {
        pred = &head_; curr = head_.next;
        while (!curr->tail && curr->key < k) { pred = curr; curr = curr->next; }
    }
public:
    CoarseList() { tail_.tail = true; head_.next = &tail_; }
    ~CoarseList() { Node* n = head_.next; while (!n->tail) { Node* x = n->next; delete n; n = x; } }

    bool add(const Key& k) {
        lock_.acquire();
        Node *p, *c; find(k, p, c);
        bool ok = c->tail || !(c->key == k);
        if (ok) p->next = new Node{k, c};
        lock_.release();
        return ok;
    }
    bool remove(const Key& k) {
        lock_.acquire();
        Node *p, *c; find(k, p, c);
        bool ok = !c->tail && c->key == k;
        if (ok) { p->next = c->next; delete c; }
        lock_.release();
        return ok;
    }
    bool contains(const Key& k) {
        lock_.acquire();
        Node *p, *c; find(k, p, c);
        bool ok = !c->tail && c->key == k;
        lock_.release();
        return ok;
    }
    // Used by Part 3: take out and delete the SMALLEST element (head of the list).
    std::optional<Key> remove_min() {
        lock_.acquire();
        std::optional<Key> out;
        Node* c = head_.next;
        if (!c->tail) { out = c->key; head_.next = c->next; delete c; }
        lock_.release();
        return out;
    }
    // Call only when no other thread is running (used in tests).
    template <class F> void for_each(F f) { for (Node* n = head_.next; !n->tail; n = n->next) f(n->key); }
};

template <class Key, class Lock>
class FineList {
    struct Node { Key key{}; Node* next = nullptr; bool tail = false; Lock lock; };
    Node head_, tail_;
    // Hand-over-hand: always hold the locks of pred and curr; to move forward,
    // lock the next node FIRST, then release the trailing one -> nobody can slip in between.
    // On return: pred and curr are both LOCKED.
    void find(const Key& k, Node*& pred, Node*& curr) {
        pred = &head_; pred->lock.acquire();
        curr = pred->next; curr->lock.acquire();
        while (!curr->tail && curr->key < k) {
            pred->lock.release();
            pred = curr;
            curr = curr->next; curr->lock.acquire();
        }
    }
public:
    FineList() { tail_.tail = true; head_.next = &tail_; }
    ~FineList() { Node* n = head_.next; while (!n->tail) { Node* x = n->next; delete n; n = x; } }

    bool add(const Key& k) {
        Node *p, *c; find(k, p, c);
        bool ok = c->tail || !(c->key == k);
        if (ok) { Node* n = new Node; n->key = k; n->next = c; p->next = n; }
        c->lock.release(); p->lock.release();
        return ok;
    }
    bool remove(const Key& k) {
        Node *p, *c; find(k, p, c);
        bool ok = !c->tail && c->key == k;
        if (ok) p->next = c->next;
        c->lock.release(); p->lock.release();
        // Safe to delete: no thread can still hold a pointer to c, because reaching c
        // requires locking p first, and we held p while unlinking c.
        if (ok) delete c;
        return ok;
    }
    bool contains(const Key& k) {
        Node *p, *c; find(k, p, c);
        bool ok = !c->tail && c->key == k;
        c->lock.release(); p->lock.release();
        return ok;
    }
    std::optional<Key> remove_min() {
        Node* p = &head_; p->lock.acquire();
        Node* c = p->next; c->lock.acquire();
        std::optional<Key> out;
        if (!c->tail) { out = c->key; p->next = c->next; }
        c->lock.release(); p->lock.release();
        if (out) delete c;
        return out;
    }
    template <class F> void for_each(F f) { for (Node* n = head_.next; !n->tail; n = n->next) f(n->key); }
};
