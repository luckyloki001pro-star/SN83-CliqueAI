"""Optimal-neighborhood construction for clique repair (ONE / Phase 5A).

Given clique C and removable set R:
  F = C \\ R
  H = ∩_{u in F} N(u)  (excluding F)

Any clique Q ⊆ H yields a valid clique F ∪ Q.
Improvement when |Q| > |R|.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .bitset import bits_to_list, list_to_mask
from .graph import BitsetGraph


@dataclass(frozen=True)
class Neighborhood:
    """Compatible replacement region for fixed set F."""

    clique_mask: int
    removed_mask: int
    fixed_mask: int
    candidate_mask: int  # H
    original_clique_size: int
    removed_count: int
    fixed_count: int
    candidate_count: int
    induced_edge_count: int
    induced_density: float
    r_subset_of_h: bool
    feasible_for_improve: bool  # |H| >= r+1
    target_size: int  # r+1 for one-vertex improvement


def build_neighborhood(
    graph: BitsetGraph,
    clique: Sequence[int],
    remove: Sequence[int],
) -> Neighborhood:
    """Build H for fixed F = clique \\ remove."""
    clique_set = sorted(set(clique))
    remove_set = sorted(set(remove))
    if any(v not in set(clique_set) for v in remove_set):
        raise ValueError("remove must be a subset of clique")
    c_mask = list_to_mask(clique_set)
    r_mask = list_to_mask(remove_set)
    f_mask = c_mask & ~r_mask
    fixed = bits_to_list(f_mask)
    r = len(remove_set)
    k = len(clique_set)

    if not fixed:
        # Removing entire clique: H = all vertices (any clique in G)
        h_mask = graph.all_vertices_mask()
    else:
        h_mask = graph.all_vertices_mask()
        for u in fixed:
            h_mask &= graph.adjacency[u]
        h_mask &= ~f_mask

    # Sanity: removed vertices should remain in H (they form a clique with F)
    r_subset = (r_mask & h_mask) == r_mask

    cand_count = h_mask.bit_count()
    # induced edges in H
    edges = 0
    verts = bits_to_list(h_mask)
    for i, u in enumerate(verts):
        edges += (graph.adjacency[u] & h_mask).bit_count()
        # count each undirected edge once by only counting higher neighbors:
        # cheaper: sum degrees / 2
    edges //= 2
    possible = cand_count * (cand_count - 1) // 2
    dens = (edges / possible) if possible else 0.0
    target = r + 1
    return Neighborhood(
        clique_mask=c_mask,
        removed_mask=r_mask,
        fixed_mask=f_mask,
        candidate_mask=h_mask,
        original_clique_size=k,
        removed_count=r,
        fixed_count=k - r,
        candidate_count=cand_count,
        induced_edge_count=edges,
        induced_density=dens,
        r_subset_of_h=r_subset,
        feasible_for_improve=cand_count >= target,
        target_size=target,
    )


def assemble_clique(fixed_mask: int, q_mask: int) -> List[int]:
    return sorted(bits_to_list(fixed_mask | q_mask))


def conflict_mask(graph: BitsetGraph, clique_mask: int, v: int) -> int:
    """Clique vertices not adjacent to outside vertex v."""
    return clique_mask & ~graph.adjacency[v] & ~(1 << v)


def conflict_count(graph: BitsetGraph, clique_mask: int, v: int) -> int:
    return conflict_mask(graph, clique_mask, v).bit_count()


def conflict_union(graph: BitsetGraph, clique_mask: int, outside: Sequence[int]) -> int:
    r = 0
    for v in outside:
        r |= conflict_mask(graph, clique_mask, v)
    return r


def repair_from_outside_set(
    graph: BitsetGraph,
    clique: Sequence[int],
    outside: Sequence[int],
) -> Optional[Tuple[List[int], int, int]]:
    """If outside set A is a clique and |A| > |R(A)|, return improved clique.

    Returns (C_new, |A|, |R|) or None if not an improving valid repair.
    """
    a = list(outside)
    if len(a) < 1:
        return None
    # A must be a clique
    for i, u in enumerate(a):
        for w in a[i + 1 :]:
            if not graph.has_edge(u, w):
                return None
    c_mask = list_to_mask(clique)
    # outside verts should not be in C
    for v in a:
        if (c_mask >> v) & 1:
            return None
    r_mask = conflict_union(graph, c_mask, a)
    if len(a) <= r_mask.bit_count():
        return None
    f_mask = c_mask & ~r_mask
    # every a in A must connect to all of F
    for v in a:
        if (graph.adjacency[v] & f_mask) != f_mask:
            return None
    new_mask = f_mask
    for v in a:
        new_mask |= 1 << v
    return assemble_clique(f_mask, list_to_mask(a) & ~f_mask), len(a), r_mask.bit_count()
