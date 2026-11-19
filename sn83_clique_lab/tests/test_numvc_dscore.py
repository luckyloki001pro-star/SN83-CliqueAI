"""Incremental dscore vs full recomputation."""

from __future__ import annotations

import random

from clique.complement_graph import build_complement
from clique.graph import BitsetGraph
from clique.numvc_state import NuMVCState
from clique.numvc_weights import EdgeWeights


def test_dscore_matches_scratch_after_random_moves():
    rng = random.Random(3)
    edges = [(i, j) for i in range(15) for j in range(i + 1, 15) if rng.random() < 0.4]
    g = BitsetGraph.from_edge_list(15, edges)
    comp = build_complement(g)
    w = EdgeWeights.create(comp)
    st = NuMVCState.create(comp, w)
    st.greedy_construct(rng)
    for _ in range(80):
        if st.cover_size == 0:
            break
        if rng.random() < 0.5 and st.cover_size > 0:
            # remove random cover vertex
            vs = [v for v in range(comp.n) if st.in_cover[v]]
            st.remove_vertex(rng.choice(vs))
        else:
            outs = [v for v in range(comp.n) if not st.in_cover[v]]
            if outs:
                st.add_vertex(rng.choice(outs))
        incremental = list(st.dscore)
        scratch = st.recompute_dscore_from_scratch()
        assert incremental == scratch


def test_weight_increment_updates_dscore():
    rng = random.Random(4)
    g = BitsetGraph.from_edge_list(8, [(0, 1), (2, 3), (4, 5)])
    comp = build_complement(g)
    w = EdgeWeights.create(comp)
    st = NuMVCState.create(comp, w)
    # empty cover: all edges uncovered
    before = list(st.dscore)
    st.apply_weight_increments()
    after = list(st.dscore)
    # endpoints of uncovered edges should increase
    assert any(after[v] > before[v] for v in range(comp.n))
    scratch = st.recompute_dscore_from_scratch()
    assert after == scratch


def test_forgetting_recomputes():
    rng = random.Random(5)
    edges = [(i, j) for i in range(10) for j in range(i + 1, 10) if rng.random() < 0.3]
    g = BitsetGraph.from_edge_list(10, edges)
    comp = build_complement(g)
    w = EdgeWeights.create(comp, gamma=1.0, rho=0.3)  # low gamma → forget soon
    st = NuMVCState.create(comp, w)
    for _ in range(50):
        st.apply_weight_increments()
        st.apply_forgetting_if_needed()
    assert st.dscore == st.recompute_dscore_from_scratch()
