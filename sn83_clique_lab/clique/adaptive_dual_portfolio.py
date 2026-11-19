"""Adaptive R-EVO + NuMVC dual portfolio (Phase 5C).

Policies (restart-based slices; no true pause/resume claimed):
  D1 stagnation_trigger — R-EVO then NuMVC probe on stagnation
  D2 early_probe — short NuMVC then remainder R-EVO
  D3 late_probe — R-EVO majority then late NuMVC
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .graph import BitsetGraph
from .portfolio_engine import DualPortfolioEngine, PortfolioResult
from .portfolio_scheduler import FixedSchedule, FixedScheduleConfig, run_fixed_schedule


class AdaptivePolicy(str, Enum):
    STAGNATION_TRIGGER = "stagnation_trigger"
    EARLY_PROBE = "early_probe"
    LATE_PROBE = "late_probe"
    # aliases for solver wiring
    ADAPTIVE_DUAL = "adaptive_dual_portfolio"
    FIXED_DUAL = "fixed_dual_portfolio"


@dataclass
class AdaptiveConfig:
    policy: AdaptivePolicy = AdaptivePolicy.EARLY_PROBE
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    seed: int = 42
    # D1
    stagnation_seconds: float = 1.0
    probe_seconds: float = 1.0
    max_probes: int = 2
    # D2
    early_probe_seconds: float = 0.5
    # D3
    late_numvc_fraction: float = 0.20
    # optional fixed schedule passthrough
    fixed_schedule: FixedSchedule = FixedSchedule.REVO_80_NUMVC_20
    revo_first: bool = True


def run_adaptive_portfolio(graph: BitsetGraph, config: AdaptiveConfig) -> PortfolioResult:
    if config.policy == AdaptivePolicy.FIXED_DUAL:
        return run_fixed_schedule(
            graph,
            FixedScheduleConfig(
                schedule=config.fixed_schedule,
                timeout_seconds=config.timeout_seconds,
                safety_margin_ms=config.safety_margin_ms,
                seed=config.seed,
                revo_first=config.revo_first,
            ),
        )

    t0 = time.perf_counter()
    absolute = t0 + config.timeout_seconds
    safe = absolute - config.safety_margin_ms / 1000.0
    usable = max(0.05, safe - t0)
    engine = DualPortfolioEngine(
        graph, seed=config.seed, absolute_deadline=absolute, safe_deadline=safe, t0=t0
    )

    if config.policy in (AdaptivePolicy.EARLY_PROBE, AdaptivePolicy.ADAPTIVE_DUAL):
        # Default adaptive = early probe (simple, interpretable)
        probe = min(config.early_probe_seconds, usable * 0.25)
        if probe >= 0.05:
            engine.run_numvc_slice(probe, reason="probe_early", seed_offset=0)
        rem = engine._remaining()
        if rem >= 0.05:
            engine.run_revo_slice(rem, reason="revo_after_early_probe", seed_offset=1)
        name = f"early_probe_{probe:.2f}s"

    elif config.policy == AdaptivePolicy.LATE_PROBE:
        revo_f = 1.0 - config.late_numvc_fraction
        revo_s = usable * revo_f
        numvc_s = usable * config.late_numvc_fraction
        if revo_s >= 0.05:
            engine.run_revo_slice(revo_s, reason="revo_before_late_probe")
        if engine._remaining() >= 0.05 and numvc_s >= 0.05:
            engine.run_numvc_slice(min(numvc_s, engine._remaining()), reason="probe_late")
        name = f"late_probe_{config.late_numvc_fraction:.2f}"

    elif config.policy == AdaptivePolicy.STAGNATION_TRIGGER:
        # Approximate stagnation: run R-EVO in chunks; if no global growth, probe NuMVC
        chunk = max(0.25, config.stagnation_seconds)
        probes = 0
        last_size = 0
        slice_i = 0
        while engine._remaining() >= 0.05:
            before = engine.incumbent.size
            spent = min(chunk, engine._remaining())
            engine.run_revo_slice(spent, reason="revo_chunk", seed_offset=slice_i)
            slice_i += 1
            grew = engine.incumbent.size > before
            if grew:
                last_size = engine.incumbent.size
            elif probes < config.max_probes and engine._remaining() >= 0.05:
                probe = min(config.probe_seconds, engine._remaining())
                engine.run_numvc_slice(probe, reason="probe_stagnation", seed_offset=probes)
                probes += 1
            # stop if almost no time left
            if engine._remaining() < 0.05:
                break
            # prevent infinite tiny loops
            if slice_i > 200:
                break
        # spend remainder on R-EVO
        if engine._remaining() >= 0.05:
            engine.run_revo_slice(engine._remaining(), reason="revo_remainder", seed_offset=999)
        name = f"stagnation_{config.stagnation_seconds:.1f}_probe_{config.probe_seconds:.1f}"
    else:
        raise ValueError(f"Unknown policy {config.policy}")

    res = engine.finalize(name)
    res.extras["policy"] = config.policy.value
    res.extras["usable_budget_ms"] = usable * 1000.0
    res.extras["total_runtime_ms"] = (time.perf_counter() - t0) * 1000.0
    res.extras["resumption_mode"] = "restart_based"
    return res


def solve_portfolio(
    graph: BitsetGraph,
    *,
    variant: str,
    timeout_seconds: float,
    seed: int = 42,
    safety_margin_ms: float = 500.0,
) -> PortfolioResult:
    """Public entry used by solver.py."""
    key = variant.strip().lower().replace("-", "_")
    if key in ("full_revo", "c0"):
        cfg = FixedScheduleConfig(
            schedule=FixedSchedule.FULL_REVO,
            timeout_seconds=timeout_seconds,
            safety_margin_ms=safety_margin_ms,
            seed=seed,
        )
        return run_fixed_schedule(graph, cfg)
    if key in ("full_numvc", "c1"):
        cfg = FixedScheduleConfig(
            schedule=FixedSchedule.FULL_NUMVC,
            timeout_seconds=timeout_seconds,
            safety_margin_ms=safety_margin_ms,
            seed=seed,
        )
        return run_fixed_schedule(graph, cfg)
    if key.startswith("revo_") and "_numvc_" in key:
        # e.g. revo_80_numvc_20 or revo_80_numvc_20_numvc_first
        revo_first = not key.endswith("numvc_first")
        base = key.replace("_numvc_first", "").replace("_revo_first", "")
        mapping = {
            "revo_90_numvc_10": FixedSchedule.REVO_90_NUMVC_10,
            "revo_80_numvc_20": FixedSchedule.REVO_80_NUMVC_20,
            "revo_70_numvc_30": FixedSchedule.REVO_70_NUMVC_30,
            "revo_60_numvc_40": FixedSchedule.REVO_60_NUMVC_40,
            "revo_50_numvc_50": FixedSchedule.REVO_50_NUMVC_50,
        }
        sched = mapping.get(base, FixedSchedule.REVO_80_NUMVC_20)
        return run_fixed_schedule(
            graph,
            FixedScheduleConfig(
                schedule=sched,
                timeout_seconds=timeout_seconds,
                safety_margin_ms=safety_margin_ms,
                seed=seed,
                revo_first=revo_first,
            ),
        )
    if key in ("early_probe", "adaptive_dual_portfolio", "adaptive_dual"):
        return run_adaptive_portfolio(
            graph,
            AdaptiveConfig(
                policy=AdaptivePolicy.EARLY_PROBE,
                timeout_seconds=timeout_seconds,
                safety_margin_ms=safety_margin_ms,
                seed=seed,
                early_probe_seconds=0.5,
            ),
        )
    if key.startswith("early_probe_"):
        # early_probe_1.0s
        try:
            sec = float(key.split("_")[-1].rstrip("s"))
        except ValueError:
            sec = 0.5
        return run_adaptive_portfolio(
            graph,
            AdaptiveConfig(
                policy=AdaptivePolicy.EARLY_PROBE,
                timeout_seconds=timeout_seconds,
                safety_margin_ms=safety_margin_ms,
                seed=seed,
                early_probe_seconds=sec,
            ),
        )
    if key in ("late_probe", "late_numvc"):
        return run_adaptive_portfolio(
            graph,
            AdaptiveConfig(
                policy=AdaptivePolicy.LATE_PROBE,
                timeout_seconds=timeout_seconds,
                safety_margin_ms=safety_margin_ms,
                seed=seed,
                late_numvc_fraction=0.20,
            ),
        )
    if key in ("stagnation_trigger", "stagnation"):
        return run_adaptive_portfolio(
            graph,
            AdaptiveConfig(
                policy=AdaptivePolicy.STAGNATION_TRIGGER,
                timeout_seconds=timeout_seconds,
                safety_margin_ms=safety_margin_ms,
                seed=seed,
                stagnation_seconds=1.0,
                probe_seconds=1.0,
            ),
        )
    # default
    return run_adaptive_portfolio(
        graph,
        AdaptiveConfig(
            policy=AdaptivePolicy.EARLY_PROBE,
            timeout_seconds=timeout_seconds,
            safety_margin_ms=safety_margin_ms,
            seed=seed,
        ),
    )
