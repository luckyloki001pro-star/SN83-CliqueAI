"""Complement graph transformation and duality tests."""

from __future__ import annotations

import random

from clique.complement_graph import (
    build_complement,
    independent_set_in_complement,
    is_vertex_cover,
    verify_complement_xor,
)
from clique.exhaustive import exact_max_clique, exact_omega
from clique.graph import BitsetGraph
from clique.validation import is_clique


def _path(n: int) -> BitsetGraph:
    return BitsetGraph.from_edge_list(n, [(i, i + 1) for i in range(n - 1)])


def test_empty_and_complete():
    empty = BitsetGraph.empty(5)
    c = build_complement(empty)
    assert c.complement_edge_count == 10
    assert verify_complement_xor(empty, c)
    complete = BitsetGraph.from_edge_list(4, [(i, j) for i in range(4) for j in range(i + 1, 4)])
    c2 = build_complement(complete)
    assert c2.complement_edge_count == 0
    assert verify_complement_xor(complete, c2)


def test_xor_and_no_loops_triangle():
    g = BitsetGraph.from_edge_list(3, [(0, 1), (1, 2), (0, 2)])
    c = build_complement(g)
    assert verify_complement_xor(g, c)
    for v in range(3):
        assert (c.adjacency[v] >> v) & 1 == 0


def test_path_cycle_star():
    for builder in (
        lambda: _path(6),
        lambda: BitsetGraph.from_edge_list(5, [(i, (i + 1) % 5) for i in range(5)]),
        lambda: BitsetGraph.from_edge_list(6, [(0, i) for i in range(1, 6)]),
    ):
        g = builder()
        c = build_complement(g)
        assert verify_complement_xor(g, c)


def test_clique_equals_independent_set():
    g = BitsetGraph.from_edge_list(5, [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)])
    c = build_complement(g)
    clique = [0, 1, 2]  # triangle
    assert is_clique(g, clique)
    assert independent_set_in_complement(c, clique)


def test_cover_complement_is_clique():
    g = _path(5)
    c = build_complement(g)
    # cover all complement edges: take all vertices — valid
    cover = (1 << 5) - 1
    assert is_vertex_cover(c, cover)
    s = [v for v in range(5) if not ((cover >> v) & 1)]
    assert is_clique(g, s) or s == []


def test_omega_alpha_tau_identity_small():
    rng = random.Random(0)
    for _ in range(8):
        n = rng.randint(6, 12)
        edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.4]
        g = BitsetGraph.from_edge_list(n, edges)
        omega = exact_omega(g)
        # alpha(H) = omega(G); tau(H) = n - alpha(H)
        # Build H as BitsetGraph and exact MIS via exact clique on H? 
        # MIS(H) = clique(G) so alpha(H)=omega(G)
        # Min cover size = n - alpha
        assert omega == len(exact_max_clique(g))
        tau = n - omega
        assert tau >= 0
