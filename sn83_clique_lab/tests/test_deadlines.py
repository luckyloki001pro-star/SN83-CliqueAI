import time

from clique.datasets import erdos_renyi
from clique.solver import solve_graph


def test_deadline_returns_valid_maximal():
    g = erdos_renyi(80, 0.7, seed=7, name="deadline80")
    result = solve_graph(
        g,
        timeout_seconds=0.05,
        variant="baseline",
        seed=42,
        safety_margin_ms=10.0,
    )
    assert result.valid
    assert result.maximal
    assert result.clique_size >= 1
    # With a tiny timeout we expect deadline or a very fast finish.
    assert result.runtime_ms < 2000


def test_ulm_respects_deadline():
    g = erdos_renyi(60, 0.75, seed=3, name="deadline60")
    t0 = time.perf_counter()
    result = solve_graph(
        g,
        timeout_seconds=0.08,
        variant="selective_ulm",
        seed=1,
        safety_margin_ms=10.0,
    )
    elapsed = time.perf_counter() - t0
    assert result.valid and result.maximal
    assert elapsed < 2.0


def test_proven_optimal_on_tiny():
    from clique.graph import BitsetGraph

    g = BitsetGraph.empty(4)
    for i in range(4):
        for j in range(i + 1, 4):
            g.add_edge(i, j)
    result = solve_graph(g, timeout_seconds=2.0, variant="baseline")
    assert result.proven_optimal
    assert result.clique_size == 4
    assert not result.deadline_reached
