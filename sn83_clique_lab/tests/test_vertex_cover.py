"""Vertex-cover validity and cover→clique conversion."""

from __future__ import annotations

import random

from clique.complement_graph import build_complement, is_vertex_cover
from clique.graph import BitsetGraph
from clique.numvc import _cover_to_maximal_clique
from clique.numvc_state import NuMVCState
from clique.numvc_weights import EdgeWeights
from clique.validation import is_clique, is_maximal_clique


def test_greedy_construct_valid_cover():
    rng = random.Random(1)
    edges = [(i, j) for i in range(10) for j in range(i + 1, 10) if rng.random() < 0.35]
    g = BitsetGraph.from_edge_list(10, edges)
    comp = build_complement(g)
    w = EdgeWeights.create(comp)
    st = NuMVCState.create(comp, w)
    st.greedy_construct(rng)
    assert st.is_valid_cover()
    assert is_vertex_cover(comp, st.cover_mask())


def test_cover_to_clique_maximal():
    rng = random.Random(2)
    edges = [(i, j) for i in range(12) for j in range(i + 1, 12) if rng.random() < 0.5]
    g = BitsetGraph.from_edge_list(12, edges)
    comp = build_complement(g)
    w = EdgeWeights.create(comp)
    st = NuMVCState.create(comp, w)
    st.greedy_construct(rng)
    clique = _cover_to_maximal_clique(g, st.cover_mask())
    assert is_clique(g, clique)
    assert is_maximal_clique(g, clique)
    assert len(clique) == g.n - st.cover_size or len(clique) >= g.n - st.cover_size


def test_empty_complement_cover():
    g = BitsetGraph.from_edge_list(4, [(i, j) for i in range(4) for j in range(i + 1, 4)])
    comp = build_complement(g)
    assert comp.complement_edge_count == 0
    assert is_vertex_cover(comp, 0)
