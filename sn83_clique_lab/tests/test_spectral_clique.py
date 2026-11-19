"""Clique validity tests for spectral solvers."""

from __future__ import annotations

from clique.datasets import erdos_renyi
from clique.graph import BitsetGraph
from clique.solver import solve_graph
from clique.spectral_clique import SpectralConfig, SpectralVariant, greedy_from_order
from clique.spectral_solve import solve_spectral
from clique.validation import is_clique, is_maximal_clique


def test_greedy_from_order_is_clique():
    g = BitsetGraph.from_edge_list(5, [(0, 1), (1, 2), (0, 2), (2, 3), (3, 4)])
    order = [0, 1, 2, 3, 4]
    c = greedy_from_order(g, order, start_v=0)
    assert is_clique(g, c)
    assert is_maximal_clique(g, c)


def test_global_spectral_valid_on_er():
    g = erdos_renyi(40, 0.35, seed=3, name="er40")
    cfg = SpectralConfig(
        variant=SpectralVariant.GLOBAL_SPECTRAL,
        timeout_seconds=1.0,
        safety_margin_ms=100.0,
        seed=42,
        lanczos_iters=8,
        n_starts=16,
    )
    res = solve_spectral(g, cfg)
    assert res.valid and res.maximal
    assert res.clique_size >= 2
    assert not res.response_deadline_violation


def test_anchored_spectral_valid():
    g = erdos_renyi(50, 0.4, seed=5, name="er50")
    cfg = SpectralConfig(
        variant=SpectralVariant.ANCHORED_SPECTRAL,
        timeout_seconds=1.2,
        safety_margin_ms=100.0,
        seed=7,
        pair_top_k=8,
        lanczos_iters=8,
    )
    res = solve_spectral(g, cfg)
    assert res.valid and res.maximal
    assert res.stats.pair_starts >= 1


def test_solver_wiring_spectral_recovery():
    g = erdos_renyi(30, 0.45, seed=1)
    r = solve_graph(g, timeout_seconds=0.8, variant="spectral_recovery", seed=42, safety_margin_ms=100.0)
    assert r.valid and r.maximal
    assert r.clique_size >= 2


def test_planted_clique_recovery_size():
    # Plant K8 in n=60 background p=0.15
    n, k = 60, 8
    import random

    rng = random.Random(11)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.15]
    for i in range(k):
        for j in range(i + 1, k):
            edges.append((i, j))
    g = BitsetGraph.from_edge_list(n, edges, name="planted")
    r = solve_graph(g, timeout_seconds=2.0, variant="anchored_spectral", seed=42, safety_margin_ms=200.0)
    assert r.valid and r.maximal
    # Should find at least the planted size often; allow heuristic miss but require >= 5
    assert r.clique_size >= 5
