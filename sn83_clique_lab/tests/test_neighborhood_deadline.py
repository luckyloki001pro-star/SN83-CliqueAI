"""Deadline / fallback behavior for ONE and exact neighborhood search."""

from __future__ import annotations

import random
import time

from clique.graph import BitsetGraph
from clique.neighborhood_exact import ExactStatus, search_target_clique
from clique.one_repair import OneConfig, OneVariant, solve_one
from clique.validation import is_clique, is_maximal_clique


def _er(n: int, p: float, seed: int = 0) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    return BitsetGraph.from_edge_list(n, edges)


def test_exact_timeout_not_proven():
    g = _er(20, 0.75, seed=3)
    res = search_target_clique(
        g, g.all_vertices_mask(), 14, time.perf_counter() + 1e-5
    )
    if res.status == ExactStatus.TIMEOUT:
        assert res.stats.interrupted >= 1
        assert res.status != ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD


def test_one_respects_hard_deadline_and_returns_maximal():
    g = _er(40, 0.35, seed=5)
    cfg = OneConfig(
        variant=OneVariant.ONE_RANDOM_REPAIR,
        timeout_seconds=0.35,
        safety_margin_ms=50.0,
        seed=1,
        revo_fraction=0.55,
        max_neighborhood_budget_ms=20.0,
    )
    t0 = time.perf_counter()
    res = solve_one(g, cfg)
    elapsed = time.perf_counter() - t0
    assert elapsed < cfg.timeout_seconds + 0.25
    assert not res.response_deadline_violation
    assert res.valid
    assert is_clique(g, res.clique)
    assert is_maximal_clique(g, res.clique)
    assert res.clique_size >= 1


def test_one_fallback_when_repair_starved():
    g = _er(30, 0.4, seed=7)
    cfg = OneConfig(
        variant=OneVariant.ONE_CONFLICT_REPAIR,
        timeout_seconds=0.25,
        safety_margin_ms=40.0,
        seed=2,
        revo_fraction=0.9,
        max_neighborhood_budget_ms=10.0,
    )
    res = solve_one(g, cfg)
    assert res.valid and res.maximal
