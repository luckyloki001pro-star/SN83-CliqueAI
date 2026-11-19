import random

import pytest

from clique.exhaustive import exact_max_clique, exact_omega
from clique.graph import BitsetGraph
from clique.greedy import greedy_maximal_from_start, multi_start_greedy
from clique.solver import solve_graph
from clique.validation import is_clique, is_maximal_clique, validate_solution


def _complete(n: int) -> BitsetGraph:
    g = BitsetGraph.empty(n, name=f"K{n}")
    for i in range(n):
        for j in range(i + 1, n):
            g.add_edge(i, j)
    return g


def _empty(n: int) -> BitsetGraph:
    return BitsetGraph.empty(n, name=f"empty{n}")


def _star(n: int) -> BitsetGraph:
    g = BitsetGraph.empty(n, name=f"star{n}")
    for i in range(1, n):
        g.add_edge(0, i)
    return g


def _path(n: int) -> BitsetGraph:
    g = BitsetGraph.empty(n, name=f"path{n}")
    for i in range(n - 1):
        g.add_edge(i, i + 1)
    return g


def _bipartite(a: int, b: int) -> BitsetGraph:
    g = BitsetGraph.empty(a + b, name=f"K{a},{b}")
    for i in range(a):
        for j in range(a, a + b):
            g.add_edge(i, j)
    return g


def _er(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    g = BitsetGraph.empty(n, name=f"er{n}_{seed}")
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p:
                g.add_edge(i, j)
    return g


def _planted(n: int, k: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    g = _er(n, p, seed)
    members = list(range(k))
    for i, u in enumerate(members):
        for v in members[i + 1 :]:
            g.add_edge(u, v)
    g.name = f"planted_n{n}_k{k}"
    return g


SMALL_GRAPHS = [
    _empty(5),
    _complete(1),
    _complete(5),
    _complete(8),
    _star(7),
    _path(8),
    _bipartite(3, 3),
    _bipartite(4, 2),
    BitsetGraph.from_edge_list(6, [(0, 1), (2, 3)], name="disconnected"),
    _er(10, 0.4, 1),
    _er(12, 0.7, 2),
    _er(14, 0.5, 3),
    _er(16, 0.6, 4),
    _planted(15, 5, 0.3, 5),
    _planted(18, 6, 0.35, 6),
]


@pytest.mark.parametrize("graph", SMALL_GRAPHS, ids=lambda g: g.name)
@pytest.mark.parametrize("variant", ["baseline", "ulm", "selective_ulm"])
def test_matches_exact_optimum(graph: BitsetGraph, variant: str):
    exact = exact_max_clique(graph)
    omega = len(exact)
    result = solve_graph(graph, timeout_seconds=5.0, variant=variant, seed=42)
    assert result.valid
    assert result.maximal
    assert result.clique_size == omega
    assert is_clique(graph, result.clique)
    assert is_maximal_clique(graph, result.clique)
    if result.proven_optimal:
        assert result.clique_size == omega


def test_greedy_produces_maximal():
    g = _er(20, 0.5, 9)
    clique, _ = multi_start_greedy(g, seed=1, restarts=5)
    assert is_maximal_clique(g, clique)
    c2 = greedy_maximal_from_start(g, 0)
    assert is_maximal_clique(g, c2)


def test_validation_rejects_non_clique():
    g = _path(4)
    v = validate_solution(g, [0, 2])
    assert not v["valid"]


def test_shared_api():
    from clique import solve_clique

    g = _complete(4)
    clique = solve_clique(g.to_adjacency_list(), timeout_seconds=1.0, variant="baseline")
    assert sorted(clique) == [0, 1, 2, 3]
