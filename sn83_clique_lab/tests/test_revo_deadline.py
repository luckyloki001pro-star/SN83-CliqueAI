"""Deadline / anytime behavior for R-EVO."""

from __future__ import annotations

import time

from clique.datasets import erdos_renyi
from clique.revo import RevoConfig, RevoVariant, solve_revo
from clique.solver import solve_graph


def test_no_hard_deadline_violation_short():
    g = erdos_renyi(80, 0.3, seed=8)
    timeout = 0.5
    t0 = time.perf_counter()
    r = solve_revo(
        g,
        RevoConfig(
            variant=RevoVariant.REVO_POPULATION,
            timeout_seconds=timeout,
            safety_margin_ms=100.0,
            seed=42,
            population_size=8,
            restart_factor=40,
        ),
    )
    wall = time.perf_counter() - t0
    assert r.valid and r.maximal
    assert not r.response_deadline_violation
    assert wall < timeout + 0.35  # allow small scheduling slack


def test_solver_wiring_revo_variants():
    g = erdos_renyi(30, 0.4, seed=2)
    for name in ("revo_no_model", "revo_population", "revo_diverse"):
        r = solve_graph(g, timeout_seconds=0.4, variant=name, seed=3, safety_margin_ms=50.0)
        assert r.valid and r.maximal
        assert r.clique_size >= 2
