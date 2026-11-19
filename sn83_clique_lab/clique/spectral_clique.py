"""Spectral-seeded clique construction (Phase 4A).

Simplified pure-Python heuristic — not an exact paper reproduction.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .bitset import bits_to_list, list_to_mask
from .competitive_search import CompetitiveConfig, CompetitiveVariant, solve_competitive
from .graph import BitsetGraph
from .greedy import extend_to_maximal, greedy_maximal_from_start
from .spectral_rank import combined_scores, lanczos_centered
from .validation import is_clique, is_maximal_clique


class SpectralVariant(str, Enum):
    GLOBAL_SPECTRAL = "global_spectral"
    GLOBAL_SPECTRAL_PLUS_IKLS = "global_spectral_plus_ikls"
    ANCHORED_SPECTRAL = "anchored_spectral"
    ANCHORED_SPECTRAL_PLUS_IKLS = "anchored_spectral_plus_ikls"
    SPECTRAL_PORTFOLIO = "spectral_portfolio"
    SPECTRAL_RECOVERY = "spectral_recovery"


@dataclass
class SpectralConfig:
    variant: SpectralVariant = SpectralVariant.GLOBAL_SPECTRAL
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    seed: int = 42
    spectral_max_time_fraction: float = 0.15
    lanczos_iters: int = 16
    n_eigens: int = 3
    alpha: float = 0.6
    beta: float = 0.4
    n_starts: int = 48
    purify_multipliers: Tuple[float, ...] = (1.5, 2.0, 3.0)
    pair_top_k: int = 32
    pair_sample: int = 2500
    use_ikls: bool = False
    portfolio_spectral_frac: float = 0.35


@dataclass
class SpectralSolveStats:
    constructions: int = 0
    valid_cliques: int = 0
    spectral_ms: float = 0.0
    construction_ms: float = 0.0
    total_ms: float = 0.0
    ikls_calls: int = 0
    ikls_improvements: int = 0
    lanczos_iters: int = 0
    residuals: List[float] = field(default_factory=list)
    eigenvalues: List[float] = field(default_factory=list)
    time_to_first_ms: float = 0.0
    time_to_best_ms: float = 0.0
    improvement_history: List[Dict[str, float]] = field(default_factory=list)
    pair_starts: int = 0
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpectralSolveResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    variant: str
    stats: SpectralSolveStats
    deadline_reached: bool = False
    response_deadline_violation: bool = False


def greedy_from_order(
    graph: BitsetGraph,
    order: Sequence[int],
    start_v: int,
) -> List[int]:
    """Exact intersection construction guided by a vertex ordering."""
    if not (0 <= start_v < graph.n):
        return []
    rank = {v: i for i, v in enumerate(order)}
    clique = [start_v]
    cand = graph.adjacency[start_v]
    while cand:
        best = None
        best_r = 10**18
        for v in bits_to_list(cand):
            r = rank.get(v, 10**18)
            if r < best_r:
                best_r = r
                best = v
        if best is None:
            break
        clique.append(best)
        cand &= graph.adjacency[best]
    return sorted(extend_to_maximal(graph, clique))


def purify_candidates(graph: BitsetGraph, candidates: Sequence[int], keep: int) -> List[int]:
    if keep >= len(candidates):
        return list(candidates)
    mask = list_to_mask(candidates)
    scored = [((graph.adjacency[v] & mask).bit_count(), v) for v in candidates]
    scored.sort(reverse=True)
    return [v for _, v in scored[:keep]]


def _consider(
    graph: BitsetGraph,
    clique: Sequence[int],
    best: List[int],
    hist: List[Dict[str, float]],
    stats: SpectralSolveStats,
    t0: float,
) -> List[int]:
    stats.constructions += 1
    if not clique or not is_clique(graph, clique):
        return best
    clique = extend_to_maximal(graph, list(clique))
    if not is_maximal_clique(graph, clique):
        return best
    stats.valid_cliques += 1
    if len(clique) > len(best):
        best = sorted(clique)
        ms = (time.perf_counter() - t0) * 1000.0
        if not hist:
            stats.time_to_first_ms = ms
        stats.time_to_best_ms = ms
        hist.append({"time_ms": ms, "size": float(len(best))})
    return best


def build_from_scores(
    graph: BitsetGraph,
    scores: Sequence[float],
    rng: random.Random,
    n_starts: int,
    soft_deadline: float,
    t0: float,
    stats: SpectralSolveStats,
    best: List[int],
    hist: List[Dict[str, float]],
    alpha: float,
    beta: float,
    purify_mults: Sequence[float],
) -> List[int]:
    n = graph.n
    degrees = graph.degrees()
    order_abs = sorted(range(n), key=lambda i: abs(scores[i]), reverse=True)
    order_pos = sorted(range(n), key=lambda i: scores[i], reverse=True)
    order_neg = sorted(range(n), key=lambda i: scores[i])
    comb = combined_scores(scores, degrees, alpha=alpha, beta=beta, use_abs=True)
    order_comb = sorted(range(n), key=lambda i: comb[i], reverse=True)
    orders: List[List[int]] = [order_abs, order_pos, order_neg, order_comb]
    for _ in range(min(4, max(1, n_starts // 8))):
        jitter = [comb[i] + 0.05 * rng.random() for i in range(n)]
        orders.append(sorted(range(n), key=lambda i: jitter[i], reverse=True))

    per = max(1, n_starts // max(1, len(orders)))
    starts = 0
    for order in orders:
        for start in order[:per]:
            if time.perf_counter() >= soft_deadline or starts >= n_starts:
                break
            tc = time.perf_counter()
            clique = greedy_from_order(graph, order, start)
            stats.construction_ms += (time.perf_counter() - tc) * 1000.0
            best = _consider(graph, clique, best, hist, stats, t0)
            starts += 1
        if time.perf_counter() >= soft_deadline or starts >= n_starts:
            break

    if best and time.perf_counter() < soft_deadline:
        base = max(len(best), 3)
        top = order_comb[: min(n, max(base * 3, 24))]
        for mult in purify_mults:
            if time.perf_counter() >= soft_deadline:
                break
            keep = max(base, int(mult * base))
            refined = purify_candidates(graph, top[: max(keep, len(top))], keep)
            sub_order = sorted(refined, key=lambda v: abs(scores[v]), reverse=True)
            for s in sub_order[:6]:
                if time.perf_counter() >= soft_deadline:
                    break
                clique = greedy_from_order(graph, sub_order, s)
                best = _consider(graph, clique, best, hist, stats, t0)
    return best


def _maybe_ikls(
    graph: BitsetGraph,
    best: List[int],
    cfg: SpectralConfig,
    soft_deadline: float,
    t0: float,
    stats: SpectralSolveStats,
    hist: List[Dict[str, float]],
) -> List[int]:
    if not cfg.use_ikls or not best or time.perf_counter() >= soft_deadline:
        return best
    remaining = max(0.05, soft_deadline - time.perf_counter())
    ik = CompetitiveConfig(
        variant=CompetitiveVariant.IKLS_VARIABLE_DEPTH,
        timeout_seconds=remaining,
        safety_margin_ms=50.0,
        seed=cfg.seed + 17,
    )
    stats.ikls_calls += 1
    before = len(best)
    raw = solve_competitive(graph, ik)
    if raw.valid and raw.clique_size > before:
        best = list(raw.clique)
        stats.ikls_improvements += 1
        ms = (time.perf_counter() - t0) * 1000.0
        stats.time_to_best_ms = ms
        hist.append({"time_ms": ms, "size": float(len(best))})
    elif raw.valid and raw.clique_size == before and raw.clique:
        # keep diverse equal-sized option if any
        pass
    return best


def solve_global_spectral(
    graph: BitsetGraph,
    cfg: SpectralConfig,
    soft_deadline: float,
    t0: float,
) -> SpectralSolveResult:
    rng = random.Random(cfg.seed)
    stats = SpectralSolveStats()
    hist: List[Dict[str, float]] = []
    best: List[int] = []

    hubs = sorted(range(graph.n), key=lambda i: graph.degree(i), reverse=True)[:12]
    for v in hubs:
        if time.perf_counter() >= soft_deadline:
            break
        c = greedy_maximal_from_start(graph, v)
        best = _consider(graph, c, best, hist, stats, t0)

    spectral_deadline = min(soft_deadline, t0 + max(0.05, cfg.timeout_seconds * cfg.spectral_max_time_fraction))
    spec = lanczos_centered(
        graph,
        max_iter=cfg.lanczos_iters,
        n_eigs=cfg.n_eigens,
        deadline=spectral_deadline,
    )
    stats.spectral_ms = spec.total_ms
    stats.lanczos_iters = spec.iterations
    stats.residuals = list(spec.residuals)
    stats.eigenvalues = list(spec.eigenvalues)
    stats.extras["spectral_stopped_early"] = bool(spec.stopped_early)
    stats.extras["matvec_ms"] = spec.matvec_ms

    for vec in (spec.eigenvectors or [[0.0] * graph.n])[: cfg.n_eigens]:
        if time.perf_counter() >= soft_deadline:
            break
        best = build_from_scores(
            graph,
            vec,
            rng,
            cfg.n_starts,
            soft_deadline,
            t0,
            stats,
            best,
            hist,
            cfg.alpha,
            cfg.beta,
            cfg.purify_multipliers,
        )

    best = _maybe_ikls(graph, best, cfg, soft_deadline, t0, stats, hist)
    best = sorted(extend_to_maximal(graph, best)) if best else []
    valid = is_clique(graph, best)
    maximal = is_maximal_clique(graph, best) if valid else False
    hard = t0 + cfg.timeout_seconds
    stats.improvement_history = hist
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    return SpectralSolveResult(
        clique=best,
        clique_size=len(best),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=cfg.variant.value,
        stats=stats,
        deadline_reached=time.perf_counter() >= soft_deadline,
        response_deadline_violation=time.perf_counter() > hard + 1e-3,
    )
