"""Fixed dual-solver schedules (Phase 5C C0–C6)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .graph import BitsetGraph
from .portfolio_engine import DualPortfolioEngine, PortfolioResult


class FixedSchedule(str, Enum):
    FULL_REVO = "full_revo"
    FULL_NUMVC = "full_numvc"
    REVO_90_NUMVC_10 = "revo_90_numvc_10"
    REVO_80_NUMVC_20 = "revo_80_numvc_20"
    REVO_70_NUMVC_30 = "revo_70_numvc_30"
    REVO_60_NUMVC_40 = "revo_60_numvc_40"
    REVO_50_NUMVC_50 = "revo_50_numvc_50"


SCHEDULE_SPLITS = {
    FixedSchedule.FULL_REVO: (1.0, 0.0),
    FixedSchedule.FULL_NUMVC: (0.0, 1.0),
    FixedSchedule.REVO_90_NUMVC_10: (0.90, 0.10),
    FixedSchedule.REVO_80_NUMVC_20: (0.80, 0.20),
    FixedSchedule.REVO_70_NUMVC_30: (0.70, 0.30),
    FixedSchedule.REVO_60_NUMVC_40: (0.60, 0.40),
    FixedSchedule.REVO_50_NUMVC_50: (0.50, 0.50),
}


@dataclass
class FixedScheduleConfig:
    schedule: FixedSchedule = FixedSchedule.REVO_80_NUMVC_20
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    seed: int = 42
    # True: R-EVO first; False: NuMVC first
    revo_first: bool = True


def run_fixed_schedule(graph: BitsetGraph, config: FixedScheduleConfig) -> PortfolioResult:
    t0 = time.perf_counter()
    absolute = t0 + config.timeout_seconds
    safe = absolute - config.safety_margin_ms / 1000.0
    usable = max(0.05, safe - t0)
    revo_f, numvc_f = SCHEDULE_SPLITS[config.schedule]
    engine = DualPortfolioEngine(
        graph, seed=config.seed, absolute_deadline=absolute, safe_deadline=safe, t0=t0
    )
    revo_s = usable * revo_f
    numvc_s = usable * numvc_f

    if config.schedule == FixedSchedule.FULL_REVO:
        engine.run_revo_slice(usable, reason="full_revo")
    elif config.schedule == FixedSchedule.FULL_NUMVC:
        engine.run_numvc_slice(usable, reason="full_numvc")
    elif config.revo_first:
        if revo_s > 0.02:
            engine.run_revo_slice(revo_s, reason="fixed_revo_first")
        if numvc_s > 0.02 and engine._remaining() > 0.02:
            engine.run_numvc_slice(min(numvc_s, engine._remaining()), reason="fixed_numvc_second")
    else:
        if numvc_s > 0.02:
            engine.run_numvc_slice(numvc_s, reason="fixed_numvc_first")
        if revo_s > 0.02 and engine._remaining() > 0.02:
            engine.run_revo_slice(min(revo_s, engine._remaining()), reason="fixed_revo_second")

    name = config.schedule.value
    if config.schedule not in (FixedSchedule.FULL_REVO, FixedSchedule.FULL_NUMVC):
        name = f"{name}_{'revo_first' if config.revo_first else 'numvc_first'}"
    res = engine.finalize(name)
    res.extras["usable_budget_ms"] = usable * 1000.0
    res.extras["revo_fraction"] = revo_f
    res.extras["numvc_fraction"] = numvc_f
    res.extras["revo_first"] = config.revo_first
    res.extras["total_runtime_ms"] = (time.perf_counter() - t0) * 1000.0
    return res
