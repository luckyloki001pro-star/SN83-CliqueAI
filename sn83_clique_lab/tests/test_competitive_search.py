"""Correctness tests for Phase-3 competitive local search."""

from __future__ import annotations

import random

from clique.competitive_search import (
    CompetitiveConfig,
    CompetitiveVariant,
    compute_C0,
    compute_C1,
    solve_competitive,
)
from clique.exhaustive import exact_max_clique
from clique.graph import BitsetGraph
from clique.validation import is_clique, is_maximal_clique


def _er(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    return BitsetGraph.from_edge_list(n, edges, name=f"er_{n}_{seed}")


def test_C0_C1_definitions():
    # Triangle + pendant-style C1
    edges = [(0, 1), (0, 2), (1, 2), (0, 3), (1, 3)]  # 3 misses edge to 2
    g = BitsetGraph.from_edge_list(4, edges)
    c0 = compute_C0(g, [0, 1, 2])
    assert c0 == 0
    c1 = compute_C1(g, [0, 1, 2])
    assert any(w == 3 and conf == 2 for w, conf in c1)


def test_plateau_swap_preserves_size_and_validity():
    edges = [(0, 1), (0, 2), (1, 2), (0, 3), (1, 3)]
    g = BitsetGraph.from_edge_list(4, edges)
    clique = [0, 1, 2]
    c1 = compute_C1(g, clique)
    assert c1
    w, conf = next(x for x in c1 if x[0] == 3)
    nxt = [u for u in clique if u != conf] + [w]
    assert len(nxt) == len(clique)
    assert is_clique(g, nxt)


def test_all_competitive_variants_valid_small():
    g = _er(18, 0.4, 11)
    exact = exact_max_clique(g)
    for variant in CompetitiveVariant:
        cfg = CompetitiveConfig(
            variant=variant,
            seed=42,
            timeout_seconds=0.8,
            safety_margin_ms=100,
        )
        res = solve_competitive(g, cfg)
        assert res.valid and res.maximal
        assert res.clique_size <= len(exact)
        assert not res.stats.response_deadline_violation


def test_pls_records_plateau_or_adds():
    g = _er(24, 0.45, 5)
    cfg = CompetitiveConfig(
        variant=CompetitiveVariant.PLS_PENALTY,
        seed=1,
        timeout_seconds=1.0,
        safety_margin_ms=100,
    )
    res = solve_competitive(g, cfg)
    assert res.valid
    assert res.stats.add_moves + res.stats.plateau_moves >= 1


def test_bls_perturbation_keeps_clique_property_via_final():
    g = _er(20, 0.5, 9)
    cfg = CompetitiveConfig(
        variant=CompetitiveVariant.BLS_ADAPTIVE,
        seed=3,
        timeout_seconds=0.7,
        safety_margin_ms=80,
        bls_stagnation_limit=5,
    )
    res = solve_competitive(g, cfg)
    assert res.valid and res.maximal
    assert is_maximal_clique(g, res.clique)


def test_ikls_and_pair_and_portfolio_deadlines():
    g = _er(30, 0.35, 2)
    for variant in (
        CompetitiveVariant.IKLS_VARIABLE_DEPTH,
        CompetitiveVariant.PAIR_ANCHOR,
        CompetitiveVariant.ADAPTIVE_PORTFOLIO,
    ):
        cfg = CompetitiveConfig(variant=variant, seed=7, timeout_seconds=0.5, safety_margin_ms=50)
        res = solve_competitive(g, cfg)
        assert res.valid and res.maximal
        assert res.stats.total_ms < 800.0
