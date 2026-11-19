"""Shared incumbent acceptance rules."""

from __future__ import annotations

from clique.graph import BitsetGraph
from clique.portfolio_incumbent import SharedIncumbent
from clique.validation import is_maximal_clique


def test_larger_replaces_smaller():
    # Two disjoint edges + a triangle elsewhere so sizes differ without auto-extend collision
    edges = [(0, 1), (2, 3), (2, 4), (3, 4)]
    g = BitsetGraph.from_edge_list(5, edges)
    inc = SharedIncumbent(g)
    assert inc.consider([0, 1], source="a", discovery_time_ms=1.0)
    assert inc.size == 2
    assert inc.consider([2, 3, 4], source="b", discovery_time_ms=2.0)
    assert inc.size == 3
    assert inc.best.source == "b"


def test_smaller_never_replaces():
    g = BitsetGraph.from_edge_list(4, [(i, j) for i in range(4) for j in range(i + 1, 4)])
    inc = SharedIncumbent(g)
    inc.consider(list(range(4)), source="a", discovery_time_ms=1.0)
    grew = inc.consider([0, 1], source="b", discovery_time_ms=2.0)
    assert not grew
    assert inc.size == 4


def test_equal_size_elite():
    # path: many size-2 cliques
    g = BitsetGraph.from_edge_list(4, [(0, 1), (1, 2), (2, 3)])
    inc = SharedIncumbent(g)
    inc.consider([0, 1], source="a", discovery_time_ms=1.0)
    inc.consider([2, 3], source="b", discovery_time_ms=2.0)
    assert inc.size == 2
    assert len(inc.elite) >= 2
    assert is_maximal_clique(g, inc.clique)
