"""Exact maximum-clique oracle for small graphs."""

from __future__ import annotations

from typing import List

from .bitset import bits_to_list
from .graph import BitsetGraph


def exact_max_clique(graph: BitsetGraph) -> List[int]:
    """
    Exhaustive Bron-Kerbosch-style search with bitsets.

    Intended for n <= ~20–22. Not for SN83-scale graphs.
    """
    if graph.n == 0:
        return []
    adj = graph.adjacency
    best: List[int] = []

    def bk(r: List[int], p: int, x: int) -> None:
        nonlocal best
        if p == 0 and x == 0:
            if len(r) > len(best):
                best = list(r)
            return
        # Simple pivot: first vertex in p|x
        ux = p | x
        if ux == 0:
            return
        u = (ux & -ux).bit_length() - 1
        # Candidates: P \ N(u)
        cand = p & ~adj[u]
        tmp = cand
        while tmp:
            bit = tmp & -tmp
            v = bit.bit_length() - 1
            tmp ^= bit
            r.append(v)
            bk(r, p & adj[v], x & adj[v])
            r.pop()
            p &= ~bit
            x |= bit

    bk([], graph.all_vertices_mask(), 0)
    return sorted(best)


def exact_omega(graph: BitsetGraph) -> int:
    return len(exact_max_clique(graph))
