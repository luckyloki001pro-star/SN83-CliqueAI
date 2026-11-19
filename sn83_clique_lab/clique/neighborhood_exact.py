"""Bounded exact maximum-clique *target* search inside an induced neighborhood.

Primary goal: find any clique of size >= target as fast as possible.
Uses greedy coloring as a safe upper bound (Tomita-style).

Statuses:
  TARGET_FOUND / PROVEN_NO_TARGET_IN_NEIGHBORHOOD / TIMEOUT / INVALID_INPUT
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence

from .bitset import bits_to_list, list_to_mask
from .coloring import greedy_color_candidates
from .graph import BitsetGraph


class ExactStatus(str, Enum):
    TARGET_FOUND = "TARGET_FOUND"
    PROVEN_NO_TARGET_IN_NEIGHBORHOOD = "PROVEN_NO_TARGET_IN_NEIGHBORHOOD"
    TIMEOUT = "TIMEOUT"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass
class ExactStats:
    search_nodes: int = 0
    recursive_calls: int = 0
    colorings: int = 0
    color_prunes: int = 0
    trivial_size_prunes: int = 0
    target_hits: int = 0
    completed_exhaustive: int = 0
    interrupted: int = 0
    maximum_depth: int = 0
    time_to_target_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class ExactResult:
    status: ExactStatus
    clique: List[int] = field(default_factory=list)
    clique_size: int = 0
    omega_if_proven: Optional[int] = None  # only when exhaustive without early target stop for max
    stats: ExactStats = field(default_factory=ExactStats)


def _degree_prune_mask(graph: BitsetGraph, cand: int, need: int) -> int:
    """Remove vertices with < need neighbors in cand (need = remaining clique slots - 1...
    For a t-clique, each vertex needs >= t-1 neighbors in H.
    When current_size=s and target=t, remaining need = t-s; a vertex needs >= (t-s)-1
    neighbors among other candidates to possibly finish? Safer iterative:
    for finding t-clique in cand alone: deg_H(v) >= t-1.
    """
    if need <= 1:
        return cand
    adj = graph.adjacency
    changed = True
    cur = cand
    while changed:
        changed = False
        tmp = cur
        while tmp:
            bit = tmp & -tmp
            v = bit.bit_length() - 1
            tmp ^= bit
            if (adj[v] & cur).bit_count() < need - 1:
                cur &= ~bit
                changed = True
    return cur


def search_target_clique(
    graph: BitsetGraph,
    candidate_mask: int,
    target_size: int,
    deadline: float,
    *,
    use_color_bound: bool = True,
    use_degree_prune: bool = True,
    order_mode: str = "color",
) -> ExactResult:
    """Find any clique of size >= target_size inside G[candidate_mask]."""
    t0 = time.perf_counter()
    stats = ExactStats()
    if target_size <= 0:
        return ExactResult(ExactStatus.INVALID_INPUT, stats=stats)
    if candidate_mask.bit_count() < target_size:
        stats.trivial_size_prunes += 1
        stats.total_ms = (time.perf_counter() - t0) * 1000.0
        stats.completed_exhaustive = 1
        return ExactResult(
            ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD,
            omega_if_proven=candidate_mask.bit_count(),
            stats=stats,
        )

    cand0 = candidate_mask
    if use_degree_prune:
        cand0 = _degree_prune_mask(graph, cand0, target_size)
        if cand0.bit_count() < target_size:
            stats.trivial_size_prunes += 1
            stats.total_ms = (time.perf_counter() - t0) * 1000.0
            stats.completed_exhaustive = 1
            return ExactResult(
                ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD,
                omega_if_proven=cand0.bit_count(),
                stats=stats,
            )

    # Pre-color whole candidate set for a global upper bound
    if use_color_bound:
        stats.colorings += 1
        col = greedy_color_candidates(graph, cand0)
        if col.bound < target_size:
            stats.color_prunes += 1
            stats.total_ms = (time.perf_counter() - t0) * 1000.0
            stats.completed_exhaustive = 1
            return ExactResult(
                ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD,
                omega_if_proven=col.bound,
                stats=stats,
            )

    found: List[int] = []
    timed_out = False
    adj = graph.adjacency

    def expand(clique: List[int], cand: int, depth: int) -> bool:
        """Return True if target found (stop)."""
        nonlocal timed_out, found
        stats.recursive_calls += 1
        stats.search_nodes += 1
        if depth > stats.maximum_depth:
            stats.maximum_depth = depth
        if time.perf_counter() >= deadline:
            timed_out = True
            stats.interrupted += 1
            return False
        cur = len(clique)
        if cur >= target_size:
            found = list(clique)
            stats.target_hits += 1
            stats.time_to_target_ms = (time.perf_counter() - t0) * 1000.0
            return True
        if cand == 0:
            return False
        if cur + cand.bit_count() < target_size:
            stats.trivial_size_prunes += 1
            return False

        # Color bound on remaining candidates
        if use_color_bound:
            stats.colorings += 1
            coloring = greedy_color_candidates(graph, cand)
            if cur + coloring.bound < target_size:
                stats.color_prunes += 1
                return False
            order = list(reversed(coloring.vertex_order))
        else:
            verts = bits_to_list(cand)
            if order_mode == "degree":
                verts.sort(key=lambda v: -((cand & adj[v]).bit_count()))
            else:
                verts.sort(key=lambda v: -((cand & adj[v]).bit_count()))
            order = verts

        # Branch
        remaining = cand
        for v in order:
            if timed_out:
                return False
            if not ((remaining >> v) & 1):
                continue
            # Tomita-style: if color of v too small to beat target, can stop
            if use_color_bound:
                # color_of is 1-based; remaining UB when taking v is roughly color number
                cnum = coloring.color_of[v]
                if cur + cnum < target_size:
                    # all remaining in this ordering have <= cnum
                    stats.color_prunes += 1
                    break
            clique.append(v)
            nxt = remaining & adj[v]
            if use_degree_prune and (target_size - (cur + 1)) > 0:
                nxt = _degree_prune_mask(graph, nxt, target_size - (cur + 1))
            if expand(clique, nxt, depth + 1):
                return True
            clique.pop()
            if timed_out:
                return False
            remaining &= ~(1 << v)
        return False

    hit = expand([], cand0, 0)
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    if hit and found:
        return ExactResult(
            ExactStatus.TARGET_FOUND,
            clique=sorted(found),
            clique_size=len(found),
            stats=stats,
        )
    if timed_out:
        return ExactResult(ExactStatus.TIMEOUT, stats=stats)
    stats.completed_exhaustive = 1
    return ExactResult(
        ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD,
        omega_if_proven=target_size - 1,  # no clique of target_size exists
        stats=stats,
    )


def search_max_clique_in_mask(
    graph: BitsetGraph,
    candidate_mask: int,
    deadline: float,
    *,
    use_color_bound: bool = True,
) -> ExactResult:
    """Exhaustive max-clique in induced mask (for small tests / optional enum)."""
    t0 = time.perf_counter()
    stats = ExactStats()
    if candidate_mask == 0:
        stats.completed_exhaustive = 1
        stats.total_ms = 0.0
        return ExactResult(ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD, omega_if_proven=0, stats=stats)

    best: List[int] = []
    timed_out = False
    adj = graph.adjacency

    def expand(clique: List[int], cand: int, depth: int) -> None:
        nonlocal timed_out, best
        stats.recursive_calls += 1
        stats.search_nodes += 1
        if depth > stats.maximum_depth:
            stats.maximum_depth = depth
        if time.perf_counter() >= deadline:
            timed_out = True
            stats.interrupted += 1
            return
        if cand == 0:
            if len(clique) > len(best):
                best = list(clique)
            return
        if use_color_bound:
            stats.colorings += 1
            coloring = greedy_color_candidates(graph, cand)
            if len(clique) + coloring.bound <= len(best):
                stats.color_prunes += 1
                return
            order = list(reversed(coloring.vertex_order))
        else:
            order = bits_to_list(cand)
            order.sort(key=lambda v: -((cand & adj[v]).bit_count()))

        remaining = cand
        for v in order:
            if timed_out:
                return
            if not ((remaining >> v) & 1):
                continue
            if use_color_bound:
                cnum = coloring.color_of[v]
                if len(clique) + cnum <= len(best):
                    stats.color_prunes += 1
                    break
            clique.append(v)
            expand(clique, remaining & adj[v], depth + 1)
            clique.pop()
            if timed_out:
                return
            remaining &= ~(1 << v)

    expand([], candidate_mask, 0)
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    if timed_out:
        # still return best-so-far but TIMEOUT
        return ExactResult(
            ExactStatus.TIMEOUT,
            clique=sorted(best),
            clique_size=len(best),
            stats=stats,
        )
    stats.completed_exhaustive = 1
    return ExactResult(
        ExactStatus.TARGET_FOUND if best else ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD,
        clique=sorted(best),
        clique_size=len(best),
        omega_if_proven=len(best),
        stats=stats,
    )
