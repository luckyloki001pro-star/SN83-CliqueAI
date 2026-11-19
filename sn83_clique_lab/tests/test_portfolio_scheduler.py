"""Fixed schedule smoke tests."""

from __future__ import annotations

import random

from clique.adaptive_dual_portfolio import AdaptiveConfig, AdaptivePolicy, run_adaptive_portfolio
from clique.graph import BitsetGraph
from clique.portfolio_scheduler import FixedSchedule, FixedScheduleConfig, run_fixed_schedule
from clique.validation import is_clique, is_maximal_clique


def _er(n=30, p=0.35, seed=0):
    rng = random.Random(seed)
    return BitsetGraph.from_edge_list(
        n, [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    )


def test_fixed_80_20_valid():
    g = _er()
    cfg = FixedScheduleConfig(
        schedule=FixedSchedule.REVO_80_NUMVC_20,
        timeout_seconds=0.6,
        safety_margin_ms=50,
        seed=1,
        revo_first=True,
    )
    res = run_fixed_schedule(g, cfg)
    assert res.valid and res.maximal
    assert is_clique(g, res.clique)
    assert res.stats.revo_slices >= 1
    assert res.stats.numvc_slices >= 1


def test_order_numvc_first():
    g = _er(seed=2)
    cfg = FixedScheduleConfig(
        schedule=FixedSchedule.REVO_50_NUMVC_50,
        timeout_seconds=0.5,
        safety_margin_ms=40,
        seed=2,
        revo_first=False,
    )
    res = run_fixed_schedule(g, cfg)
    assert res.valid
    assert "numvc_first" in res.variant


def test_early_probe():
    g = _er(seed=3)
    res = run_adaptive_portfolio(
        g,
        AdaptiveConfig(
            policy=AdaptivePolicy.EARLY_PROBE,
            timeout_seconds=0.6,
            safety_margin_ms=50,
            seed=3,
            early_probe_seconds=0.15,
        ),
    )
    assert res.valid and is_maximal_clique(g, res.clique)
    assert res.extras.get("resumption_mode") == "restart_based"
