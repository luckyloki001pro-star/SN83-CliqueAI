"""Greedy maximal-clique construction with seeded restarts."""

from __future__ import annotations

import random
from typing import List, Sequence, Tuple

from .bitset import bits_to_list, iter_bits
from .graph import BitsetGraph


def greedy_maximal_from_start(
    graph: BitsetGraph,
    start: int,
    candidates: int | None = None,
    order_by_degree: bool = True,
) -> List[int]:
    """Build a maximal clique starting from ``start``."""
    adj = graph.adjacency
    if candidates is None:
        cand = adj[start]
    else:
        cand = candidates & adj[start]
    clique = [start]
    degrees = graph.degrees() if order_by_degree else None

    while cand:
        if order_by_degree and degrees is not None:
            best_v = -1
            best_score = -1
            tmp = cand
            while tmp:
                bit = tmp & -tmp
                v = bit.bit_length() - 1
                tmp ^= bit
                # Prefer high residual degree inside candidates.
                score = (cand & adj[v]).bit_count()
                if score > best_score or (score == best_score and degrees[v] > degrees[best_v]):
                    best_score = score
                    best_v = v
            v = best_v
        else:
            v = (cand & -cand).bit_length() - 1
        clique.append(v)
        cand &= adj[v]
    return clique


def extend_to_maximal(graph: BitsetGraph, clique: Sequence[int]) -> List[int]:
    """Greedily extend a clique to maximality."""
    if not clique:
        # Pick highest-degree vertex then extend.
        degrees = graph.degrees()
        start = max(range(graph.n), key=lambda v: degrees[v]) if graph.n else -1
        if start < 0:
            return []
        return greedy_maximal_from_start(graph, start)

    adj = graph.adjacency
    common = graph.all_vertices_mask()
    for v in clique:
        common &= adj[v]
    out = list(clique)
    while common:
        # Choose vertex maximizing residual common neighbors.
        best_v = -1
        best_score = -1
        tmp = common
        while tmp:
            bit = tmp & -tmp
            v = bit.bit_length() - 1
            tmp ^= bit
            score = (common & adj[v]).bit_count()
            if score > best_score:
                best_score = score
                best_v = v
        out.append(best_v)
        common &= adj[best_v]
    return out


def multi_start_greedy(
    graph: BitsetGraph,
    seed: int = 42,
    restarts: int = 8,
) -> Tuple[List[int], float]:
    """
    Run multiple seeded greedy constructions.

    Returns (best_clique, elapsed_seconds_placeholder_caller_times).
    All solvers must share this incumbent for a given (graph, seed).
    """
    if graph.n == 0:
        return [], 0.0

    rng = random.Random(seed)
    degrees = graph.degrees()
    # Deterministic priority starts: high degree first.
    ranked = sorted(range(graph.n), key=lambda v: (-degrees[v], v))
    starts = ranked[: min(len(ranked), max(1, restarts // 2))]
    # Remaining starts are seeded random vertices.
    remaining = [v for v in ranked if v not in starts]
    rng.shuffle(remaining)
    starts.extend(remaining[: max(0, restarts - len(starts))])

    best: List[int] = []
    for s in starts:
        clique = greedy_maximal_from_start(graph, s)
        if len(clique) > len(best):
            best = clique
        # Also try a random-order greedy from the same start pool.
        cand = graph.adjacency[s]
        clique2 = [s]
        order = bits_to_list(cand)
        rng.shuffle(order)
        for v in order:
            # Feasible if adjacent to all current clique members.
            ok = True
            for u in clique2:
                if not ((graph.adjacency[u] >> v) & 1):
                    ok = False
                    break
            if ok:
                clique2.append(v)
        clique2 = extend_to_maximal(graph, clique2)
        if len(clique2) > len(best):
            best = clique2

    if not best:
        best = [0] if graph.n else []
        best = extend_to_maximal(graph, best)
    return best, 0.0


def initial_incumbent(graph: BitsetGraph, seed: int = 42, restarts: int = 8) -> List[int]:
    clique, _ = multi_start_greedy(graph, seed=seed, restarts=restarts)
    return sorted(clique)
