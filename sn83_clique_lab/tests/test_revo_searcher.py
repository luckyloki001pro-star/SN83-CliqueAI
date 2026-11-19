"""Tests for reactive searcher moves and guided restarts."""

from __future__ import annotations

import random

from clique.datasets import erdos_renyi
from clique.graph import BitsetGraph
from clique.revo_model import ProbabilityModel
from clique.revo_searcher import ReactiveSearcher
from clique.validation import is_clique, is_maximal_clique


def test_build_from_probability_is_maximal_clique():
    g = erdos_renyi(30, 0.4, seed=1)
    model = ProbabilityModel(n=g.n, initial=0.5)
    s = ReactiveSearcher(0, g, random.Random(42), use_model=True)
    c = s.build_from_probability(model)
    assert is_clique(g, c)
    assert is_maximal_clique(g, c)


def test_uniform_restart_when_no_model():
    g = erdos_renyi(25, 0.35, seed=2)
    s = ReactiveSearcher(1, g, random.Random(7), use_model=False)
    s.initialize_random()
    before = s.best_size
    s.restart(None)
    assert s.best_size >= before or s.best_size >= 2
    assert is_maximal_clique(g, s.verified_best())


def test_add_drop_preserve_clique_property():
    edges = [(i, j) for i in range(6) for j in range(i + 1, 6)]  # K6
    g = BitsetGraph.from_edge_list(8, edges + [(6, 0), (7, 1)])
    s = ReactiveSearcher(0, g, random.Random(3), tabu_ratio=0.2, restart_factor=1000)
    s.initialize_random()
    for _ in range(40):
        s.step()
        # current may be nonmaximal but must remain a clique if nonempty
        if s.current:
            assert is_clique(g, s.current)
    vb = s.verified_best()
    assert is_clique(g, vb) and is_maximal_clique(g, vb)


def test_tabu_blocks_immediate_reversal():
    g = erdos_renyi(20, 0.5, seed=4)
    s = ReactiveSearcher(0, g, random.Random(5), tabu_ratio=0.5, restart_factor=10**9)
    s.initialize_random()
    s.move_count = 10
    s.mark_tabu(3, tenure=5)
    assert s.is_tabu(3)
    s.move_count = 16
    assert not s.is_tabu(3)


def test_weighted_sampling_prefers_high_prob():
    # star-like: vertex 0 connected to all; others sparse
    n = 12
    edges = [(0, i) for i in range(1, n)]
    edges += [(1, 2), (2, 3)]
    g = BitsetGraph.from_edge_list(n, edges)
    model = ProbabilityModel(n=n, learning_rate=1.0, initial=0.01)
    model.probability = [0.01] * n
    model.probability[0] = 0.99
    s = ReactiveSearcher(0, g, random.Random(0), use_model=True)
    hits = 0
    for seed in range(30):
        s.rng = random.Random(seed)
        c = s.build_from_probability(model)
        if 0 in c:
            hits += 1
    assert hits >= 20


def test_stagnation_threshold_scales():
    g = BitsetGraph.empty(5)
    s = ReactiveSearcher(0, g, random.Random(1), restart_factor=100)
    s.best_size = 5
    assert s.restart_threshold() == 500
    s.stats.last_improvement_step = 0
    s.move_count = 500
    assert s.stagnated()
