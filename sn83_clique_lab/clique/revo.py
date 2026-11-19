"""R-EVO population loop (Battiti & Brunato inspired; pure Python).

Variants:
  revo_no_model   — B0 independent reactive searchers, random restarts
  revo_population — B1 shared probability model + guided restarts
  revo_diverse    — B2 model + diversity safeguards (extension)

NOT claimed as an exact line-by-line reproduction of DIT-07-034.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .competitive_search import DiverseElitePool
from .graph import BitsetGraph
from .greedy import greedy_maximal_from_start
from .revo_model import ProbabilityModel, binary_entropy_mean, mean_pairwise_jaccard
from .revo_searcher import ReactiveSearcher
from .validation import is_clique, is_maximal_clique


class RevoVariant(str, Enum):
    REVO_NO_MODEL = "revo_no_model"
    REVO_POPULATION = "revo_population"
    REVO_DIVERSE = "revo_diverse"
    REVO_INSPIRED = "revo_inspired"  # alias → revo_population until equivalence claimed


@dataclass
class RevoConfig:
    variant: RevoVariant = RevoVariant.REVO_POPULATION
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    seed: int = 42
    population_size: int = 10
    model_delta: int = 3
    learning_rate: float = 0.5
    tabu_ratio: float = 0.20
    restart_factor: int = 100
    model_initial: float = 0.5
    model_update_every_sweeps: int = 1
    steps_per_searcher_per_sweep: int = 8
    elite_capacity: int = 32
    # B2 only
    epsilon_probability_floor: float = 0.02
    random_restart_probability: float = 0.10
    diversity_jaccard_trigger: float = 0.85
    entropy_trigger: float = 0.15
    # Optional low-overhead incumbent callback (size improvements only).
    # Signature: (solver_name, clique, clique_size, elapsed_ms, seed) -> None
    on_incumbent: Optional[Callable[..., None]] = None


@dataclass
class RevoStats:
    constructions: int = 0
    population_sweeps: int = 0
    total_moves: int = 0
    restarts: int = 0
    model_updates: int = 0
    model_update_ms: float = 0.0
    local_search_ms: float = 0.0
    restart_ms: float = 0.0
    elite_ms: float = 0.0
    init_ms: float = 0.0
    total_ms: float = 0.0
    time_to_first_ms: float = 0.0
    time_to_best_ms: float = 0.0
    global_incumbent_updates: int = 0
    model_guided_restarts: int = 0
    model_guided_restart_improvements: int = 0
    plateau_moves: int = 0
    tabu_blocks: int = 0
    model_entropy_trace: List[float] = field(default_factory=list)
    jaccard_trace: List[float] = field(default_factory=list)
    improvement_history: List[Dict[str, float]] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RevoResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    variant: str
    stats: RevoStats
    deadline_reached: bool = False
    response_deadline_violation: bool = False


def _output_policy(elite: DiverseElitePool, rng: random.Random, mode: str) -> List[int]:
    return elite.sample_best_sized(rng, mode=mode) if len(elite) else []


def solve_revo(graph: BitsetGraph, config: RevoConfig) -> RevoResult:
    t0 = time.perf_counter()
    soft = t0 + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    hard = t0 + config.timeout_seconds
    stats = RevoStats()
    rng_root = random.Random(config.seed)

    use_model = config.variant != RevoVariant.REVO_NO_MODEL
    diverse = config.variant == RevoVariant.REVO_DIVERSE
    if config.variant == RevoVariant.REVO_INSPIRED:
        use_model = True
        diverse = False

    model = ProbabilityModel(
        n=graph.n,
        learning_rate=config.learning_rate,
        delta=config.model_delta,
        initial=config.model_initial,
    )

    elite = DiverseElitePool(config.elite_capacity)
    best_global: List[int] = []
    hist: List[Dict[str, float]] = []
    on_inc = config.on_incumbent

    def _emit(clique: List[int], elapsed_ms: float) -> None:
        if on_inc is None:
            return
        on_inc(config.variant.value, clique, len(clique), elapsed_ms, config.seed)

    # --- init ---
    ti = time.perf_counter()
    if graph.n:
        seed_v = max(range(graph.n), key=lambda v: graph.degree(v))
        best_global = sorted(greedy_maximal_from_start(graph, seed_v))
        elite.add(best_global, 0.0)
        stats.constructions += 1
        stats.global_incumbent_updates += 1
        stats.time_to_first_ms = (time.perf_counter() - t0) * 1000.0
        stats.time_to_best_ms = stats.time_to_first_ms
        hist.append({"time_ms": stats.time_to_first_ms, "size": float(len(best_global))})
        _emit(best_global, stats.time_to_first_ms)
    stats.init_ms = (time.perf_counter() - ti) * 1000.0

    N = max(1, config.population_size)
    searchers: List[ReactiveSearcher] = []
    for i in range(N):
        s = ReactiveSearcher(
            searcher_id=i,
            graph=graph,
            rng=random.Random(config.seed * 1009 + i * 9176 + 13),
            tabu_ratio=config.tabu_ratio,
            restart_factor=config.restart_factor,
            use_model=use_model,
            epsilon_floor=config.epsilon_probability_floor if diverse else 0.0,
            random_restart_probability=config.random_restart_probability if diverse else 0.0,
        )
        s.initialize_random()
        stats.constructions += 1
        vb = s.verified_best()
        if vb and len(vb) > len(best_global):
            best_global = vb
            ms = (time.perf_counter() - t0) * 1000.0
            elite.add(vb, ms)
            stats.global_incumbent_updates += 1
            stats.time_to_best_ms = ms
            hist.append({"time_ms": ms, "size": float(len(best_global))})
            _emit(best_global, ms)
        searchers.append(s)

    def consider_searcher(s: ReactiveSearcher) -> None:
        nonlocal best_global
        vb = s.verified_best()
        if not vb:
            return
        te = time.perf_counter()
        elite.add(vb, (te - t0) * 1000.0)
        stats.elite_ms += (time.perf_counter() - te) * 1000.0
        if len(vb) > len(best_global):
            best_global = vb
            ms = (te - t0) * 1000.0
            stats.global_incumbent_updates += 1
            stats.time_to_best_ms = ms
            hist.append({"time_ms": ms, "size": float(len(best_global)), "searcher": float(s.searcher_id)})
            _emit(best_global, ms)

    # --- main loop ---
    while time.perf_counter() < soft and graph.n:
        stats.population_sweeps += 1
        # local search steps
        tls = time.perf_counter()
        for s in searchers:
            if time.perf_counter() >= soft:
                break
            for _ in range(config.steps_per_searcher_per_sweep):
                if time.perf_counter() >= soft:
                    break
                s.step()
            consider_searcher(s)
        stats.local_search_ms += (time.perf_counter() - tls) * 1000.0

        # aggregate searcher stats lightly
        for s in searchers:
            stats.total_moves += s.stats.moves
            s.stats.moves = 0  # count incrementally per sweep
            stats.plateau_moves += s.stats.plateau_moves
            s.stats.plateau_moves = 0
            stats.tabu_blocks += s.stats.tabu_blocks
            s.stats.tabu_blocks = 0

        # model update
        if use_model and (stats.population_sweeps % max(1, config.model_update_every_sweeps) == 0):
            tm = time.perf_counter()
            cliques = [s.verified_best() or s.best for s in searchers]
            sizes = [len(c) for c in cliques]
            used = model.update_from_cliques(cliques, sizes)
            stats.model_updates += 1 if used else 0
            stats.model_update_ms += (time.perf_counter() - tm) * 1000.0
            if used:
                stats.model_entropy_trace.append(model.last_entropy)
                near = [c for c, sz in zip(cliques, sizes) if sz >= max(sizes) - config.model_delta]
                if len(near) >= 2:
                    stats.jaccard_trace.append(mean_pairwise_jaccard(near))

            if diverse:
                # collapse safeguards
                jac = stats.jaccard_trace[-1] if stats.jaccard_trace else 0.0
                ent = model.last_entropy
                if jac >= config.diversity_jaccard_trigger or ent <= config.entropy_trigger:
                    model.clamp(floor=config.epsilon_probability_floor)

        # restarts for stagnant searchers
        for s in searchers:
            if time.perf_counter() >= soft:
                break
            if s.stagnated():
                tr = time.perf_counter()
                # B2: force some uniform restarts when collapsed
                force_uniform = False
                if diverse and stats.jaccard_trace and stats.jaccard_trace[-1] >= config.diversity_jaccard_trigger:
                    force_uniform = s.rng.random() < 0.5
                if force_uniform:
                    old_use = s.use_model
                    s.use_model = False
                    s.restart(model)
                    s.use_model = old_use
                else:
                    s.restart(model if use_model else None)
                stats.restart_ms += (time.perf_counter() - tr) * 1000.0
                stats.restarts += 1
                stats.model_guided_restarts += s.stats.model_guided_restarts
                s.stats.model_guided_restarts = 0
                consider_searcher(s)

    # finalize
    mode = "diverse" if diverse else "first"
    out = _output_policy(elite, rng_root, mode) or best_global
    if out:
        out = sorted(out)
    valid = is_clique(graph, out) if out else False
    maximal = is_maximal_clique(graph, out) if valid else False

    # fold remaining searcher diagnostics
    stats.model_guided_restart_improvements = sum(
        s.stats.model_guided_restart_improvements for s in searchers
    )
    stats.extras = {
        "population_size": N,
        "use_model": use_model,
        "diverse": diverse,
        "final_model_entropy": model.last_entropy if use_model else None,
        "final_jaccard": stats.jaccard_trace[-1] if stats.jaccard_trace else None,
        "searcher_best_sizes": [s.best_size for s in searchers],
        "unique_personal_bests": len({tuple(s.best) for s in searchers if s.best}),
        "elite_size": len(elite),
        "learning_rate": config.learning_rate,
        "model_delta": config.model_delta,
        "tabu_ratio": config.tabu_ratio,
        "simplified_adaptation_note": (
            "Pure-Python R-EVO-inspired population search; not an exact DIT-07-034 reproduction."
        ),
    }
    stats.improvement_history = hist
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    return RevoResult(
        clique=out,
        clique_size=len(out),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=config.variant.value,
        stats=stats,
        deadline_reached=time.perf_counter() >= soft,
        response_deadline_violation=time.perf_counter() > hard + 1e-3,
    )
