"""Independent clique validation helpers."""

from __future__ import annotations

from typing import Sequence

from .bitset import list_to_mask
from .graph import BitsetGraph


def is_clique(graph: BitsetGraph, vertices: Sequence[int]) -> bool:
    if not vertices:
        return False
    seen = 0
    for v in vertices:
        if not (0 <= v < graph.n):
            return False
        bit = 1 << v
        if seen & bit:
            return False
        seen |= bit
    verts = list(vertices)
    for i, u in enumerate(verts):
        for v in verts[i + 1 :]:
            if not graph.has_edge(u, v):
                return False
    return True


def is_maximal_clique(graph: BitsetGraph, vertices: Sequence[int]) -> bool:
    if not is_clique(graph, vertices):
        return False
    clique_mask = list_to_mask(vertices)
    candidates = graph.all_vertices_mask() & ~clique_mask
    # A vertex can extend the clique iff it is adjacent to every clique member.
    common = candidates
    for v in vertices:
        common &= graph.adjacency[v]
        if common == 0:
            return True
    return common == 0


def validate_solution(graph: BitsetGraph, vertices: Sequence[int]) -> dict:
    valid = is_clique(graph, vertices)
    maximal = is_maximal_clique(graph, vertices) if valid else False
    return {
        "valid": valid,
        "maximal": maximal,
        "clique_size": len(vertices) if valid else 0,
        "duplicates": len(vertices) != len(set(vertices)),
        "out_of_range": any(not (0 <= v < graph.n) for v in vertices),
    }
