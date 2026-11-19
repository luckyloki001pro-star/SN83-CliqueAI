"""Official SN83-style NetworkX approximation reference (Method R)."""

from __future__ import annotations

import time
from typing import List

import networkx as nx

from .graph import BitsetGraph
from .greedy import extend_to_maximal
from .solver import SolverResult
from .validation import is_clique, is_maximal_clique


def networkx_approximate_clique(graph: BitsetGraph) -> List[int]:
    """Mirror CliqueAI/clique_algorithms/networkx_algorithm.py."""
    adj_list = graph.to_adjacency_list()
    dict_of_lists = {i: adj_list[i] for i in range(graph.n)}
    g = nx.from_dict_of_lists(dict_of_lists)
    clique = list(nx.approximation.max_clique(g))
    return sorted(extend_to_maximal(graph, clique))


def solve_networkx_ref(
    graph: BitsetGraph,
    timeout_seconds: float = 30.0,
) -> SolverResult:
    t0 = time.perf_counter()
    clique = networkx_approximate_clique(graph)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # NetworkX approx has no cooperative deadline; record whether it
    # exceeded the simulated limit.
    deadline_reached = elapsed_ms > timeout_seconds * 1000.0
    valid = is_clique(graph, clique)
    maximal = is_maximal_clique(graph, clique) if valid else False
    return SolverResult(
        solver="networkx_approx",
        clique=clique,
        clique_size=len(clique),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        runtime_ms=elapsed_ms,
        search_nodes=0,
        deadline_reached=deadline_reached,
        extras={"note": "NetworkX approximation, not exact"},
    )
