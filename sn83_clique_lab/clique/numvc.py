"""NuMVC-inspired minimum vertex cover on the complement graph (Phase 5B).

Inspired by Cai, Su, Luo & Sattar, JAIR 2013 / arXiv:1402.0584.
Not a line-by-line port of the reference C implementation.

Variants:
  numvc_complement   — B1 reference-inspired
  numvc_diversified  — B2 BMS + restarts + elite retention
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .bitset import bits_to_list, full_mask, list_to_mask
from .complement_graph import build_complement
from .graph import BitsetGraph
from .greedy import extend_to_maximal
from .numvc_diversity import CliquePool
from .numvc_state import NuMVCState
from .numvc_weights import EdgeWeights
from .validation import is_clique, is_maximal_clique


class NuMVCVariant(str, Enum):
    NUMVC_COMPLEMENT = "numvc_complement"
    NUMVC_DIVERSIFIED = "numvc_diversified"
    NUMVC_PLUS_REVO = "numvc_plus_revo"  # hybrid wrapper elsewhere


@dataclass
class NuMVCConfig:
    variant: NuMVCVariant = NuMVCVariant.NUMVC_COMPLEMENT
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    seed: int = 42
    gamma: Optional[float] = None  # default 0.5*|V|
    rho: float = 0.3
    enable_weights: bool = True
    enable_forgetting: bool = True
    enable_conf_change: bool = True
    bms_sample: int = 0  # 0 = full scan; >0 for BMS on removal
    restart_every_steps: int = 0  # diversified only
    elite_capacity: int = 32
    deadline_check_every: int = 64
    # Optional low-overhead incumbent callback (size improvements only).
    on_incumbent: Optional[Callable[..., None]] = None


@dataclass
class NuMVCStats:
    constructions: int = 0
    search_steps: int = 0
    cover_removals: int = 0
    cover_additions: int = 0
    valid_cover_discoveries: int = 0
    best_cover_improvements: int = 0
    forgetting_events: int = 0
    weight_increments: int = 0
    prevented_readditions: int = 0
    conf_updates: int = 0
    restarts: int = 0
    complement_ms: float = 0.0
    init_cover_ms: float = 0.0
    local_search_ms: float = 0.0
    weight_update_ms: float = 0.0
    conversion_ms: float = 0.0
    total_ms: float = 0.0
    time_to_first_ms: float = 0.0
    time_to_best_ms: float = 0.0
    best_cover_size: int = 0
    complement_edge_count: int = 0
    complement_density: float = 0.0
    steps_per_second: float = 0.0
    mean_edge_weight: float = 0.0
    max_edge_weight: int = 0
    improvement_history: List[Dict[str, float]] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NuMVCResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    variant: str
    stats: NuMVCStats
    deadline_reached: bool = False
    response_deadline_violation: bool = False
    best_cover_size: int = 0


def _cover_to_maximal_clique(graph: BitsetGraph, cover_mask: int) -> List[int]:
    """S = V\\C as independent set in H = clique in G; extend to maximal in G."""
    s_mask = full_mask(graph.n) & ~cover_mask
    s = bits_to_list(s_mask)
    if not s:
        # empty IS — extend from empty → greedy maximal
        return sorted(extend_to_maximal(graph, []))
    return sorted(extend_to_maximal(graph, s))


def solve_numvc(graph: BitsetGraph, config: NuMVCConfig) -> NuMVCResult:
    t0 = time.perf_counter()
    soft = t0 + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    hard = t0 + config.timeout_seconds
    stats = NuMVCStats()
    rng = random.Random(config.seed)
    elite = CliquePool(config.elite_capacity)
    on_inc = config.on_incumbent

    def _emit(clique: List[int], elapsed_ms: float) -> None:
        if on_inc is None:
            return
        on_inc(config.variant.value, clique, len(clique), elapsed_ms, config.seed)

    diversified = config.variant == NuMVCVariant.NUMVC_DIVERSIFIED
    bms = config.bms_sample if diversified else (config.bms_sample or 0)
    if diversified and bms <= 0:
        bms = 50  # default BMS for diversified
    restart_every = config.restart_every_steps if diversified else 0
    if diversified and restart_every <= 0:
        restart_every = 200_000

    # --- complement ---
    tc = time.perf_counter()
    comp = build_complement(graph)
    stats.complement_ms = (time.perf_counter() - tc) * 1000.0
    stats.complement_edge_count = comp.complement_edge_count
    stats.complement_density = comp.complement_density

    # Special case: no complement edges → V is a clique
    if comp.complement_edge_count == 0:
        clique = list(range(graph.n))
        stats.total_ms = (time.perf_counter() - t0) * 1000.0
        stats.time_to_first_ms = stats.total_ms
        stats.time_to_best_ms = stats.total_ms
        stats.best_cover_size = 0
        _emit(clique, stats.total_ms)
        valid = is_clique(graph, clique) if clique else True
        return NuMVCResult(
            clique=clique,
            clique_size=len(clique),
            valid=valid,
            maximal=is_maximal_clique(graph, clique) if clique else True,
            proven_optimal=True,
            variant=config.variant.value,
            stats=stats,
            deadline_reached=False,
            response_deadline_violation=time.perf_counter() > hard,
            best_cover_size=0,
        )

    weights = EdgeWeights.create(
        comp,
        gamma=config.gamma,
        rho=config.rho,
        enable_forgetting=config.enable_forgetting,
        enable_weights=config.enable_weights,
    )
    state = NuMVCState.create(comp, weights, use_conf_change=config.enable_conf_change)

    ti = time.perf_counter()
    state.greedy_construct(rng)
    stats.init_cover_ms = (time.perf_counter() - ti) * 1000.0
    stats.constructions += 1

    best_cover_mask = state.cover_mask()
    best_cover_size = state.cover_size
    stats.best_cover_size = best_cover_size
    stats.valid_cover_discoveries += 1
    stats.best_cover_improvements += 1

    # Publish initial clique
    tv = time.perf_counter()
    best_clique = _cover_to_maximal_clique(graph, best_cover_mask)
    stats.conversion_ms += (time.perf_counter() - tv) * 1000.0
    now_ms = (time.perf_counter() - t0) * 1000.0
    stats.time_to_first_ms = now_ms
    stats.time_to_best_ms = now_ms
    stats.improvement_history.append({"time_ms": now_ms, "size": float(len(best_clique))})
    elite.add(best_clique, discovery_time_ms=now_ms, variant=config.variant.value, seed=config.seed)
    _emit(best_clique, now_ms)

    # --- local search ---
    tl = time.perf_counter()
    check_every = max(1, config.deadline_check_every)
    steps_since_restart = 0

    while time.perf_counter() < soft:
        stats.search_steps += 1
        steps_since_restart += 1
        if stats.search_steps % check_every == 0 and time.perf_counter() >= soft:
            break

        if state.is_valid_cover():
            stats.valid_cover_discoveries += 1
            if state.cover_size < best_cover_size:
                best_cover_size = state.cover_size
                best_cover_mask = state.cover_mask()
                stats.best_cover_improvements += 1
                stats.best_cover_size = best_cover_size
                tv = time.perf_counter()
                cand = _cover_to_maximal_clique(graph, best_cover_mask)
                stats.conversion_ms += (time.perf_counter() - tv) * 1000.0
                if len(cand) > len(best_clique) or (
                    len(cand) == len(best_clique)
                    and list_to_mask(cand) != list_to_mask(best_clique)
                ):
                    if len(cand) >= len(best_clique):
                        if len(cand) > len(best_clique):
                            best_clique = cand
                            now_ms = (time.perf_counter() - t0) * 1000.0
                            stats.time_to_best_ms = now_ms
                            stats.improvement_history.append(
                                {"time_ms": now_ms, "size": float(len(best_clique))}
                            )
                            _emit(best_clique, now_ms)
                        elite.add(
                            cand,
                            discovery_time_ms=(time.perf_counter() - t0) * 1000.0,
                            variant=config.variant.value,
                            seed=config.seed,
                        )
            # shrink: remove highest dscore
            u = state.choose_remove_vertex(rng, bms=bms)
            if u < 0:
                break
            state.remove_vertex(u)
            continue

        # two-stage exchange
        u = state.choose_remove_vertex(rng, bms=bms)
        if u < 0:
            break
        state.remove_vertex(u)

        if len(state.uncovered) == 0:
            # rare: remove didn't uncover (redundant vertex)
            continue
        e = state.uncovered.sample(rng)
        v = state.choose_add_endpoint(e, rng)
        if state.use_conf_change and not state.conf_change[v]:
            stats.prevented_readditions += 1
        state.add_vertex(v)

        tw = time.perf_counter()
        state.apply_weight_increments()
        if state.apply_forgetting_if_needed():
            stats.forgetting_events += 1
        stats.weight_update_ms += (time.perf_counter() - tw) * 1000.0

        if restart_every and steps_since_restart >= restart_every:
            # soft restart: rebuild greedy from empty with current weights reset
            steps_since_restart = 0
            stats.restarts += 1
            weights2 = EdgeWeights.create(
                comp,
                gamma=config.gamma,
                rho=config.rho,
                enable_forgetting=config.enable_forgetting,
                enable_weights=config.enable_weights,
            )
            state = NuMVCState.create(
                comp, weights2, use_conf_change=config.enable_conf_change
            )
            state.greedy_construct(rng)
            stats.constructions += 1
            if state.is_valid_cover() and state.cover_size < best_cover_size:
                best_cover_size = state.cover_size
                best_cover_mask = state.cover_mask()
                stats.best_cover_improvements += 1
                cand = _cover_to_maximal_clique(graph, best_cover_mask)
                if len(cand) > len(best_clique):
                    best_clique = cand
                    now_ms = (time.perf_counter() - t0) * 1000.0
                    stats.time_to_best_ms = now_ms
                    stats.improvement_history.append(
                        {"time_ms": now_ms, "size": float(len(best_clique))}
                    )
                    _emit(best_clique, now_ms)

    stats.local_search_ms = (time.perf_counter() - tl) * 1000.0
    stats.cover_removals = state.removals
    stats.cover_additions = state.additions
    stats.weight_increments = state.weights.weight_increments
    stats.prevented_readditions += state.prevented_readditions
    stats.conf_updates = state.conf_updates
    stats.mean_edge_weight = state.weights.mean_weight
    stats.max_edge_weight = state.weights.max_weight
    stats.best_cover_size = best_cover_size
    elapsed = max(1e-9, time.perf_counter() - t0)
    stats.steps_per_second = stats.search_steps / elapsed
    stats.total_ms = elapsed * 1000.0

    # Final ensure maximal verified
    out = sorted(best_clique)
    if out and not is_maximal_clique(graph, out):
        out = sorted(extend_to_maximal(graph, out))
    valid = is_clique(graph, out) if out else False
    maximal = is_maximal_clique(graph, out) if valid else False

    stats.extras = {
        "complement_edge_count": stats.complement_edge_count,
        "complement_density": stats.complement_density,
        "complement_ms": stats.complement_ms,
        "init_cover_ms": stats.init_cover_ms,
        "local_search_ms": stats.local_search_ms,
        "weight_update_ms": stats.weight_update_ms,
        "conversion_ms": stats.conversion_ms,
        "search_steps": stats.search_steps,
        "steps_per_second": stats.steps_per_second,
        "best_cover_size": best_cover_size,
        "valid_cover_discoveries": stats.valid_cover_discoveries,
        "best_cover_improvements": stats.best_cover_improvements,
        "forgetting_events": stats.forgetting_events,
        "weight_increments": stats.weight_increments,
        "mean_edge_weight": stats.mean_edge_weight,
        "max_edge_weight": stats.max_edge_weight,
        "prevented_readditions": stats.prevented_readditions,
        "conf_updates": stats.conf_updates,
        "restarts": stats.restarts,
        "bms_sample": bms,
        "enable_weights": config.enable_weights,
        "enable_forgetting": config.enable_forgetting,
        "enable_conf_change": config.enable_conf_change,
        "elite": elite.to_dict(),
        "gamma": state.weights.gamma,
        "rho": config.rho,
        "search_incomplete_at_deadline": time.perf_counter() >= soft,
        "response_deadline_violation": time.perf_counter() > hard,
    }

    return NuMVCResult(
        clique=out,
        clique_size=len(out) if valid else 0,
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=config.variant.value,
        stats=stats,
        deadline_reached=time.perf_counter() >= soft,
        response_deadline_violation=time.perf_counter() > hard,
        best_cover_size=best_cover_size,
    )
