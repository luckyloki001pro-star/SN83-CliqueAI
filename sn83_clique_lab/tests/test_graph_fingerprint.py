"""Tests for graph fingerprinting utilities."""

from __future__ import annotations

import math
import random

from clique.datasets import erdos_renyi
from clique.graph import BitsetGraph
from clique.graph_fingerprint import (
    er_expected_count_threshold,
    er_log_expected_cliques,
    fingerprint_graph,
)


def test_er_log_expected_complete_graph():
    # p=1 → E[X_k] = C(n,k); log E for k=n is 0
    assert abs(er_log_expected_cliques(5, 1.0, 5) - 0.0) < 1e-9
    assert er_log_expected_cliques(5, 1.0, 3) > 0


def test_er_threshold_monotone_in_p():
    t_lo, _, _ = er_expected_count_threshold(100, 0.1)
    t_hi, _, _ = er_expected_count_threshold(100, 0.5)
    assert t_hi >= t_lo


def test_fingerprint_basic_properties():
    g = BitsetGraph.from_edge_list(4, [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)], name="c4diag")
    fp = fingerprint_graph(g, seed=0)
    assert fp.n == 4
    assert fp.m == 5
    assert abs(fp.density - 5 / 6) < 1e-9
    assert fp.min_degree >= 1
    assert fp.max_degree <= 3
    assert fp.fingerprint_ms >= 0
    assert 0.0 <= fp.sampled_triangle_density <= 1.0


def test_fingerprint_empty_and_complete():
    empty = BitsetGraph.empty(6, name="empty")
    fp0 = fingerprint_graph(empty, seed=1)
    assert fp0.density == 0.0
    assert fp0.m == 0

    edges = [(i, j) for i in range(5) for j in range(i + 1, 5)]
    complete = BitsetGraph.from_edge_list(5, edges, name="k5")
    fp1 = fingerprint_graph(complete, seed=1)
    assert abs(fp1.density - 1.0) < 1e-12
    assert fp1.er_expected_count_threshold == 5


def test_fingerprint_er_reproducible():
    g = erdos_renyi(40, 0.3, seed=7)
    a = fingerprint_graph(g, seed=42)
    b = fingerprint_graph(g, seed=42)
    assert a.sampled_triangle_density == b.sampled_triangle_density
    assert a.cn_edge_mean == b.cn_edge_mean


def test_log_expected_no_overflow():
    # large n should not overflow
    lg = er_log_expected_cliques(900, 0.2, 20)
    assert math.isfinite(lg)
