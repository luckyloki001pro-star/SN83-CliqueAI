"""Optimal-Neighborhood Exploration (ONE) repair solvers — Phase 5A.

Variants:
  one_random_repair
  one_conflict_repair
  one_adaptive_repair
  one_diverse_repair

Uses R-EVO (unchanged) for the initial phase, then bounded exact repair
inside compatible neighborhoods H = ∩ N(F).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .bitset import list_to_mask
from .greedy import extend_to_maximal
from .graph import BitsetGraph
from .neighborhood_diversity import ElitePool
from .neighborhood_exact import ExactStatus, search_target_clique
from .neighborhood_selector import (
    AdaptiveRController,
    ProposedNeighborhood,
    conflict_guided_removals,
    iter_scheduled_neighborhoods,
    random_removals,
)
from .optimal_neighborhood import assemble_clique, build_neighborhood
from .revo import RevoConfig, RevoVariant, solve_revo
from .validation import is_clique, is_maximal_clique


class OneVariant(str, Enum):
    ONE_RANDOM_REPAIR = "one_random_repair"
    ONE_CONFLICT_REPAIR = "one_conflict_repair"
    ONE_ADAPTIVE_REPAIR = "one_adaptive_repair"
    ONE_DIVERSE_REPAIR = "one_diverse_repair"
    REVO_PLUS_EXACT_REPAIR = "revo_plus_exact_repair"  # alias → conflict


@dataclass
class OneConfig:
    variant: OneVariant = OneVariant.ONE_CONFLICT_REPAIR
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    seed: int = 42
    # Fraction of soft deadline for initial R-EVO (rest for repair)
    revo_fraction: float = 0.65
    min_neighborhood_budget_ms: float = 2.0
    max_neighborhood_budget_ms: float = 100.0
    fixed_r: Optional[int] = None  # if set, prefer this r for random
    removal_sizes: Tuple[int, ...] = (3, 4, 6, 8, 10)
    elite_capacity: int = 64
    output_policy: str = "first_best"
    enum_budget_fraction: float = 0.15  # of remaining repair time after improvement stall
    continue_revo_control: bool = False  # if True: spend repair budget on more R-EVO instead


@dataclass
class OneStats:
    constructions: int = 0
    neighborhoods_attempted: int = 0
    neighborhoods_completed: int = 0
    neighborhoods_timed_out: int = 0
    neighborhoods_rejected_size: int = 0
    target_cliques_found: int = 0
    proven_impossible_neighborhoods: int = 0
    improvements_of_one: int = 0
    improvements_of_two_or_more: int = 0
    cache_hits: int = 0
    search_nodes_total: int = 0
    color_prunes_total: int = 0
    revo_ms: float = 0.0
    repair_ms: float = 0.0
    total_ms: float = 0.0
    time_to_first_ms: float = 0.0
    time_to_best_ms: float = 0.0
    time_to_first_improvement_ms: float = 0.0
    elite_count: int = 0
    improvement_history: List[Dict[str, float]] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OneResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    variant: str
    stats: OneStats
    deadline_reached: bool = False
    response_deadline_violation: bool = False


def _selector_mode(variant: OneVariant) -> str:
    if variant == OneVariant.ONE_RANDOM_REPAIR:
        return "random"
    if variant == OneVariant.ONE_CONFLICT_REPAIR:
        return "conflict"
    if variant == OneVariant.ONE_ADAPTIVE_REPAIR:
        return "adaptive"
    if variant == OneVariant.ONE_DIVERSE_REPAIR:
        return "conflict"
    if variant == OneVariant.REVO_PLUS_EXACT_REPAIR:
        return "conflict"
    return "random"


def _neighborhood_slice_ms(remaining_ms: float, cfg: OneConfig) -> float:
    return max(
        cfg.min_neighborhood_budget_ms,
        min(cfg.max_neighborhood_budget_ms, remaining_ms * 0.25),
    )


def solve_one(graph: BitsetGraph, config: OneConfig) -> OneResult:
    t0 = time.perf_counter()
    soft = t0 + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    hard = t0 + config.timeout_seconds
    stats = OneStats()
    rng = random.Random(config.seed)
    elite = ElitePool(config.elite_capacity)
    controller = AdaptiveRController(sizes=list(config.removal_sizes))

    # ---- Phase A: R-EVO initial ----
    revo_deadline = t0 + max(0.05, (soft - t0) * config.revo_fraction)
    revo_timeout = max(0.05, revo_deadline - t0)
    revo_cfg = RevoConfig(
        variant=RevoVariant.REVO_NO_MODEL,
        timeout_seconds=revo_timeout,
        safety_margin_ms=0.0,  # already sliced; soft bound is revo_deadline
        seed=config.seed,
    )
    # Cap revo soft deadline via timeout_seconds only (margin 0 → soft=hard for this slice)
    # But we must not exceed global soft: clamp timeout
    revo_cfg.timeout_seconds = min(revo_timeout, max(0.05, soft - t0))
    tr0 = time.perf_counter()
    revo_res = solve_revo(graph, revo_cfg)
    stats.revo_ms = (time.perf_counter() - tr0) * 1000.0
    stats.constructions += revo_res.stats.constructions

    best = list(revo_res.clique)
    if best and not is_maximal_clique(graph, best):
        best = sorted(extend_to_maximal(graph, best))
    best = sorted(best) if best else []
    working = list(best)

    if best:
        stats.time_to_first_ms = (time.perf_counter() - t0) * 1000.0
        stats.time_to_best_ms = stats.time_to_first_ms
        stats.improvement_history.append(
            {"time_ms": stats.time_to_first_ms, "size": float(len(best))}
        )
        elite.add(
            best,
            discovery_time_ms=stats.time_to_first_ms,
            method="revo",
            seed=config.seed,
        )

    # Control: continue R-EVO instead of repair
    if config.continue_revo_control and time.perf_counter() < soft:
        rem = max(0.05, soft - time.perf_counter())
        cont = RevoConfig(
            variant=RevoVariant.REVO_NO_MODEL,
            timeout_seconds=rem,
            safety_margin_ms=0.0,
            seed=config.seed + 7,
        )
        tr1 = time.perf_counter()
        cont_res = solve_revo(graph, cont)
        stats.repair_ms = (time.perf_counter() - tr1) * 1000.0
        if len(cont_res.clique) > len(best):
            best = sorted(cont_res.clique)
            working = list(best)
            stats.time_to_best_ms = (time.perf_counter() - t0) * 1000.0
            stats.improvement_history.append(
                {"time_ms": stats.time_to_best_ms, "size": float(len(best))}
            )
            elite.add(
                best,
                discovery_time_ms=stats.time_to_best_ms,
                method="revo_continue",
                seed=config.seed,
            )
        return _finalize(graph, config, best, elite, stats, t0, soft, hard)

    # ---- Phase B: exact neighborhood repair ----
    mode = _selector_mode(config.variant)
    # Cache: (fixed_mask, target) -> status string for proven failures only
    proven_cache: Dict[Tuple[int, int], str] = {}
    attempted_sigs: set = set()
    cand_counts: List[int] = []
    r_success: Dict[int, int] = {}
    r_attempts: Dict[int, int] = {}

    repair_start = time.perf_counter()
    stall_after_best = time.perf_counter()
    do_enum = config.variant == OneVariant.ONE_DIVERSE_REPAIR

    while time.perf_counter() < soft:
        if not working or len(working) < 2:
            break
        remaining_ms = (soft - time.perf_counter()) * 1000.0
        if remaining_ms < config.min_neighborhood_budget_ms:
            break

        # Optional equal-size enum budget near end for diverse variant
        if (
            do_enum
            and stats.improvements_of_one + stats.improvements_of_two_or_more == 0
            and (time.perf_counter() - stall_after_best) > 0.5 * (soft - repair_start)
        ):
            # use remaining fraction for equal-size enumeration
            enum_deadline = min(soft, time.perf_counter() + remaining_ms / 1000.0 * config.enum_budget_fraction)
            props = list(
                conflict_guided_removals(graph, working, rng, max_proposals=4)
            ) or random_removals(working, min(6, len(working) - 1), rng, 2)
            for prop in props:
                if time.perf_counter() >= enum_deadline:
                    break
                nb = build_neighborhood(graph, working, prop.remove)
                slice_s = min(
                    config.max_neighborhood_budget_ms / 1000.0,
                    enum_deadline - time.perf_counter(),
                )
                if slice_s <= 0:
                    break
                # equal size target = r
                res = search_target_clique(
                    graph, nb.candidate_mask, nb.removed_count, time.perf_counter() + slice_s
                )
                stats.neighborhoods_attempted += 1
                if res.status == ExactStatus.TARGET_FOUND and res.clique:
                    new_c = assemble_clique(nb.fixed_mask, list_to_mask(res.clique))
                    new_c = sorted(extend_to_maximal(graph, new_c))
                    if is_clique(graph, new_c):
                        elite.add(
                            new_c,
                            discovery_time_ms=(time.perf_counter() - t0) * 1000.0,
                            method="equal_enum",
                            seed=config.seed,
                            neighborhood_signature=nb.fixed_mask,
                        )
                        if len(new_c) > len(best):
                            delta = len(new_c) - len(best)
                            best = list(new_c)
                            working = list(best)
                            stats.time_to_best_ms = (time.perf_counter() - t0) * 1000.0
                            if delta == 1:
                                stats.improvements_of_one += 1
                            else:
                                stats.improvements_of_two_or_more += 1
                            stats.improvement_history.append(
                                {"time_ms": stats.time_to_best_ms, "size": float(len(best))}
                            )
                            stall_after_best = time.perf_counter()
            # after enum pass, continue improvement search
            do_enum = False  # one enum burst per solve

        proposals = list(
            iter_scheduled_neighborhoods(
                graph,
                working,
                rng,
                mode=mode,
                r_fixed=config.fixed_r,
                controller=controller,
                batch=4,
            )
        )
        if not proposals:
            # fallback random r=4
            proposals = random_removals(working, min(4, len(working) - 1), rng, 4)
        progressed = False
        for prop in proposals:
            if time.perf_counter() >= soft:
                break
            rem_ms = (soft - time.perf_counter()) * 1000.0
            if rem_ms < config.min_neighborhood_budget_ms:
                break
            sig = (prop.signature, len(working) - prop.r + 1)  # fixed + target
            if prop.signature in attempted_sigs and sig in proven_cache:
                stats.cache_hits += 1
                continue
            attempted_sigs.add(prop.signature)

            nb = build_neighborhood(graph, working, prop.remove)
            r_attempts[prop.r] = r_attempts.get(prop.r, 0) + 1
            if not nb.r_subset_of_h:
                # graph / construction anomaly — skip
                continue
            if not nb.feasible_for_improve:
                stats.neighborhoods_rejected_size += 1
                proven_cache[sig] = ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD.value
                continue

            cache_key = (nb.fixed_mask, nb.target_size)
            if cache_key in proven_cache:
                stats.cache_hits += 1
                continue

            cand_counts.append(nb.candidate_count)
            slice_ms = _neighborhood_slice_ms(rem_ms, config)
            ndeadline = min(soft, time.perf_counter() + slice_ms / 1000.0)
            stats.neighborhoods_attempted += 1

            res = search_target_clique(
                graph, nb.candidate_mask, nb.target_size, ndeadline
            )
            stats.search_nodes_total += res.stats.search_nodes
            stats.color_prunes_total += res.stats.color_prunes

            improved = False
            timed_out = res.status == ExactStatus.TIMEOUT
            proven = res.status == ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD

            if proven:
                stats.proven_impossible_neighborhoods += 1
                stats.neighborhoods_completed += 1
                proven_cache[cache_key] = res.status.value
            elif timed_out:
                stats.neighborhoods_timed_out += 1
            elif res.status == ExactStatus.TARGET_FOUND:
                stats.target_cliques_found += 1
                stats.neighborhoods_completed += 1
                q_mask = list_to_mask(res.clique)
                new_c = assemble_clique(nb.fixed_mask, q_mask)
                if not is_clique(graph, new_c):
                    controller.record(
                        prop.r,
                        improved=False,
                        candidate_count=nb.candidate_count,
                        search_nodes=res.stats.search_nodes,
                        search_ms=res.stats.total_ms,
                        timed_out=False,
                        proven=False,
                    )
                    continue
                new_c = sorted(extend_to_maximal(graph, new_c))
                if not is_clique(graph, new_c) or not is_maximal_clique(graph, new_c):
                    # maximality check failed somehow — skip
                    pass
                elif len(new_c) > len(best):
                    delta = len(new_c) - len(best)
                    best = list(new_c)
                    working = list(best)
                    improved = True
                    progressed = True
                    now_ms = (time.perf_counter() - t0) * 1000.0
                    if stats.time_to_first_improvement_ms <= 0:
                        stats.time_to_first_improvement_ms = now_ms
                    stats.time_to_best_ms = now_ms
                    if delta == 1:
                        stats.improvements_of_one += 1
                    else:
                        stats.improvements_of_two_or_more += 1
                    r_success[prop.r] = r_success.get(prop.r, 0) + 1
                    stats.improvement_history.append(
                        {"time_ms": now_ms, "size": float(len(best))}
                    )
                    elite.add(
                        best,
                        discovery_time_ms=now_ms,
                        method=f"exact_r{prop.r}",
                        seed=config.seed,
                        neighborhood_signature=nb.fixed_mask,
                    )
                    stall_after_best = time.perf_counter()
                    # Invalidate caches keyed on old target sizes implicitly by new K
                    proven_cache.clear()
                    attempted_sigs.clear()
                elif len(new_c) == len(best):
                    elite.add(
                        new_c,
                        discovery_time_ms=(time.perf_counter() - t0) * 1000.0,
                        method=f"equal_r{prop.r}",
                        seed=config.seed,
                        neighborhood_signature=nb.fixed_mask,
                    )

            controller.record(
                prop.r,
                improved=improved,
                candidate_count=nb.candidate_count,
                search_nodes=res.stats.search_nodes,
                search_ms=res.stats.total_ms,
                timed_out=timed_out,
                proven=proven,
            )
            if progressed:
                break  # rebuild proposals around new working clique

        if not progressed and not proposals:
            break

    stats.repair_ms = (time.perf_counter() - repair_start) * 1000.0
    return _finalize(graph, config, best, elite, stats, t0, soft, hard, controller, cand_counts, r_success, r_attempts)


def _finalize(
    graph: BitsetGraph,
    config: OneConfig,
    best: List[int],
    elite: ElitePool,
    stats: OneStats,
    t0: float,
    soft: float,
    hard: float,
    controller: Optional[AdaptiveRController] = None,
    cand_counts: Optional[List[int]] = None,
    r_success: Optional[Dict[int, int]] = None,
    r_attempts: Optional[Dict[int, int]] = None,
) -> OneResult:
    rng = random.Random(config.seed + 99)
    if config.variant == OneVariant.ONE_DIVERSE_REPAIR and len(elite) > 0:
        out = elite.sample(rng, policy=config.output_policy)
    else:
        out = list(best) if best else (elite.sample(rng, "first_best") if len(elite) else [])

    if out and not is_maximal_clique(graph, out):
        out = sorted(extend_to_maximal(graph, out))
    out = sorted(out) if out else []

    stats.elite_count = len(elite)
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    deadline_reached = time.perf_counter() >= soft
    violation = time.perf_counter() > hard

    diag = elite.to_diagnostics()
    stats.extras = {
        "revo_fraction": config.revo_fraction,
        "selector_mode": _selector_mode(config.variant),
        "adaptive_r": controller.to_dict() if controller else {},
        "candidate_count_distribution": {
            "n": len(cand_counts or []),
            "mean": (sum(cand_counts) / len(cand_counts)) if cand_counts else 0.0,
            "max": max(cand_counts) if cand_counts else 0,
            "min": min(cand_counts) if cand_counts else 0,
        },
        "improvement_rate_by_r": {
            str(r): {
                "attempts": (r_attempts or {}).get(r, 0),
                "successes": (r_success or {}).get(r, 0),
            }
            for r in sorted(set(list((r_attempts or {}).keys()) + list((r_success or {}).keys())))
        },
        "elite": diag,
        "output_policy": config.output_policy,
        "search_incomplete_at_deadline": deadline_reached,
        "response_deadline_violation": violation,
        "neighborhoods_attempted": stats.neighborhoods_attempted,
        "neighborhoods_completed": stats.neighborhoods_completed,
        "neighborhoods_timed_out": stats.neighborhoods_timed_out,
        "proven_impossible_neighborhoods": stats.proven_impossible_neighborhoods,
        "target_cliques_found": stats.target_cliques_found,
        "improvements_of_one": stats.improvements_of_one,
        "improvements_of_two_or_more": stats.improvements_of_two_or_more,
        "time_to_first_improvement_ms": stats.time_to_first_improvement_ms,
        "cache_hits": stats.cache_hits,
        "revo_ms": stats.revo_ms,
        "repair_ms": stats.repair_ms,
        "search_nodes_total": stats.search_nodes_total,
        "color_prunes_total": stats.color_prunes_total,
    }

    valid = is_clique(graph, out) if out else False
    maximal = is_maximal_clique(graph, out) if valid else False
    return OneResult(
        clique=out,
        clique_size=len(out) if valid else 0,
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=config.variant.value,
        stats=stats,
        deadline_reached=deadline_reached,
        response_deadline_violation=violation,
    )
