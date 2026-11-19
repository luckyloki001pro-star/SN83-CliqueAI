"""Deadline / fallback behavior for portfolio."""

from __future__ import annotations

import random
import time

from clique.graph import BitsetGraph
from clique.portfolio_scheduler import FixedSchedule, FixedScheduleConfig, run_fixed_schedule
from clique.validation import is_clique


def test_short_budget_valid_or_empty():
    rng = random.Random(0)
    g = BitsetGraph.from_edge_list(
        25, [(i, j) for i in range(25) for j in range(i + 1, 25) if rng.random() < 0.3]
    )
    for tl in (0.1, 0.5, 1.0):
        t0 = time.perf_counter()
        res = run_fixed_schedule(
            g,
            FixedScheduleConfig(
                schedule=FixedSchedule.REVO_80_NUMVC_20,
                timeout_seconds=tl,
                safety_margin_ms=30,
                seed=0,
            ),
        )
        assert time.perf_counter() - t0 < tl + 0.4
        assert not res.response_deadline_violation
        if res.clique:
            assert is_clique(g, res.clique)
            assert res.valid
