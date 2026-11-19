"""Dual-solver portfolio engines (R-EVO + NuMVC) with restart-based time slices.

True cooperative pause/resume is NOT claimed. Each run_until call starts a fresh
solver instance for the allocated slice (state is lost at slice boundaries).
In-memory shared incumbent preserves the best verified output across slices.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .graph import BitsetGraph
from .numvc import NuMVCConfig, NuMVCVariant, solve_numvc
from .portfolio_incumbent import SharedIncumbent
from .revo import RevoConfig, RevoVariant, solve_revo


@dataclass
class EngineStats:
    revo_init_ms: float = 0.0
    revo_search_ms: float = 0.0
    numvc_init_ms: float = 0.0
    numvc_search_ms: float = 0.0
    scheduler_overhead_ms: float = 0.0
    verification_ms: float = 0.0
    revo_slices: int = 0
    numvc_slices: int = 0
    switches: int = 0
    switch_reasons: List[str] = field(default_factory=list)
    probe_count: int = 0
    successful_probe_count: int = 0
    unsuccessful_probe_count: int = 0
    revo_best_size: int = 0
    numvc_best_size: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PortfolioResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    variant: str
    stats: EngineStats
    incumbent: Dict[str, Any]
    deadline_reached: bool = False
    response_deadline_violation: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)


class DualPortfolioEngine:
    """Independent R-EVO / NuMVC slices reporting to one SharedIncumbent."""

    def __init__(
        self,
        graph: BitsetGraph,
        seed: int = 42,
        *,
        absolute_deadline: float,
        safe_deadline: float,
        t0: Optional[float] = None,
    ):
        self.graph = graph
        self.seed = seed
        self.absolute_deadline = absolute_deadline
        self.safe_deadline = safe_deadline
        self.t0 = t0 if t0 is not None else time.perf_counter()
        self.incumbent = SharedIncumbent(graph)
        self.stats = EngineStats()
        self._last_solver: Optional[str] = None
        # No access to historical miner answers — graph only.

    def _elapsed_ms(self) -> float:
        return (time.perf_counter() - self.t0) * 1000.0

    def _remaining(self) -> float:
        return max(0.0, self.safe_deadline - time.perf_counter())

    def _note_switch(self, solver: str, reason: str) -> None:
        if self._last_solver is not None and self._last_solver != solver:
            self.stats.switches += 1
            self.stats.switch_reasons.append(reason)
        self._last_solver = solver

    def run_revo_slice(self, seconds: float, *, reason: str = "revo_slice", seed_offset: int = 0) -> int:
        """Run R-EVO for up to `seconds` (restart-based). Returns size found in slice."""
        rem = self._remaining()
        budget = min(max(0.0, seconds), rem)
        if budget < 0.02:
            return 0
        self._note_switch("revo", reason)
        before = self.incumbent.size
        events: List[Dict[str, Any]] = []

        def on_inc(name, clique, size, elapsed_ms, seed):
            # elapsed_ms is relative to slice start; convert to portfolio clock via wall
            wall = self._elapsed_ms()
            grew = self.incumbent.consider(clique, source="revo_no_model", discovery_time_ms=wall)
            ev = {
                "solver": "revo_no_model",
                "size": size,
                "elapsed_ms": wall,
                "slice_elapsed_ms": elapsed_ms,
                "grew_global": grew,
            }
            events.append(ev)
            self.stats.events.append(ev)

        t_slice = time.perf_counter()
        cfg = RevoConfig(
            variant=RevoVariant.REVO_NO_MODEL,
            timeout_seconds=budget,
            safety_margin_ms=0.0,
            seed=self.seed + seed_offset,
            on_incumbent=on_inc,
        )
        res = solve_revo(self.graph, cfg)
        wall_ms = (time.perf_counter() - t_slice) * 1000.0
        # Approximate init vs search from stats
        self.stats.revo_init_ms += res.stats.init_ms
        self.stats.revo_search_ms += max(0.0, wall_ms - res.stats.init_ms)
        self.stats.revo_slices += 1
        self.stats.revo_best_size = max(self.stats.revo_best_size, res.clique_size)
        tv = time.perf_counter()
        self.incumbent.consider(
            res.clique, source="revo_no_model", discovery_time_ms=self._elapsed_ms()
        )
        self.stats.verification_ms += (time.perf_counter() - tv) * 1000.0
        return self.incumbent.size - before

    def run_numvc_slice(self, seconds: float, *, reason: str = "numvc_slice", seed_offset: int = 0) -> int:
        rem = self._remaining()
        budget = min(max(0.0, seconds), rem)
        if budget < 0.02:
            return 0
        self._note_switch("numvc", reason)
        before = self.incumbent.size

        def on_inc(name, clique, size, elapsed_ms, seed):
            wall = self._elapsed_ms()
            grew = self.incumbent.consider(clique, source="numvc_complement", discovery_time_ms=wall)
            ev = {
                "solver": "numvc_complement",
                "size": size,
                "elapsed_ms": wall,
                "slice_elapsed_ms": elapsed_ms,
                "grew_global": grew,
            }
            self.stats.events.append(ev)

        t_slice = time.perf_counter()
        cfg = NuMVCConfig(
            variant=NuMVCVariant.NUMVC_COMPLEMENT,
            timeout_seconds=budget,
            safety_margin_ms=0.0,
            # Same seed namespace as standalone numvc_complement for fair comparison.
            seed=self.seed + seed_offset,
            on_incumbent=on_inc,
        )
        res = solve_numvc(self.graph, cfg)
        wall_ms = (time.perf_counter() - t_slice) * 1000.0
        self.stats.numvc_init_ms += res.stats.complement_ms + res.stats.init_cover_ms
        self.stats.numvc_search_ms += max(0.0, wall_ms - (res.stats.complement_ms + res.stats.init_cover_ms))
        self.stats.numvc_slices += 1
        self.stats.numvc_best_size = max(self.stats.numvc_best_size, res.clique_size)
        tv = time.perf_counter()
        grew = self.incumbent.consider(
            res.clique, source="numvc_complement", discovery_time_ms=self._elapsed_ms()
        )
        self.stats.verification_ms += (time.perf_counter() - tv) * 1000.0
        if reason.startswith("probe"):
            self.stats.probe_count += 1
            if grew or self.incumbent.size > before:
                self.stats.successful_probe_count += 1
            else:
                self.stats.unsuccessful_probe_count += 1
        return self.incumbent.size - before

    def finalize(self, variant: str) -> PortfolioResult:
        out = self.incumbent.clique
        from .validation import is_clique, is_maximal_clique

        valid = is_clique(self.graph, out) if out else False
        maximal = is_maximal_clique(self.graph, out) if valid else False
        return PortfolioResult(
            clique=out,
            clique_size=len(out) if valid else 0,
            valid=valid,
            maximal=maximal,
            variant=variant,
            stats=self.stats,
            incumbent=self.incumbent.to_dict(),
            deadline_reached=time.perf_counter() >= self.safe_deadline,
            response_deadline_violation=time.perf_counter() > self.absolute_deadline,
            extras={
                "resumption_mode": "restart_based",
                "historical_access": False,
                "revo_best_size": self.stats.revo_best_size,
                "numvc_best_size": self.stats.numvc_best_size,
                "switches": self.stats.switches,
                "switch_reasons": list(self.stats.switch_reasons),
                "probe_count": self.stats.probe_count,
                "successful_probe_count": self.stats.successful_probe_count,
                "unsuccessful_probe_count": self.stats.unsuccessful_probe_count,
                "revo_active_ms": self.stats.revo_init_ms + self.stats.revo_search_ms,
                "numvc_active_ms": self.stats.numvc_init_ms + self.stats.numvc_search_ms,
                "events": self.stats.events,
            },
        )
