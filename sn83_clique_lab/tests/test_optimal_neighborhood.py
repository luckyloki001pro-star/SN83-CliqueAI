"""Tests for F/R/H neighborhood construction and conflict-union repair."""

from __future__ import annotations

from clique.graph import BitsetGraph
from clique.optimal_neighborhood import (
    build_neighborhood,
    conflict_mask,
    conflict_union,
    repair_from_outside_set,
)
from clique.validation import is_clique


def _k(n: int) -> BitsetGraph:
    edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
    return BitsetGraph.from_edge_list(n, edges)


def test_r_subset_of_h_on_clique():
    g = _k(8)
    c = list(range(6))
    nb = build_neighborhood(g, c, [4, 5])
    assert nb.r_subset_of_h
    assert nb.fixed_count == 4
    assert nb.removed_count == 2
    assert nb.feasible_for_improve  # H includes at least removed verts + maybe more
    assert nb.candidate_count >= 2


def test_early_reject_when_h_too_small():
    # Path: clique of size 1 only useful; make sparse
    g = BitsetGraph.from_edge_list(5, [(0, 1), (1, 2)])
    c = [0, 1]
    nb = build_neighborhood(g, c, [0, 1])  # remove all → H = V
    assert nb.fixed_count == 0
    # remove one from triangle-free clique of 2
    nb2 = build_neighborhood(g, c, [1])
    # F={0}, H=N(0)\{0}={1} only size 1; r+1=2 → infeasible
    assert nb2.candidate_count == 1
    assert not nb2.feasible_for_improve


def test_assemble_improves_when_q_larger():
    # K5 on 0..4 plus vertex 5 connected to 0,1,2 (not 3,4)
    edges = [(i, j) for i in range(5) for j in range(i + 1, 5)]
    edges += [(5, 0), (5, 1), (5, 2)]
    g = BitsetGraph.from_edge_list(6, edges)
    c = [0, 1, 2, 3, 4]
    nb = build_neighborhood(g, c, [3, 4])
    # H should include 3,4,5
    assert nb.candidate_count >= 3
    assert nb.target_size == 3


def test_conflict_mask():
    edges = [(i, j) for i in range(4) for j in range(i + 1, 4)]
    edges += [(4, 0), (4, 1)]  # 4 conflicts with 2,3
    g = BitsetGraph.from_edge_list(5, edges)
    c_mask = (1 << 4) - 1
    cm = conflict_mask(g, c_mask, 4)
    assert cm.bit_count() == 2
    assert (cm >> 2) & 1 and (cm >> 3) & 1


def test_conflict_union_improvement():
    # C = {0,1,2,3}; outside 4,5 adjacent; both conflict only with {2,3}
    edges = [(i, j) for i in range(4) for j in range(i + 1, 4)]
    edges += [(4, 0), (4, 1), (5, 0), (5, 1), (4, 5)]
    g = BitsetGraph.from_edge_list(6, edges)
    c = [0, 1, 2, 3]
    # |A|=2, |R|=2 → not improving
    assert repair_from_outside_set(g, c, [4, 5]) is None
    # add 6 also conflicting only with 2,3 and clique with 4,5
    g2 = BitsetGraph.from_edge_list(
        7,
        edges + [(6, 0), (6, 1), (6, 4), (6, 5)],
    )
    res = repair_from_outside_set(g2, c, [4, 5, 6])
    assert res is not None
    new_c, a_sz, r_sz = res
    assert a_sz == 3 and r_sz == 2
    assert len(new_c) == 5  # (C\R)∪A = 2+3
    assert is_clique(g2, new_c)
