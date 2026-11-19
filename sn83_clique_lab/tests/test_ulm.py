import random

import pytest

from clique.coloring import greedy_color_candidates
from clique.exhaustive import exact_omega
from clique.graph import BitsetGraph
from clique.ulm import ULMReasoner


def _er(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    g = BitsetGraph.empty(n)
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p:
                g.add_edge(i, j)
    return g


def _conflict_prone() -> BitsetGraph:
    """
    Build a small graph whose coloring creates several independent sets
    that unit-propagate into conflicts (odd wheel-ish / Mycielski-ish).
    """
    # C5 + diagonals carefully: omega=2, chromatic number 3.
    g = BitsetGraph.empty(5, name="c5")
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)]
    for u, v in edges:
        g.add_edge(u, v)
    return g


@pytest.mark.parametrize("seed", list(range(20)))
def test_ulm_bound_soundness_random(seed: int):
    g = _er(12, 0.55, seed)
    cand = g.all_vertices_mask()
    coloring = greedy_color_candidates(g, cand)
    reasoner = ULMReasoner(g)
    res = reasoner.tighten_bound(coloring.color_classes, cand)
    omega = exact_omega(g)
    assert omega <= res.bound <= coloring.bound
    assert res.reduction == coloring.bound - res.bound
    assert res.reduction >= 0


def test_ulm_never_exceeds_coloring():
    g = _conflict_prone()
    coloring = greedy_color_candidates(g, g.all_vertices_mask())
    res = ULMReasoner(g).tighten_bound(coloring.color_classes, g.all_vertices_mask())
    assert res.bound <= coloring.bound
    assert exact_omega(g) <= res.bound


def test_ulm_on_complete_no_false_reduction():
    g = BitsetGraph.empty(5)
    for i in range(5):
        for j in range(i + 1, 5):
            g.add_edge(i, j)
    coloring = greedy_color_candidates(g, g.all_vertices_mask())
    res = ULMReasoner(g).tighten_bound(coloring.color_classes, g.all_vertices_mask())
    # Each color class is a singleton; no conflict among them as a clique
    # can pick one from each. Bound should remain n.
    assert res.bound == 5
    assert exact_omega(g) == 5


def test_ulm_disabled_on_demand():
    g = _er(10, 0.5, 0)
    r = ULMReasoner(g)
    r.disable("test")
    coloring = greedy_color_candidates(g, g.all_vertices_mask())
    res = r.tighten_bound(coloring.color_classes, g.all_vertices_mask())
    assert res.reduction == 0
    assert res.bound == coloring.bound
