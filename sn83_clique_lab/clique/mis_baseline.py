"""Complement independent-set baselines (Phase 5B B0 + diagnostic MIS search).

  mis_random_restart       — randomized greedy MIS in H + simple repair
  mis_configuration_search — tightness-based local search with confChange
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .bitset import bits_to_list, full_mask, list_to_mask
from .complement_graph import build_complement, ComplementGraph
from .graph import BitsetGraph
from .greedy import extend_to_maximal
from .numvc_diversity import CliquePool
from .validation import is_clique, is_maximal_clique


class MISVariant(str, Enum):
    MIS_RANDOM_RESTART = "mis_random_restart"
    MIS_CONFIGURATION_SEARCH = "mis_configuration_search"


@dataclass
class MISConfig:
    variant: MISVariant = MISVariant.MIS_RANDOM_RESTART
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    seed: int = 42
    elite_capacity: int = 32


@dataclass
class MISStats:
    constructions: int = 0
    local_improvements: int = 0
    unique_independent_sets: int = 0
    best_independent_set_size: int = 0
    search_steps: int = 0
    complement_ms: float = 0.0
    total_ms: float = 0.0
    time_to_first_ms: float = 0.0
    time_to_best_ms: float = 0.0
    complement_edge_count: int = 0
    complement_density: float = 0.0
    improvement_history: List[Dict[str, float]] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MISResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    variant: str
    stats: MISStats
    deadline_reached: bool = False
    response_deadline_violation: bool = False


def _greedy_mis(comp: ComplementGraph, rng: random.Random, start: Optional[int] = None) -> List[int]:
    """Build maximal IS in H (clique in G) by random/high-degree greedy."""
    n = comp.n
    if n <= 0:
        return []
    allv = full_mask(n)
    remaining = allv
    s: List[int] = []
    if start is not None and 0 <= start < n:
        s.append(start)
        remaining = remaining & ~comp.adjacency[start] & ~(1 << start) & allv
    while remaining:
        best_d = None
        candidates: List[int] = []
        tmp = remaining
        while tmp:
            bit = tmp & -tmp
            v = bit.bit_length() - 1
            tmp ^= bit
            if v >= n:
                continue
            d = (comp.adjacency[v] & remaining).bit_count()
            # Prefer LOW residual complement degree (classic greedy MIS)
            score = -d
            if best_d is None or score > best_d:
                best_d = score
                candidates = [v]
            elif score == best_d:
                candidates.append(v)
        if not candidates:
            break
        v = candidates[rng.randrange(len(candidates))]
        s.append(v)
        remaining = remaining & ~comp.adjacency[v] & ~(1 << v) & allv
    return sorted(s)


def _solve_random_restart(graph: BitsetGraph, comp: ComplementGraph, cfg: MISConfig, soft: float, t0: float) -> MISResult:
    stats = MISStats()
    stats.complement_edge_count = comp.complement_edge_count
    stats.complement_density = comp.complement_density
    rng = random.Random(cfg.seed)
    elite = CliquePool(cfg.elite_capacity)
    best: List[int] = []
    seen = set()

    while time.perf_counter() < soft:
        start = rng.randrange(comp.n) if comp.n else None
        s = _greedy_mis(comp, rng, start=start)
        stats.constructions += 1
        # simple local: try swap one out for better
        improved = True
        while improved and time.perf_counter() < soft:
            improved = False
            s_mask = list_to_mask(s)
            outside = bits_to_list(full_mask(comp.n) & ~s_mask)
            rng.shuffle(outside)
            for v in outside[: min(64, len(outside))]:
                # neighbors of v in S (complement)
                conflicts = [u for u in s if comp.has_edge(u, v)]
                if len(conflicts) == 0:
                    s = sorted(s + [v])
                    stats.local_improvements += 1
                    improved = True
                    break
                if len(conflicts) == 1:
                    # 1-for-1
                    u = conflicts[0]
                    new_s = [x for x in s if x != u] + [v]
                    # check still IS
                    ok = True
                    for i, a in enumerate(new_s):
                        for b in new_s[i + 1 :]:
                            if comp.has_edge(a, b):
                                ok = False
                                break
                        if not ok:
                            break
                    if ok and len(new_s) >= len(s):
                        s = sorted(new_s)
                        stats.local_improvements += 1
                        improved = True
                        break
            stats.search_steps += 1

        # convert / extend maximal in G
        clique = sorted(extend_to_maximal(graph, s))
        mask = list_to_mask(clique)
        if mask not in seen:
            seen.add(mask)
            stats.unique_independent_sets += 1
        now = (time.perf_counter() - t0) * 1000.0
        if not best:
            best = clique
            stats.time_to_first_ms = now
            stats.time_to_best_ms = now
            stats.improvement_history.append({"time_ms": now, "size": float(len(best))})
        elif len(clique) > len(best):
            best = clique
            stats.time_to_best_ms = now
            stats.improvement_history.append({"time_ms": now, "size": float(len(best))})
        elite.add(clique, discovery_time_ms=now, variant=cfg.variant.value, seed=cfg.seed)

    stats.best_independent_set_size = len(best)
    return _finalize_mis(graph, cfg, best, stats, elite, t0, soft)


def _solve_configuration(graph: BitsetGraph, comp: ComplementGraph, cfg: MISConfig, soft: float, t0: float) -> MISResult:
    """Tightness-based IS search with confChange on complement."""
    stats = MISStats()
    stats.complement_edge_count = comp.complement_edge_count
    stats.complement_density = comp.complement_density
    rng = random.Random(cfg.seed)
    elite = CliquePool(cfg.elite_capacity)
    n = comp.n
    adj = comp.adjacency

    s = _greedy_mis(comp, rng)
    stats.constructions += 1
    s_set = set(s)
    conf = [True] * n
    best = sorted(extend_to_maximal(graph, s))
    now = (time.perf_counter() - t0) * 1000.0
    stats.time_to_first_ms = now
    stats.time_to_best_ms = now
    stats.improvement_history.append({"time_ms": now, "size": float(len(best))})
    elite.add(best, discovery_time_ms=now, variant=cfg.variant.value, seed=cfg.seed)

    def tightness(v: int) -> int:
        return sum(1 for u in s_set if (adj[v] >> u) & 1)

    idle = 0
    while time.perf_counter() < soft:
        stats.search_steps += 1
        # additions
        added = False
        outside = [v for v in range(n) if v not in s_set]
        rng.shuffle(outside)
        for v in outside[:128]:
            if tightness(v) == 0 and conf[v]:
                s_set.add(v)
                # mark neighbors conf
                tmp = adj[v]
                while tmp:
                    bit = tmp & -tmp
                    conf[bit.bit_length() - 1] = True
                    tmp ^= bit
                added = True
                stats.local_improvements += 1
                break
        if added:
            idle = 0
        else:
            # plateau: tightness-1 swap
            swapped = False
            for v in outside[:128]:
                if tightness(v) != 1 or not conf[v]:
                    continue
                # find the unique neighbor in S
                conflict = -1
                tmp = adj[v]
                while tmp:
                    bit = tmp & -tmp
                    u = bit.bit_length() - 1
                    tmp ^= bit
                    if u in s_set:
                        conflict = u
                        break
                if conflict < 0:
                    continue
                s_set.remove(conflict)
                conf[conflict] = False
                tmp = adj[conflict]
                while tmp:
                    bit = tmp & -tmp
                    conf[bit.bit_length() - 1] = True
                    tmp ^= bit
                s_set.add(v)
                tmp = adj[v]
                while tmp:
                    bit = tmp & -tmp
                    conf[bit.bit_length() - 1] = True
                    tmp ^= bit
                swapped = True
                stats.local_improvements += 1
                break
            if not swapped:
                idle += 1
                if idle > 50:
                    # perturb: drop random and rebuild extension
                    if s_set:
                        drop = rng.choice(list(s_set))
                        s_set.remove(drop)
                        conf[drop] = False
                    idle = 0
                    stats.constructions += 1

        clique = sorted(extend_to_maximal(graph, sorted(s_set)))
        s_set = set(clique)  # work on maximal
        now = (time.perf_counter() - t0) * 1000.0
        if len(clique) > len(best):
            best = clique
            stats.time_to_best_ms = now
            stats.improvement_history.append({"time_ms": now, "size": float(len(best))})
        elite.add(clique, discovery_time_ms=now, variant=cfg.variant.value, seed=cfg.seed)

    stats.best_independent_set_size = len(best)
    stats.unique_independent_sets = len(elite)
    return _finalize_mis(graph, cfg, best, stats, elite, t0, soft)


def _finalize_mis(
    graph: BitsetGraph,
    cfg: MISConfig,
    best: List[int],
    stats: MISStats,
    elite: CliquePool,
    t0: float,
    soft: float,
) -> MISResult:
    out = sorted(best)
    if out and not is_maximal_clique(graph, out):
        out = sorted(extend_to_maximal(graph, out))
    valid = is_clique(graph, out) if out else False
    maximal = is_maximal_clique(graph, out) if valid else False
    hard = t0 + cfg.timeout_seconds
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    stats.extras = {
        "complement_edge_count": stats.complement_edge_count,
        "complement_density": stats.complement_density,
        "complement_ms": stats.complement_ms,
        "constructions": stats.constructions,
        "local_improvements": stats.local_improvements,
        "unique_independent_sets": stats.unique_independent_sets,
        "search_steps": stats.search_steps,
        "elite": elite.to_dict(),
        "search_incomplete_at_deadline": time.perf_counter() >= soft,
        "response_deadline_violation": time.perf_counter() > hard,
    }
    return MISResult(
        clique=out,
        clique_size=len(out) if valid else 0,
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=cfg.variant.value,
        stats=stats,
        deadline_reached=time.perf_counter() >= soft,
        response_deadline_violation=time.perf_counter() > hard,
    )


def solve_mis(graph: BitsetGraph, config: MISConfig) -> MISResult:
    t0 = time.perf_counter()
    soft = t0 + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    tc = time.perf_counter()
    comp = build_complement(graph)
    complement_ms = (time.perf_counter() - tc) * 1000.0

    if config.variant == MISVariant.MIS_CONFIGURATION_SEARCH:
        res = _solve_configuration(graph, comp, config, soft, t0)
    else:
        res = _solve_random_restart(graph, comp, config, soft, t0)
    res.stats.complement_ms = complement_ms
    res.stats.extras["complement_ms"] = complement_ms
    return res
