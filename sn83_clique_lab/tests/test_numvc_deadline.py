"""Deadline / anytime behavior for NuMVC."""

from __future__ import annotations

import random
import time

from clique.graph import BitsetGraph
from clique.numvc import NuMVCConfig, NuMVCVariant, solve_numvc
from clique.validation import is_clique, is_maximal_clique


def test_short_deadline_valid_fallback():
    rng = random.Random(9)
    n = 40
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.3]
    g = BitsetGraph.from_edge_list(n, edges)
    cfg = NuMVCConfig(
        variant=NuMVCVariant.NUMVC_COMPLEMENT,
        timeout_seconds=0.25,
        safety_margin_ms=40.0,
        seed=9,
    )
    t0 = time.perf_counter()
    res = solve_numvc(g, cfg)
    elapsed = time.perf_counter() - t0
    assert elapsed < cfg.timeout_seconds + 0.5
    assert not res.response_deadline_violation
    assert res.valid
    assert is_clique(g, res.clique)
    assert is_maximal_clique(g, res.clique)


def test_complete_graph_fast():
    g = BitsetGraph.from_edge_list(6, [(i, j) for i in range(6) for j in range(i + 1, 6)])
    cfg = NuMVCConfig(timeout_seconds=0.2, safety_margin_ms=20, seed=0)
    res = solve_numvc(g, cfg)
    assert res.clique_size == 6
    assert res.proven_optimal
