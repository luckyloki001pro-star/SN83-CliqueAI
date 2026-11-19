"""Conflict-guided removable sets and conflict-union clique repairs."""

from __future__ import annotations

import random

from clique.graph import BitsetGraph
from clique.neighborhood_selector import conflict_guided_removals
from clique.optimal_neighborhood import repair_from_outside_set
from clique.validation import is_clique


def test_conflict_proposals_produce_valid_removals():
    # C = K6 on 0..5
    edges = [(i, j) for i in range(6) for j in range(i + 1, 6)]
    # 6 adjacent to 0,1,2,3 — conflicts with 4,5
    edges += [(6, 0), (6, 1), (6, 2), (6, 3)]
    # 7 adjacent to 0,1,2,4 — conflicts with 3,5
    edges += [(7, 0), (7, 1), (7, 2), (7, 4)]
    # 8 adjacent to 0,1,2,5 — conflicts with 3,4
    edges += [(8, 0), (8, 1), (8, 2), (8, 5)]
    edges += [(6, 7), (7, 8), (6, 8)]
    g = BitsetGraph.from_edge_list(9, edges)
    c = list(range(6))
    props = conflict_guided_removals(g, c, random.Random(0), max_proposals=16)
    assert props
    rem_sets = [set(p.remove) for p in props]
    assert any(len(s) >= 1 for s in rem_sets)
    # Triple seed should suggest removing {3,4,5}
    assert any(s == {3, 4, 5} for s in rem_sets)


def test_conflict_union_grows_clique():
    edges = [(i, j) for i in range(4) for j in range(i + 1, 4)]
    edges += [(4, 0), (4, 1), (5, 0), (5, 1), (6, 0), (6, 1)]
    edges += [(4, 5), (5, 6), (4, 6)]
    g = BitsetGraph.from_edge_list(7, edges)
    c = [0, 1, 2, 3]
    res = repair_from_outside_set(g, c, [4, 5, 6])
    assert res is not None
    new_c, a, r = res
    assert a > r
    assert len(new_c) > len(c)
    assert is_clique(g, new_c)
