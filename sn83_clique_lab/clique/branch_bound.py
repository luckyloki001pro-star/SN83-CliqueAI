"""Bitset branch-and-bound maximum-clique search with optional ULM."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Sequence

from .bitset import bits_to_list
from .coloring import greedy_color_candidates
from .graph import BitsetGraph
from .greedy import extend_to_maximal, initial_incumbent
from .selective_ulm import (
    SelectiveULMConfig,
    SelectiveULMCounters,
    should_run_ulm,
)
from .ulm import ULMConfig, ULMReasoner
from .validation import is_clique, is_maximal_clique


class SolverVariant(str, Enum):
    BASELINE = "baseline"
    ULM = "ulm"
    SELECTIVE_ULM = "selective_ulm"


@dataclass
class SearchStats:
    search_nodes: int = 0
    coloring_calls: int = 0
    coloring_prunes: int = 0
    ulm_prunes: int = 0
    max_depth: int = 0
    incumbent_improvements: int = 0
    incumbent_times_ms: List[float] = field(default_factory=list)
    improvement_history: List[dict] = field(default_factory=list)
    best_from_phase: str = "none"
    deadline_reached: bool = False
    search_incomplete_at_deadline: bool = False
    response_deadline_violation: bool = False
    proven_optimal: bool = False
    initial_heuristic_ms: float = 0.0
    branch_bound_ms: float = 0.0
    ulm_time_ms: float = 0.0
    total_ms: float = 0.0
    selective: SelectiveULMCounters = field(default_factory=SelectiveULMCounters)


@dataclass
class BnBResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    stats: SearchStats
    variant: str


@dataclass
class BnBConfig:
    variant: SolverVariant = SolverVariant.BASELINE
    seed: int = 42
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    deadline_check_interval: int = 64
    greedy_restarts: int = 8
    ulm: ULMConfig = field(default_factory=ULMConfig)
    selective: SelectiveULMConfig = field(default_factory=SelectiveULMConfig)
    # Shared incumbent injection for fair A/B/C comparison.
    shared_incumbent: Optional[List[int]] = None


def solve_bnb(graph: BitsetGraph, config: BnBConfig) -> BnBResult:
    """Run bitset BnB with optional (selective) ULM upper bounds."""
    t_start = time.perf_counter()
    stats = SearchStats()
    deadline = t_start + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    hard_deadline = t_start + max(0.0, config.timeout_seconds)
    total_budget_ns = int(max(config.timeout_seconds, 0.0) * 1e9)

    # Initial incumbent
    t_h0 = time.perf_counter()
    if config.shared_incumbent is not None:
        best = list(config.shared_incumbent)
    else:
        best = initial_incumbent(graph, seed=config.seed, restarts=config.greedy_restarts)
    best = extend_to_maximal(graph, best)
    stats.initial_heuristic_ms = (time.perf_counter() - t_h0) * 1000.0
    stats.incumbent_improvements = 1
    stats.incumbent_times_ms.append(stats.initial_heuristic_ms)
    stats.improvement_history.append(
        {"time_ms": stats.initial_heuristic_ms, "size": float(len(best)), "phase": "greedy"}
    )
    stats.best_from_phase = "greedy"

    reasoner: Optional[ULMReasoner] = None
    use_ulm = config.variant in (SolverVariant.ULM, SolverVariant.SELECTIVE_ULM)
    selective = config.variant == SolverVariant.SELECTIVE_ULM
    if use_ulm:
        reasoner = ULMReasoner(graph, config.ulm)

    adj = graph.adjacency
    check_iv = max(1, config.deadline_check_interval)
    nodes_since_check = 0
    timed_out = False

    def timed_out_now() -> bool:
        nonlocal nodes_since_check, timed_out
        nodes_since_check += 1
        if nodes_since_check >= check_iv:
            nodes_since_check = 0
            if time.perf_counter() >= deadline:
                timed_out = True
                stats.deadline_reached = True
                stats.search_incomplete_at_deadline = True
                return True
        return timed_out

    def update_best(clique: List[int], phase: str = "bnb") -> None:
        nonlocal best
        if len(clique) > len(best):
            best = list(clique)
            stats.incumbent_improvements += 1
            now = (time.perf_counter() - t_start) * 1000.0
            stats.incumbent_times_ms.append(now)
            stats.improvement_history.append(
                {"time_ms": now, "size": float(len(best)), "phase": phase}
            )
            stats.best_from_phase = phase

    def expand(clique: List[int], candidates: int, depth: int) -> None:
        nonlocal timed_out
        if timed_out_now():
            return

        stats.search_nodes += 1
        if depth > stats.max_depth:
            stats.max_depth = depth

        if candidates == 0:
            update_best(clique, phase="bnb")
            return

        stats.coloring_calls += 1
        coloring = greedy_color_candidates(graph, candidates)
        color_bound = coloring.bound
        cur = len(clique)

        if cur + color_bound <= len(best):
            stats.coloring_prunes += 1
            return

        # Optional ULM tightening
        bound = color_bound
        if use_ulm and reasoner is not None and reasoner.available:
            gap = cur + color_bound - len(best)
            cand_count = candidates.bit_count()
            remaining_ms = max(0.0, (deadline - time.perf_counter()) * 1000.0)
            run = True
            if selective:
                run = should_run_ulm(
                    gap=gap,
                    candidate_count=cand_count,
                    remaining_ms=remaining_ms,
                    ulm_time_ns=reasoner.global_stats.time_ns,
                    total_budget_ns=total_budget_ns,
                    cfg=config.selective,
                    counters=stats.selective,
                )
            if run:
                ulm_res = reasoner.tighten_bound(coloring.color_classes, candidates)
                stats.ulm_time_ms = reasoner.global_stats.time_ns / 1e6
                if selective:
                    stats.selective.ulm_time_ns = reasoner.global_stats.time_ns
                    stats.selective.conflicts_found += ulm_res.stats.conflicts
                    stats.selective.bound_reductions += ulm_res.stats.bound_reductions
                if ulm_res.reduction > 0:
                    bound = ulm_res.bound
                    if cur + bound <= len(best):
                        stats.ulm_prunes += 1
                        if selective:
                            stats.selective.additional_prunes += 1
                        return

        if cur + bound <= len(best):
            stats.coloring_prunes += 1
            return

        # Branch vertices that can beat incumbent: color_number > need.
        need = len(best) - cur
        # Iterate high color first (reverse of ascending order).
        for v in reversed(coloring.vertex_order):
            if timed_out_now():
                return
            c = coloring.color_of[v]
            # After ULM, use min(c, bound) conservatively for pruning of
            # trailing branches. Color numbers remain valid individual
            # bounds; ULM only tightens the aggregate.
            if c <= need:
                # Remaining vertices have even smaller colors.
                break
            # Candidate may have been removed implicitly — check bit.
            if not ((candidates >> v) & 1):
                continue

            clique.append(v)
            new_cand = candidates & adj[v]
            # Remove v from candidates for siblings.
            candidates &= ~(1 << v)
            expand(clique, new_cand, depth + 1)
            clique.pop()
            if timed_out:
                return
            # Re-evaluate need after possible incumbent update.
            need = len(best) - cur
            if c <= need:
                break

    t_bnb0 = time.perf_counter()
    root_candidates = graph.all_vertices_mask()
    expand([], root_candidates, 0)
    stats.branch_bound_ms = (time.perf_counter() - t_bnb0) * 1000.0
    stats.proven_optimal = not stats.deadline_reached
    stats.total_ms = (time.perf_counter() - t_start) * 1000.0
    stats.response_deadline_violation = time.perf_counter() > hard_deadline

    # Ensure maximality of returned clique.
    best = extend_to_maximal(graph, best)
    valid = is_clique(graph, best)
    maximal = is_maximal_clique(graph, best) if valid else False

    if reasoner is not None:
        stats.ulm_time_ms = reasoner.global_stats.time_ns / 1e6

    return BnBResult(
        clique=sorted(best),
        clique_size=len(best),
        valid=valid,
        maximal=maximal,
        proven_optimal=stats.proven_optimal and valid,
        stats=stats,
        variant=config.variant.value,
    )
