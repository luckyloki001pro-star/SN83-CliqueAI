"""Counterfactual scoring uses official calculator after solve."""

from __future__ import annotations

import random

from clique.graph import BitsetGraph
from clique.portfolio_scheduler import FixedSchedule, FixedScheduleConfig, run_fixed_schedule
from clique.sn83_scoring import CliqueScoreCalculator, GraphView


def test_score_after_solve():
    rng = random.Random(0)
    n = 20
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.4:
                adj[i].append(j)
                adj[j].append(i)
    g = BitsetGraph.from_adjacency_list(adj)
    res = run_fixed_schedule(
        g,
        FixedScheduleConfig(
            schedule=FixedSchedule.FULL_REVO,
            timeout_seconds=0.3,
            safety_margin_ms=40,
            seed=0,
        ),
    )
    view = GraphView(n, adj)
    hist = [[0, 1]] if g.has_edge(0, 1) else [res.clique]
    scored = CliqueScoreCalculator(view, 1.0, hist + [res.clique]).score_detailed()
    assert len(scored.rewards) == len(hist) + 1
