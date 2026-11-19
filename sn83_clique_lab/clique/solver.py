"""Public solver API for future SN83 miner integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .anytime_search import (
    AnytimeConfig,
    AnytimeVariant,
    CHECKPOINT_SECONDS,
    solve_anytime,
)
from .branch_bound import BnBConfig, BnBResult, SolverVariant, solve_bnb
from .competitive_search import (
    CompetitiveConfig,
    CompetitiveVariant,
    solve_competitive,
)
from .graph import BitsetGraph
from .greedy import initial_incumbent
from .selective_ulm import SelectiveULMConfig
from .adaptive_dual_portfolio import solve_portfolio
from .mis_baseline import MISConfig, MISVariant, solve_mis
from .numvc import NuMVCConfig, NuMVCVariant, solve_numvc
from .one_repair import OneConfig, OneVariant, solve_one
from .revo import RevoConfig, RevoVariant, solve_revo
from .spectral_clique import SpectralConfig, SpectralVariant
from .spectral_solve import solve_spectral
from .ulm import ULMConfig


@dataclass
class SolverResult:
    solver: str
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    runtime_ms: float
    search_nodes: int
    ulm_calls: int = 0
    ulm_prunes: int = 0
    ulm_time_ms: float = 0.0
    coloring_calls: int = 0
    coloring_prunes: int = 0
    deadline_reached: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


ANYTIME_VARIANTS = {
    "multistart_greedy": AnytimeVariant.MULTISTART_GREEDY,
    "d": AnytimeVariant.MULTISTART_GREEDY,
    "swap_local_search": AnytimeVariant.SWAP_LOCAL_SEARCH,
    "e": AnytimeVariant.SWAP_LOCAL_SEARCH,
    "triangle_guided": AnytimeVariant.TRIANGLE_GUIDED,
    "f": AnytimeVariant.TRIANGLE_GUIDED,
}

COMPETITIVE_VARIANTS = {
    "pls_penalty": CompetitiveVariant.PLS_PENALTY,
    "h": CompetitiveVariant.PLS_PENALTY,
    "bls_adaptive": CompetitiveVariant.BLS_ADAPTIVE,
    "g": CompetitiveVariant.BLS_ADAPTIVE,
    "ikls_variable_depth": CompetitiveVariant.IKLS_VARIABLE_DEPTH,
    "i": CompetitiveVariant.IKLS_VARIABLE_DEPTH,
    "pair_anchor": CompetitiveVariant.PAIR_ANCHOR,
    "j": CompetitiveVariant.PAIR_ANCHOR,
    "adaptive_portfolio": CompetitiveVariant.ADAPTIVE_PORTFOLIO,
    "portfolio": CompetitiveVariant.ADAPTIVE_PORTFOLIO,
    "p": CompetitiveVariant.ADAPTIVE_PORTFOLIO,
}

SPECTRAL_VARIANTS = {
    "global_spectral": SpectralVariant.GLOBAL_SPECTRAL,
    "global_spectral_plus_ikls": SpectralVariant.GLOBAL_SPECTRAL_PLUS_IKLS,
    "anchored_spectral": SpectralVariant.ANCHORED_SPECTRAL,
    "anchored_spectral_plus_ikls": SpectralVariant.ANCHORED_SPECTRAL_PLUS_IKLS,
    "spectral_portfolio": SpectralVariant.SPECTRAL_PORTFOLIO,
    "spectral_recovery": SpectralVariant.SPECTRAL_RECOVERY,
}

REVO_VARIANTS = {
    "revo_no_model": RevoVariant.REVO_NO_MODEL,
    "revo_population": RevoVariant.REVO_POPULATION,
    "revo_diverse": RevoVariant.REVO_DIVERSE,
    "revo_inspired": RevoVariant.REVO_INSPIRED,
}

ONE_VARIANTS = {
    "one_random_repair": OneVariant.ONE_RANDOM_REPAIR,
    "one_conflict_repair": OneVariant.ONE_CONFLICT_REPAIR,
    "one_adaptive_repair": OneVariant.ONE_ADAPTIVE_REPAIR,
    "one_diverse_repair": OneVariant.ONE_DIVERSE_REPAIR,
    "revo_plus_exact_repair": OneVariant.REVO_PLUS_EXACT_REPAIR,
}

MIS_VARIANTS = {
    "mis_random_restart": MISVariant.MIS_RANDOM_RESTART,
    "mis_configuration_search": MISVariant.MIS_CONFIGURATION_SEARCH,
}

NUMVC_VARIANTS = {
    "numvc_complement": NuMVCVariant.NUMVC_COMPLEMENT,
    "numvc_diversified": NuMVCVariant.NUMVC_DIVERSIFIED,
}

PORTFOLIO_VARIANTS = {
    "full_revo",
    "full_numvc",
    "revo_90_numvc_10",
    "revo_80_numvc_20",
    "revo_70_numvc_30",
    "revo_60_numvc_40",
    "revo_50_numvc_50",
    "revo_80_numvc_20_numvc_first",
    "revo_50_numvc_50_numvc_first",
    "early_probe",
    "early_probe_0.25s",
    "early_probe_0.5s",
    "early_probe_1.0s",
    "late_probe",
    "stagnation_trigger",
    "adaptive_dual_portfolio",
    "fixed_dual_portfolio",
}


def _variant_from_str(name: str) -> SolverVariant:
    key = name.strip().lower().replace("-", "_")
    mapping = {
        "baseline": SolverVariant.BASELINE,
        "a": SolverVariant.BASELINE,
        "bnb": SolverVariant.BASELINE,
        "ulm": SolverVariant.ULM,
        "b": SolverVariant.ULM,
        "full_ulm": SolverVariant.ULM,
        "selective_ulm": SolverVariant.SELECTIVE_ULM,
        "c": SolverVariant.SELECTIVE_ULM,
        "selective": SolverVariant.SELECTIVE_ULM,
    }
    if key not in mapping:
        raise ValueError(f"Unknown solver variant: {name}")
    return mapping[key]


def _checkpoints_from_history(history: List[dict], timeout_seconds: float, final_size: int) -> dict:
    out: Dict[str, Any] = {}
    for sec in CHECKPOINT_SECONDS:
        if sec > timeout_seconds + 1e-9:
            out[f"{sec:g}s"] = None
            continue
        size = 0
        t_ms = sec * 1000.0
        for row in history:
            if float(row["time_ms"]) <= t_ms + 1e-9:
                size = int(row["size"])
            else:
                break
        out[f"{sec:g}s"] = size if history else 0
    out["deadline"] = final_size
    return out


def solve_clique(
    adjacency_list: list[list[int]],
    timeout_seconds: float,
    variant: str = "baseline",
    seed: int = 42,
) -> list[int]:
    """
    Miner-friendly API: return clique vertex indices.

    Independent of Bittensor. Graphs use 0..n-1 indexing matching the
    adjacency list order.
    """
    result = solve_clique_detailed(
        adjacency_list=adjacency_list,
        timeout_seconds=timeout_seconds,
        variant=variant,
        seed=seed,
    )
    return result.clique


def solve_clique_detailed(
    adjacency_list: list[list[int]],
    timeout_seconds: float,
    variant: str = "baseline",
    seed: int = 42,
    shared_incumbent: Optional[Sequence[int]] = None,
    safety_margin_ms: float = 500.0,
    selective_config: Optional[SelectiveULMConfig] = None,
    ulm_config: Optional[ULMConfig] = None,
    graph_name: str = "",
) -> SolverResult:
    """Rich solver entrypoint returning diagnostics."""
    graph = BitsetGraph.from_adjacency_list(adjacency_list, name=graph_name)
    return solve_graph(
        graph,
        timeout_seconds=timeout_seconds,
        variant=variant,
        seed=seed,
        shared_incumbent=shared_incumbent,
        safety_margin_ms=safety_margin_ms,
        selective_config=selective_config,
        ulm_config=ulm_config,
    )


def solve_graph(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: str = "baseline",
    seed: int = 42,
    shared_incumbent: Optional[Sequence[int]] = None,
    safety_margin_ms: float = 500.0,
    selective_config: Optional[SelectiveULMConfig] = None,
    ulm_config: Optional[ULMConfig] = None,
) -> SolverResult:
    key = variant.strip().lower().replace("-", "_")
    if key in ANYTIME_VARIANTS:
        return _solve_anytime(
            graph,
            timeout_seconds=timeout_seconds,
            variant=ANYTIME_VARIANTS[key],
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key in COMPETITIVE_VARIANTS:
        return _solve_competitive(
            graph,
            timeout_seconds=timeout_seconds,
            variant=COMPETITIVE_VARIANTS[key],
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key in SPECTRAL_VARIANTS:
        return _solve_spectral(
            graph,
            timeout_seconds=timeout_seconds,
            variant=SPECTRAL_VARIANTS[key],
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key in REVO_VARIANTS:
        return _solve_revo(
            graph,
            timeout_seconds=timeout_seconds,
            variant=REVO_VARIANTS[key],
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key in ONE_VARIANTS:
        return _solve_one(
            graph,
            timeout_seconds=timeout_seconds,
            variant=ONE_VARIANTS[key],
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key in MIS_VARIANTS:
        return _solve_mis(
            graph,
            timeout_seconds=timeout_seconds,
            variant=MIS_VARIANTS[key],
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key in NUMVC_VARIANTS:
        return _solve_numvc(
            graph,
            timeout_seconds=timeout_seconds,
            variant=NUMVC_VARIANTS[key],
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key == "numvc_plus_revo":
        return _solve_numvc_plus_revo(
            graph,
            timeout_seconds=timeout_seconds,
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )
    if key in PORTFOLIO_VARIANTS or key.startswith("early_probe_") or (
        key.startswith("revo_") and "_numvc_" in key
    ):
        return _solve_portfolio(
            graph,
            timeout_seconds=timeout_seconds,
            variant=key,
            seed=seed,
            safety_margin_ms=safety_margin_ms,
        )

    v = _variant_from_str(variant)
    cfg = BnBConfig(
        variant=v,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
        shared_incumbent=list(shared_incumbent) if shared_incumbent is not None else None,
        selective=selective_config or SelectiveULMConfig(),
        ulm=ulm_config or ULMConfig(),
    )
    raw: BnBResult = solve_bnb(graph, cfg)
    ulm_calls = 0
    if v != SolverVariant.BASELINE:
        ulm_calls = raw.stats.selective.activated if v == SolverVariant.SELECTIVE_ULM else -1
        if v == SolverVariant.ULM:
            ulm_calls = raw.stats.coloring_calls

    extras = {
        "max_depth": raw.stats.max_depth,
        "incumbent_improvements": raw.stats.incumbent_improvements,
        "incumbent_times_ms": list(raw.stats.incumbent_times_ms),
        "improvement_history": list(raw.stats.improvement_history),
        "checkpoints": _checkpoints_from_history(
            raw.stats.improvement_history, timeout_seconds, raw.clique_size
        ),
        "best_from_phase": raw.stats.best_from_phase,
        "initial_heuristic_ms": raw.stats.initial_heuristic_ms,
        "branch_bound_ms": raw.stats.branch_bound_ms,
        "search_incomplete_at_deadline": raw.stats.search_incomplete_at_deadline,
        "response_deadline_violation": raw.stats.response_deadline_violation,
        "selective": {
            "eligible": raw.stats.selective.eligible,
            "activated": raw.stats.selective.activated,
            "skipped": raw.stats.selective.skipped,
            "skip_reasons": dict(raw.stats.selective.skip_reasons),
            "additional_prunes": raw.stats.selective.additional_prunes,
        },
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        "graph_hash": graph.content_hash() if graph.n <= 2000 else "",
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=raw.proven_optimal,
        runtime_ms=raw.stats.total_ms,
        search_nodes=raw.stats.search_nodes,
        ulm_calls=ulm_calls if ulm_calls >= 0 else raw.stats.coloring_calls,
        ulm_prunes=raw.stats.ulm_prunes,
        ulm_time_ms=raw.stats.ulm_time_ms,
        coloring_calls=raw.stats.coloring_calls,
        coloring_prunes=raw.stats.coloring_prunes,
        deadline_reached=raw.stats.deadline_reached,
        extras=extras,
    )


def _solve_anytime(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: AnytimeVariant,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    cfg = AnytimeConfig(
        variant=variant,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
    )
    raw = solve_anytime(graph, cfg)
    st = raw.stats
    extras = {
        "incumbent_improvements": st.incumbent_improvements,
        "improvement_history": list(st.improvement_history),
        "checkpoints": dict(st.checkpoints),
        "time_to_first_ms": st.time_to_first_ms,
        "time_to_best_ms": st.time_to_best_ms,
        "constructions": st.constructions,
        "restarts": st.restarts,
        "unique_cliques": st.unique_cliques,
        "swap_1for2_attempts": st.swap_1for2_attempts,
        "swap_1for2_success": st.swap_1for2_success,
        "swap_2for3_attempts": st.swap_2for3_attempts,
        "swap_2for3_success": st.swap_2for3_success,
        "perturbations": st.perturbations,
        "escape_improvements": st.escape_improvements,
        "construction_time_ms": st.construction_time_ms,
        "local_search_time_ms": st.local_search_time_ms,
        "triangle_prep_time_ms": st.triangle_prep_time_ms,
        "search_incomplete_at_deadline": st.search_incomplete_at_deadline,
        "response_deadline_violation": st.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        "graph_hash": graph.content_hash() if graph.n <= 2000 else "",
        **st.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=False,
        runtime_ms=st.total_ms,
        search_nodes=st.constructions,
        ulm_calls=0,
        ulm_prunes=0,
        ulm_time_ms=0.0,
        coloring_calls=0,
        coloring_prunes=0,
        deadline_reached=st.deadline_reached,
        extras=extras,
    )


def _solve_competitive(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: CompetitiveVariant,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    cfg = CompetitiveConfig(
        variant=variant,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
    )
    raw = solve_competitive(graph, cfg)
    st = raw.stats
    extras = {
        "incumbent_improvements": st.incumbent_improvements,
        "improvement_history": list(st.improvement_history),
        "checkpoints": dict(st.checkpoints),
        "time_to_first_ms": st.time_to_first_ms,
        "time_to_best_ms": st.time_to_best_ms,
        "constructions": st.constructions,
        "plateau_moves": st.plateau_moves,
        "useful_plateau_moves": st.useful_plateau_moves,
        "add_moves": st.add_moves,
        "perturbations": st.perturbations,
        "avg_perturbation_strength": st.avg_perturbation_strength,
        "revisited_states": st.revisited_states,
        "successful_escapes": st.successful_escapes,
        "phase_transitions": st.phase_transitions,
        "penalty_updates": st.penalty_updates,
        "variable_depth_sequences": st.variable_depth_sequences,
        "variable_depth_improvements": st.variable_depth_improvements,
        "pair_starts": st.pair_starts,
        "unique_cliques": st.unique_cliques,
        "local_search_time_ms": st.local_search_time_ms,
        "perturbation_time_ms": st.perturbation_time_ms,
        "pair_prep_time_ms": st.pair_prep_time_ms,
        "search_incomplete_at_deadline": st.search_incomplete_at_deadline,
        "response_deadline_violation": st.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        "graph_hash": graph.content_hash() if graph.n <= 2000 else "",
        **st.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=False,
        runtime_ms=st.total_ms,
        search_nodes=st.constructions + st.plateau_moves + st.add_moves,
        ulm_calls=0,
        ulm_prunes=0,
        ulm_time_ms=0.0,
        coloring_calls=0,
        coloring_prunes=0,
        deadline_reached=st.deadline_reached,
        extras=extras,
    )


def _solve_spectral(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: SpectralVariant,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    cfg = SpectralConfig(
        variant=variant,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
    )
    raw = solve_spectral(graph, cfg)
    st = raw.stats
    extras = {
        "improvement_history": list(st.improvement_history),
        "checkpoints": _checkpoints_from_history(
            st.improvement_history, timeout_seconds, raw.clique_size
        ),
        "time_to_first_ms": st.time_to_first_ms,
        "time_to_best_ms": st.time_to_best_ms,
        "constructions": st.constructions,
        "valid_cliques": st.valid_cliques,
        "spectral_ms": st.spectral_ms,
        "construction_ms": st.construction_ms,
        "lanczos_iters": st.lanczos_iters,
        "residuals": list(st.residuals),
        "eigenvalues": list(st.eigenvalues),
        "ikls_calls": st.ikls_calls,
        "ikls_improvements": st.ikls_improvements,
        "pair_starts": st.pair_starts,
        "search_incomplete_at_deadline": raw.deadline_reached,
        "response_deadline_violation": raw.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        "graph_hash": graph.content_hash() if graph.n <= 2000 else "",
        **st.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=False,
        runtime_ms=st.total_ms,
        search_nodes=st.constructions,
        ulm_calls=0,
        ulm_prunes=0,
        ulm_time_ms=0.0,
        coloring_calls=0,
        coloring_prunes=0,
        deadline_reached=raw.deadline_reached,
        extras=extras,
    )


def _solve_revo(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: RevoVariant,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    cfg = RevoConfig(
        variant=variant,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
    )
    raw = solve_revo(graph, cfg)
    st = raw.stats
    extras = {
        "improvement_history": list(st.improvement_history),
        "checkpoints": _checkpoints_from_history(
            st.improvement_history, timeout_seconds, raw.clique_size
        ),
        "time_to_first_ms": st.time_to_first_ms,
        "time_to_best_ms": st.time_to_best_ms,
        "constructions": st.constructions,
        "population_sweeps": st.population_sweeps,
        "total_moves": st.total_moves,
        "restarts": st.restarts,
        "model_updates": st.model_updates,
        "model_update_ms": st.model_update_ms,
        "local_search_ms": st.local_search_ms,
        "restart_ms": st.restart_ms,
        "elite_ms": st.elite_ms,
        "init_ms": st.init_ms,
        "global_incumbent_updates": st.global_incumbent_updates,
        "model_guided_restarts": st.model_guided_restarts,
        "model_guided_restart_improvements": st.model_guided_restart_improvements,
        "plateau_moves": st.plateau_moves,
        "tabu_blocks": st.tabu_blocks,
        "model_entropy_trace": list(st.model_entropy_trace[-20:]),
        "jaccard_trace": list(st.jaccard_trace[-20:]),
        "search_incomplete_at_deadline": raw.deadline_reached,
        "response_deadline_violation": raw.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        **st.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=False,
        runtime_ms=st.total_ms,
        search_nodes=st.total_moves + st.constructions,
        ulm_calls=0,
        ulm_prunes=0,
        ulm_time_ms=0.0,
        coloring_calls=0,
        coloring_prunes=0,
        deadline_reached=raw.deadline_reached,
        extras=extras,
    )


def _solve_one(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: OneVariant,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    cfg = OneConfig(
        variant=variant,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
    )
    raw = solve_one(graph, cfg)
    st = raw.stats
    extras = {
        "improvement_history": list(st.improvement_history),
        "checkpoints": _checkpoints_from_history(
            st.improvement_history, timeout_seconds, raw.clique_size
        ),
        "time_to_first_ms": st.time_to_first_ms,
        "time_to_best_ms": st.time_to_best_ms,
        "constructions": st.constructions,
        "search_incomplete_at_deadline": raw.deadline_reached,
        "response_deadline_violation": raw.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        **st.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=False,
        runtime_ms=st.total_ms,
        search_nodes=st.search_nodes_total + st.constructions,
        ulm_calls=0,
        ulm_prunes=0,
        ulm_time_ms=0.0,
        coloring_calls=st.color_prunes_total,
        coloring_prunes=st.color_prunes_total,
        deadline_reached=raw.deadline_reached,
        extras=extras,
    )


def _solve_mis(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: MISVariant,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    cfg = MISConfig(
        variant=variant,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
    )
    raw = solve_mis(graph, cfg)
    st = raw.stats
    extras = {
        "improvement_history": list(st.improvement_history),
        "checkpoints": _checkpoints_from_history(
            st.improvement_history, timeout_seconds, raw.clique_size
        ),
        "time_to_first_ms": st.time_to_first_ms,
        "time_to_best_ms": st.time_to_best_ms,
        "constructions": st.constructions,
        "search_incomplete_at_deadline": raw.deadline_reached,
        "response_deadline_violation": raw.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        **st.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=False,
        runtime_ms=st.total_ms,
        search_nodes=st.search_steps + st.constructions,
        deadline_reached=raw.deadline_reached,
        extras=extras,
    )


def _solve_numvc(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: NuMVCVariant,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    cfg = NuMVCConfig(
        variant=variant,
        seed=seed,
        timeout_seconds=timeout_seconds,
        safety_margin_ms=safety_margin_ms,
    )
    raw = solve_numvc(graph, cfg)
    st = raw.stats
    extras = {
        "improvement_history": list(st.improvement_history),
        "checkpoints": _checkpoints_from_history(
            st.improvement_history, timeout_seconds, raw.clique_size
        ),
        "time_to_first_ms": st.time_to_first_ms,
        "time_to_best_ms": st.time_to_best_ms,
        "constructions": st.constructions,
        "search_incomplete_at_deadline": raw.deadline_reached,
        "response_deadline_violation": raw.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        **st.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=raw.proven_optimal,
        runtime_ms=st.total_ms,
        search_nodes=st.search_steps,
        deadline_reached=raw.deadline_reached,
        extras=extras,
    )


def _solve_numvc_plus_revo(
    graph: BitsetGraph,
    timeout_seconds: float,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    """Independent 50/50 NuMVC + R-EVO under one deadline; take best size."""
    import time as _time

    soft_budget = max(0.1, timeout_seconds - safety_margin_ms / 1000.0)
    half = soft_budget / 2.0
    t0 = _time.perf_counter()
    numvc = solve_numvc(
        graph,
        NuMVCConfig(
            variant=NuMVCVariant.NUMVC_COMPLEMENT,
            timeout_seconds=half,
            safety_margin_ms=0.0,
            seed=seed,
        ),
    )
    revo = solve_revo(
        graph,
        RevoConfig(
            variant=RevoVariant.REVO_NO_MODEL,
            timeout_seconds=max(0.05, soft_budget - (_time.perf_counter() - t0)),
            safety_margin_ms=0.0,
            seed=seed + 1,
        ),
    )
    if len(revo.clique) > len(numvc.clique):
        best_c, src = revo.clique, "revo"
        valid, maximal = revo.valid, revo.maximal
    else:
        best_c, src = numvc.clique, "numvc"
        valid, maximal = numvc.valid, numvc.maximal
    total_ms = (_time.perf_counter() - t0) * 1000.0
    hard_viol = (_time.perf_counter() - t0) > timeout_seconds
    return SolverResult(
        solver="numvc_plus_revo",
        clique=sorted(best_c),
        clique_size=len(best_c),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        runtime_ms=total_ms,
        search_nodes=numvc.stats.search_steps + revo.stats.total_moves,
        deadline_reached=True,
        extras={
            "winner": src,
            "numvc_size": numvc.clique_size,
            "revo_size": revo.clique_size,
            "response_deadline_violation": hard_viol,
            "search_incomplete_at_deadline": True,
            "time_to_best_ms": total_ms,
            "improvement_history": [
                {"time_ms": total_ms, "size": float(len(best_c))}
            ],
        },
    )


def _solve_portfolio(
    graph: BitsetGraph,
    timeout_seconds: float,
    variant: str,
    seed: int,
    safety_margin_ms: float,
) -> SolverResult:
    raw = solve_portfolio(
        graph,
        variant=variant,
        timeout_seconds=timeout_seconds,
        seed=seed,
        safety_margin_ms=safety_margin_ms,
    )
    st = raw.stats
    extras = {
        "improvement_history": [
            {"time_ms": e["elapsed_ms"], "size": float(e["size"])} for e in st.events if e.get("grew_global")
        ],
        "time_to_best_ms": raw.incumbent.get("discovery_time_ms"),
        "search_incomplete_at_deadline": raw.deadline_reached,
        "response_deadline_violation": raw.response_deadline_violation,
        "graph_n": graph.n,
        "graph_edges": graph.edge_count(),
        "graph_density": graph.density(),
        "incumbent": raw.incumbent,
        **raw.extras,
    }
    return SolverResult(
        solver=raw.variant,
        clique=raw.clique,
        clique_size=raw.clique_size,
        valid=raw.valid,
        maximal=raw.maximal,
        proven_optimal=False,
        runtime_ms=float(raw.extras.get("total_runtime_ms") or 0.0),
        search_nodes=st.revo_slices + st.numvc_slices,
        deadline_reached=raw.deadline_reached,
        extras=extras,
    )


def shared_initial_incumbent(graph: BitsetGraph, seed: int = 42) -> List[int]:
    """Same incumbent for fair A/B/C comparison."""
    return initial_incumbent(graph, seed=seed)
