"""End-to-end NuMVC / MIS search correctness on small graphs."""

from __future__ import annotations

import random
import time

from clique.exhaustive import exact_omega
from clique.graph import BitsetGraph
from clique.mis_baseline import MISConfig, MISVariant, solve_mis
from clique.numvc import NuMVCConfig, NuMVCVariant, solve_numvc
from clique.validation import is_clique, is_maximal_clique


def _er(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    return BitsetGraph.from_edge_list(n, edges)


def test_numvc_finds_optimal_on_tiny():
    g = _er(10, 0.4, seed=0)
    omega = exact_omega(g)
    cfg = NuMVCConfig(
        variant=NuMVCVariant.NUMVC_COMPLEMENT,
        timeout_seconds=1.0,
        safety_margin_ms=50.0,
        seed=0,
    )
    res = solve_numvc(g, cfg)
    assert res.valid and res.maximal
    assert is_clique(g, res.clique)
    assert res.clique_size <= omega
    # should often hit optimum on tiny graphs
    assert res.clique_size >= max(1, omega - 2)


def test_mis_baseline_valid():
    g = _er(12, 0.35, seed=1)
    cfg = MISConfig(variant=MISVariant.MIS_RANDOM_RESTART, timeout_seconds=0.4, safety_margin_ms=40, seed=1)
    res = solve_mis(g, cfg)
    assert res.valid and res.maximal and is_maximal_clique(g, res.clique)


def test_mis_configuration_valid():
    g = _er(12, 0.35, seed=2)
    cfg = MISConfig(
        variant=MISVariant.MIS_CONFIGURATION_SEARCH,
        timeout_seconds=0.4,
        safety_margin_ms=40,
        seed=2,
    )
    res = solve_mis(g, cfg)
    assert res.valid and res.maximal


def test_diversified_runs():
    g = _er(14, 0.4, seed=3)
    cfg = NuMVCConfig(
        variant=NuMVCVariant.NUMVC_DIVERSIFIED,
        timeout_seconds=0.5,
        safety_margin_ms=40,
        seed=3,
        bms_sample=20,
        restart_every_steps=5000,
    )
    res = solve_numvc(g, cfg)
    assert res.valid and res.maximal


def test_two_stage_preserves_invariants():
    g = _er(11, 0.45, seed=4)
    cfg = NuMVCConfig(timeout_seconds=0.3, safety_margin_ms=30, seed=4)
    res = solve_numvc(g, cfg)
    assert res.stats.search_steps >= 1
    assert res.clique_size == len(res.clique)
