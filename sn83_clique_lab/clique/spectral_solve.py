"""Phase-4A spectral solver entrypoints."""

from __future__ import annotations

import time
from typing import List

from .anchored_spectral import solve_anchored_spectral
from .competitive_search import CompetitiveConfig, CompetitiveVariant, solve_competitive
from .graph import BitsetGraph
from .spectral_clique import SpectralConfig, SpectralSolveResult, SpectralVariant, solve_global_spectral
from .validation import is_clique, is_maximal_clique


def solve_spectral(graph: BitsetGraph, config: SpectralConfig) -> SpectralSolveResult:
    t0 = time.perf_counter()
    soft = t0 + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    v = config.variant

    if v == SpectralVariant.GLOBAL_SPECTRAL:
        cfg = SpectralConfig(**{**config.__dict__, "use_ikls": False, "variant": v})
        return solve_global_spectral(graph, cfg, soft, t0)
    if v == SpectralVariant.GLOBAL_SPECTRAL_PLUS_IKLS:
        cfg = SpectralConfig(**{**config.__dict__, "use_ikls": True, "variant": v})
        return solve_global_spectral(graph, cfg, soft, t0)
    if v == SpectralVariant.ANCHORED_SPECTRAL:
        cfg = SpectralConfig(**{**config.__dict__, "use_ikls": False, "variant": v})
        return solve_anchored_spectral(graph, cfg, soft, t0)
    if v == SpectralVariant.ANCHORED_SPECTRAL_PLUS_IKLS:
        cfg = SpectralConfig(**{**config.__dict__, "use_ikls": True, "variant": v})
        return solve_anchored_spectral(graph, cfg, soft, t0)
    if v in (SpectralVariant.SPECTRAL_RECOVERY, SpectralVariant.SPECTRAL_PORTFOLIO):
        return _solve_spectral_portfolio(graph, config, soft, t0)
    raise ValueError(f"Unknown spectral variant: {v}")


def _solve_spectral_portfolio(
    graph: BitsetGraph,
    config: SpectralConfig,
    soft: float,
    t0: float,
) -> SpectralSolveResult:
    """Shared deadline: spectral discovery then adaptive portfolio on remainder."""
    frac = min(0.6, max(0.1, config.portfolio_spectral_frac))
    split = t0 + max(0.05, (soft - t0) * frac)

    # Phase 1: anchored spectral (usually better signal than global on dense ER-like graphs)
    cfg1 = SpectralConfig(
        variant=SpectralVariant.ANCHORED_SPECTRAL,
        timeout_seconds=max(0.1, split - t0),
        safety_margin_ms=0.0,
        seed=config.seed,
        spectral_max_time_fraction=0.5,
        lanczos_iters=config.lanczos_iters,
        n_eigens=config.n_eigens,
        pair_top_k=config.pair_top_k,
        use_ikls=False,
    )
    # soft deadline = split
    r1 = solve_anchored_spectral(graph, cfg1, split, t0)
    best = list(r1.clique)
    stats = r1.stats

    # Phase 2: adaptive portfolio on remaining time
    remaining = max(0.05, soft - time.perf_counter())
    cfg2 = CompetitiveConfig(
        variant=CompetitiveVariant.ADAPTIVE_PORTFOLIO,
        timeout_seconds=remaining,
        safety_margin_ms=50.0,
        seed=config.seed + 3,
    )
    r2 = solve_competitive(graph, cfg2)
    if r2.valid and r2.clique_size > len(best):
        best = list(r2.clique)
        ms = (time.perf_counter() - t0) * 1000.0
        stats.time_to_best_ms = ms
        stats.improvement_history.append({"time_ms": ms, "size": float(len(best))})
        stats.extras["portfolio_improved"] = True
    elif r2.valid and r2.clique_size == len(best) and not best:
        best = list(r2.clique)

    stats.extras["spectral_phase_ms"] = (split - t0) * 1000.0
    stats.extras["portfolio_phase_size"] = r2.clique_size
    stats.extras["anchored_phase_size"] = r1.clique_size

    valid = is_clique(graph, best)
    maximal = is_maximal_clique(graph, best) if valid else False
    hard = t0 + config.timeout_seconds
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    return SpectralSolveResult(
        clique=sorted(best),
        clique_size=len(best),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=config.variant.value,
        stats=stats,
        deadline_reached=time.perf_counter() >= soft,
        response_deadline_violation=time.perf_counter() > hard + 1e-3,
    )
