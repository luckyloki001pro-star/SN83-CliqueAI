"""Exact neighborhood target search vs exhaustive oracle."""

from __future__ import annotations

import random
import time

from clique.bitset import list_to_mask
from clique.exhaustive import exact_max_clique, exact_omega
from clique.graph import BitsetGraph
from clique.neighborhood_exact import ExactStatus, search_max_clique_in_mask, search_target_clique
from clique.optimal_neighborhood import assemble_clique, build_neighborhood
from clique.validation import is_clique


def _induced(graph: BitsetGraph, verts: list[int]) -> BitsetGraph:
    idx = {v: i for i, v in enumerate(verts)}
    edges = []
    for i, u in enumerate(verts):
        for v in verts[i + 1 :]:
            if graph.has_edge(u, v):
                edges.append((i, idx[v]))
    return BitsetGraph.from_edge_list(len(verts), edges)


def test_target_finds_known_clique():
    edges = [(i, j) for i in range(6) for j in range(i + 1, 6)]  # K6
    g = BitsetGraph.from_edge_list(6, edges)
    res = search_target_clique(g, g.all_vertices_mask(), 6, time.perf_counter() + 1.0)
    assert res.status == ExactStatus.TARGET_FOUND
    assert res.clique_size >= 6
    assert is_clique(g, res.clique)


def test_proven_impossible_by_size():
    g = BitsetGraph.from_edge_list(4, [(0, 1), (1, 2)])
    res = search_target_clique(g, (1 << 3) - 1, 4, time.perf_counter() + 1.0)
    assert res.status == ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD


def test_matches_oracle_omega_on_random_small():
    rng = random.Random(0)
    for trial in range(12):
        n = rng.randint(8, 14)
        p = rng.uniform(0.2, 0.6)
        edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
        g = BitsetGraph.from_edge_list(n, edges)
        omega = exact_omega(g)
        # target = omega should succeed
        if omega >= 1:
            res = search_target_clique(
                g, g.all_vertices_mask(), omega, time.perf_counter() + 2.0
            )
            assert res.status == ExactStatus.TARGET_FOUND
            assert res.clique_size >= omega
        # target = omega+1 should prove impossible (complete)
        res2 = search_target_clique(
            g, g.all_vertices_mask(), omega + 1, time.perf_counter() + 2.0
        )
        assert res2.status == ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD


def test_max_search_matches_oracle():
    rng = random.Random(1)
    for _ in range(8):
        n = rng.randint(7, 12)
        edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.45]
        g = BitsetGraph.from_edge_list(n, edges)
        oracle = exact_max_clique(g)
        res = search_max_clique_in_mask(g, g.all_vertices_mask(), time.perf_counter() + 2.0)
        assert res.status != ExactStatus.TIMEOUT
        assert res.clique_size == len(oracle)
        assert is_clique(g, res.clique)


def test_neighborhood_repair_6for7_style():
    """Build a graph where removing 2 and adding 3 improves."""
    # Base clique 0..4 (K5). Vertices 5,6,7 form K3 with all of {0,1,2} but not 3,4.
    edges = [(i, j) for i in range(5) for j in range(i + 1, 5)]
    for v in (5, 6, 7):
        edges += [(v, 0), (v, 1), (v, 2)]
    edges += [(5, 6), (6, 7), (5, 7)]
    g = BitsetGraph.from_edge_list(8, edges)
    c = [0, 1, 2, 3, 4]
    nb = build_neighborhood(g, c, [3, 4])
    assert nb.feasible_for_improve
    res = search_target_clique(
        g, nb.candidate_mask, nb.target_size, time.perf_counter() + 1.0
    )
    assert res.status == ExactStatus.TARGET_FOUND
    assert res.clique_size >= 3
    new_c = assemble_clique(nb.fixed_mask, list_to_mask(res.clique))
    assert is_clique(g, new_c)
    assert len(new_c) >= 6  # 3 fixed + >=3


def test_timeout_not_claimed_proven():
    # Dense-ish graph with tiny deadline
    rng = random.Random(2)
    n = 18
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.7]
    g = BitsetGraph.from_edge_list(n, edges)
    res = search_target_clique(
        g, g.all_vertices_mask(), 12, time.perf_counter() + 0.0001, use_color_bound=True
    )
    assert res.status in (ExactStatus.TIMEOUT, ExactStatus.TARGET_FOUND, ExactStatus.PROVEN_NO_TARGET_IN_NEIGHBORHOOD)
    if res.status == ExactStatus.TIMEOUT:
        assert res.stats.interrupted >= 1
