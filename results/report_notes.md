# Report notes

## Issues found in the given A* pseudocode and notebook

| Where | Issue | Fix |
|---|---|---|
| Slides 9-10 | u is never removed from O | pop u from the heap |
| Slides 9-10 | `Prev` and `Pred` used for the same array | one array `prev` |
| Slides 9-10 | no "no path" case when O becomes empty | return infinity |
| Slides 9-10 | skipping nodes in C is only correct for a consistent h | straight-line h is consistent |
| Notebook | `f = g_score + h_score` of the current node | f of the neighbour |
| Notebook | `t` accumulated across neighbours | compute t per neighbour |
| Notebook | default heuristic missing the `graph` argument | pass all arguments |
| Notebook | `speeds[floor(t)]` fails when t >= 20 | wrap with `% len(speeds)` |
| Notebook | returns f instead of the cost | return g |
| Notebook | h divides by the current speed, not admissible | divide by the max speed |

## Part 1(b) uncertain h
- Shared per-minute noise gives gap = 0 by construction: travel time is monotone in distance,
  so the fastest path is always the shortest one.
- Per-edge noise, 8 random pairs: mean plan 0.532 / 1.293 min (avg / max gap),
  robust 0.602 / 1.249. Robust has a smaller max gap in only 3/8 pairs:
  assuming every edge is slow at once is too pessimistic because independent edge noise averages out.
