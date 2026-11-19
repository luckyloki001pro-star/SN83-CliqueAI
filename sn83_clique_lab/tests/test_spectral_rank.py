"""Numerical tests for centered adjacency + Lanczos."""

from __future__ import annotations

import math

from clique.graph import BitsetGraph
from clique.spectral_rank import centered_matvec, lanczos_centered, power_iteration_abs, rank_from_eigenvector


def test_centered_matvec_complete_graph():
    # K3 density=1 → B=0
    g = BitsetGraph.from_edge_list(3, [(0, 1), (1, 2), (0, 2)])
    x = [1.0, 0.0, -1.0]
    y = centered_matvec(g, x, p=1.0)
    assert all(abs(v) < 1e-12 for v in y)


def test_centered_matvec_empty():
    g = BitsetGraph.empty(3)
    x = [1.0, 2.0, 3.0]
    # B[i,j]= -0 = 0 for empty with p=0
    y = centered_matvec(g, x, p=0.0)
    assert all(abs(v) < 1e-12 for v in y)


def test_lanczos_path_graph():
    # Path 0-1-2-3; density small; should run and give finite residuals
    g = BitsetGraph.from_edge_list(4, [(0, 1), (1, 2), (2, 3)])
    res = lanczos_centered(g, max_iter=8, n_eigs=2)
    assert res.iterations >= 1
    assert len(res.eigenvalues) >= 1
    assert all(math.isfinite(e) for e in res.eigenvalues)
    assert all(r < 1.0 for r in res.residuals)  # loose residual bound


def test_rank_orientations():
    vec = [0.1, -2.0, 0.5, -0.01]
    assert rank_from_eigenvector(vec, "abs")[0] == 1
    assert rank_from_eigenvector(vec, "pos")[0] == 2
    assert rank_from_eigenvector(vec, "neg")[0] == 1


def test_power_notes_largest_abs():
    g = BitsetGraph.from_edge_list(5, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)])
    res = power_iteration_abs(g, max_iter=12)
    assert "note_largest_abs_not_necessarily_largest_algebraic" in res.extras


def test_planted_clique_signal_weak_ok():
    # Small planted K4 in sparse ER-like noise — just ensure valid run
    edges = [(i, j) for i in range(4) for j in range(i + 1, 4)]
    edges += [(0, 5), (1, 6), (2, 7), (5, 6)]
    g = BitsetGraph.from_edge_list(8, edges)
    res = lanczos_centered(g, max_iter=10, n_eigs=2)
    assert len(res.eigenvectors[0]) == 8
