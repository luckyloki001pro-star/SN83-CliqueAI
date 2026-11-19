"""Correctness tests for Methods D/E/F anytime local search."""

from __future__ import annotations

import random

from clique.anytime_search import (
    AnytimeConfig,
    AnytimeVariant,
    greedy_construct,
    solve_anytime,
    try_1for2,
    try_2for3,
)
from clique.exhaustive import exact_max_clique
from clique.graph import BitsetGraph
from clique.validation import is_clique, is_maximal_clique


def _er(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p:
                edges.append((i, j))
    return BitsetGraph.from_edge_list(n, edges, name=f"er_{n}_{seed}")


def test_greedy_maximal_and_deterministic():
    g = _er(20, 0.4, 1)
    cfg = AnytimeConfig(seed=7, timeout_seconds=0.5, safety_margin_ms=50)
    rng = random.Random(7)
    c1 = greedy_construct(g, rng, 0, cfg, "rcl")
    rng2 = random.Random(7)
    c2 = greedy_construct(g, rng2, 0, cfg, "rcl")
    assert c1 == c2
    assert is_clique(g, c1)
    assert is_maximal_clique(g, c1)


def test_1for2_improves_or_none():
    # Diamond-like: clique {0,1,2} maximal? 3 connects to 0,1 not 2; 4 connects to 0,1 not 2
    # Better: C4 with diagonals — use planted clique
    edges = [
        (0, 1),
        (0, 2),
        (0, 3),
        (1, 2),
        (1, 3),
        (2, 3),  # K4 on 0-3
        (0, 4),
        (1, 4),
        (2, 4),
        (3, 4),  # K5
    ]
    g = BitsetGraph.from_edge_list(5, edges)
    # Start from suboptimal clique missing growth — take {0,1,2,3} size 4, already max
    # Construct a case where removing helps: clique {0,1,2} and outside 3,4 adjacent to {0,1} and each other
    # but 3,4 not to 2 — then remove 2, add 3,4
    edges2 = [
        (0, 1),
        (0, 2),
        (1, 2),  # triangle
        (0, 3),
        (1, 3),
        (0, 4),
        (1, 4),
        (3, 4),
    ]
    g2 = BitsetGraph.from_edge_list(5, edges2)
    rng = random.Random(0)
    improved = try_1for2(g2, [0, 1, 2], rng, first_improvement=True)
    assert improved is not None
    assert len(improved) == 4
    assert is_clique(g2, improved)


def test_2for3_triangle_requirement():
    # remaining after removing 2 verts must accept a triangle
    edges = [
        (0, 1),
        (0, 2),
        (0, 3),
        (0, 4),
        (0, 5),
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (2, 3),
        (3, 4),
        (3, 5),
        (4, 5),
    ]
    g = BitsetGraph.from_edge_list(6, edges)
    cfg = AnytimeConfig(max_2for3_remove_pairs=20, max_2for3_cand_scan=20)
    rng = random.Random(1)
    # clique [0,1,2] — remove 0,1 maybe add 3,4,5 if they form triangle with remaining [2]? 3,4,5 all connect to 2? 2-4 no
    out = try_2for3(g, [0, 1, 2], rng, cfg, deadline=1e100)
    if out is not None:
        assert len(out) == len([0, 1, 2]) + 1
        assert is_clique(g, out)


def test_anytime_variants_valid_on_small_graphs():
    g = _er(16, 0.35, 99)
    exact = exact_max_clique(g)
    for variant in AnytimeVariant:
        cfg = AnytimeConfig(
            variant=variant,
            seed=42,
            timeout_seconds=1.0,
            safety_margin_ms=100,
            enable_2for3=True,
        )
        res = solve_anytime(g, cfg)
        assert res.valid and res.maximal
        assert res.clique_size <= len(exact)
        assert not res.stats.response_deadline_violation


def test_deadline_returns_incumbent():
    g = _er(40, 0.5, 3)
    cfg = AnytimeConfig(
        variant=AnytimeVariant.SWAP_LOCAL_SEARCH,
        seed=1,
        timeout_seconds=0.2,
        safety_margin_ms=50,
    )
    res = solve_anytime(g, cfg)
    assert res.valid and res.maximal
    assert res.clique_size >= 1
    assert res.stats.total_ms <= 250.0  # soft margin slack for CI noise


def test_elite_and_seed_stability_size():
    g = _er(18, 0.45, 5)
    cfg = AnytimeConfig(
        variant=AnytimeVariant.MULTISTART_GREEDY,
        seed=123,
        timeout_seconds=0.5,
        safety_margin_ms=50,
    )
    a = solve_anytime(g, cfg)
    b = solve_anytime(g, cfg)
    assert a.clique == b.clique
