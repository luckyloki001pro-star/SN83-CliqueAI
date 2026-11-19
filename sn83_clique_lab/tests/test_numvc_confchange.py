"""Configuration checking semantics."""

from __future__ import annotations

import random

from clique.complement_graph import build_complement
from clique.graph import BitsetGraph
from clique.numvc_state import NuMVCState
from clique.numvc_weights import EdgeWeights


def test_initial_conf_all_true():
    g = BitsetGraph.from_edge_list(5, [(0, 1), (1, 2)])
    comp = build_complement(g)
    st = NuMVCState.create(comp, EdgeWeights.create(comp))
    assert all(st.conf_change)


def test_remove_sets_conf_false_and_neighbors_true():
    rng = random.Random(0)
    edges = [(i, j) for i in range(8) for j in range(i + 1, 8) if rng.random() < 0.5]
    g = BitsetGraph.from_edge_list(8, edges)
    comp = build_complement(g)
    st = NuMVCState.create(comp, EdgeWeights.create(comp))
    st.greedy_construct(rng)
    # pick a cover vertex with a complement neighbor
    v = next(v for v in range(comp.n) if st.in_cover[v] and comp.degree(v) > 0)
    neigh = []
    for e in comp.incident[v]:
        other = comp.edge_v[e] if comp.edge_u[e] == v else comp.edge_u[e]
        neigh.append(other)
    st.remove_vertex(v)
    assert st.conf_change[v] is False
    for z in neigh:
        assert st.conf_change[z] is True


def test_uncovered_edge_has_eligible_endpoint():
    """Proposition 1 style: after search moves, uncovered edges stay eligible."""
    rng = random.Random(7)
    edges = [(i, j) for i in range(12) for j in range(i + 1, 12) if rng.random() < 0.35]
    g = BitsetGraph.from_edge_list(12, edges)
    comp = build_complement(g)
    st = NuMVCState.create(comp, EdgeWeights.create(comp))
    st.greedy_construct(rng)
    for _ in range(40):
        if st.is_valid_cover():
            u = st.choose_remove_vertex(rng)
            st.remove_vertex(u)
            continue
        u = st.choose_remove_vertex(rng)
        st.remove_vertex(u)
        if len(st.uncovered) == 0:
            continue
        e = st.uncovered.sample(rng)
        a, b = comp.edge_u[e], comp.edge_v[e]
        assert st.conf_change[a] or st.conf_change[b]
        v = st.choose_add_endpoint(e, rng)
        st.add_vertex(v)
        st.apply_weight_increments()
