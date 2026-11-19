"""Complement graph construction for clique ↔ MIS / MVC duality.

H = complement(G): edge (u,v) in H iff u≠v and (u,v) not in G.
A clique in G is an independent set in H.
A min vertex cover C of H yields clique S = V\\C in G with |S| = n - |C|.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .bitset import full_mask
from .graph import BitsetGraph


@dataclass
class ComplementGraph:
    """Complement of an original BitsetGraph with compact edge indexing."""

    n: int
    adjacency: List[int]  # complement adj bitsets
    # Edge table: edge e has endpoints (u[e], v[e]) with u < v
    edge_u: List[int] = field(default_factory=list)
    edge_v: List[int] = field(default_factory=list)
    # incident edge ids per vertex
    incident: List[List[int]] = field(default_factory=list)
    original_edge_count: int = 0
    complement_edge_count: int = 0
    complement_density: float = 0.0
    build_time_ms: float = 0.0
    original: BitsetGraph | None = None

    def has_edge(self, u: int, v: int) -> bool:
        if u == v:
            return False
        return (self.adjacency[u] >> v) & 1 == 1

    def degree(self, v: int) -> int:
        return self.adjacency[v].bit_count()

    def all_vertices_mask(self) -> int:
        return full_mask(self.n)

    def as_bitset_graph(self) -> BitsetGraph:
        return BitsetGraph(n=self.n, adjacency=list(self.adjacency), name="complement")


def build_complement(graph: BitsetGraph) -> ComplementGraph:
    """Build complement with edge list and incident indices."""
    t0 = time.perf_counter()
    n = graph.n
    full = full_mask(n)
    orig_edges = graph.edge_count()
    adj: List[int] = [0] * n
    edge_u: List[int] = []
    edge_v: List[int] = []
    incident: List[List[int]] = [[] for _ in range(n)]

    for u in range(n):
        # complement neighbors: everyone except self and G-neighbors
        cmask = full & ~graph.adjacency[u] & ~(1 << u)
        adj[u] = cmask

    # Build undirected edge list once (u < v)
    for u in range(n):
        tmp = adj[u]
        # only higher neighbors
        higher = tmp & ~((1 << (u + 1)) - 1) if u + 1 < n else 0
        # clearer: iterate bits > u
        m = tmp
        while m:
            bit = m & -m
            v = bit.bit_length() - 1
            m ^= bit
            if v <= u:
                continue
            eid = len(edge_u)
            edge_u.append(u)
            edge_v.append(v)
            incident[u].append(eid)
            incident[v].append(eid)

    m_edges = len(edge_u)
    possible = n * (n - 1) // 2 if n > 1 else 0
    dens = (m_edges / possible) if possible else 0.0
    return ComplementGraph(
        n=n,
        adjacency=adj,
        edge_u=edge_u,
        edge_v=edge_v,
        incident=incident,
        original_edge_count=orig_edges,
        complement_edge_count=m_edges,
        complement_density=dens,
        build_time_ms=(time.perf_counter() - t0) * 1000.0,
        original=graph,
    )


def verify_complement_xor(graph: BitsetGraph, comp: ComplementGraph) -> bool:
    """edge_G XOR edge_H for all pairs; no self-loops; symmetry."""
    n = graph.n
    for u in range(n):
        if (comp.adjacency[u] >> u) & 1:
            return False
        for v in range(u + 1, n):
            g = graph.has_edge(u, v)
            h = comp.has_edge(u, v)
            if g == h:
                return False
            if comp.has_edge(u, v) != comp.has_edge(v, u):
                return False
    return True


def independent_set_in_complement(comp: ComplementGraph, verts: Sequence[int]) -> bool:
    if not verts:
        return True
    for i, u in enumerate(verts):
        for v in verts[i + 1 :]:
            if comp.has_edge(u, v):
                return False
    return True


def is_vertex_cover(comp: ComplementGraph, cover_mask: int) -> bool:
    """Every complement edge has an endpoint in cover_mask."""
    for e in range(comp.complement_edge_count):
        u = comp.edge_u[e]
        v = comp.edge_v[e]
        if not (((cover_mask >> u) & 1) or ((cover_mask >> v) & 1)):
            return False
    return True
