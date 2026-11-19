"""Sequential greedy coloring upper bounds for candidate subgraphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .bitset import bits_to_list, iter_bits
from .graph import BitsetGraph


@dataclass(slots=True)
class ColoringResult:
    """Coloring of a candidate mask.

    ``color_classes[i]`` is a bitset of vertices with color i (0-based).
    A clique can take at most one vertex from each class, so
    ``len(color_classes)`` is a valid upper bound on clique size in the
    candidate subgraph.
    """

    color_classes: List[int]
    # For each colored vertex in branching order (high color first),
    # ``bounds[k]`` = number of colors among the first k+1 vertices in
    # that order. Used for Tomita-style pruning: after selecting the
    # vertex at position k, remaining UB contribution is bounds[k]-1? 
    # Actually classic MCQ: vertices ordered by color number descending;
    # when branching on vertex with color c, prune if |S|+c <= |best|.
    vertex_order: List[int]
    color_of: List[int]  # color number (1-based) per vertex, 0 if absent
    bound: int


def greedy_color_candidates(
    graph: BitsetGraph,
    candidates: int,
    order: Sequence[int] | None = None,
) -> ColoringResult:
    """
    Color the induced candidate subgraph with sequential greedy coloring.

    Vertices are considered in ``order`` (default: descending degree in
    the candidate subgraph). Color numbers are 1-based. Independent sets
    (color classes) are returned as bitsets.
    """
    adj = graph.adjacency
    n = graph.n
    color_of = [0] * n
    color_classes: List[int] = []

    if candidates == 0:
        return ColoringResult([], [], color_of, 0)

    if order is None:
        # Degeneracy-ish: high residual candidate-degree first.
        verts = bits_to_list(candidates)
        verts.sort(key=lambda v: -((candidates & adj[v]).bit_count()))
    else:
        verts = [v for v in order if (candidates >> v) & 1]

    for v in verts:
        # Find the lowest color class not containing a neighbor of v.
        assigned = -1
        neigh = adj[v]
        for c, class_mask in enumerate(color_classes):
            if (class_mask & neigh) == 0:
                assigned = c
                break
        if assigned < 0:
            assigned = len(color_classes)
            color_classes.append(0)
        color_classes[assigned] |= 1 << v
        color_of[v] = assigned + 1  # 1-based

    # Branching order: non-decreasing color (Tomita / MCS style uses
    # increasing color so higher colors are branched first when iterating
    # from the end). We return ascending color order; BnB pops from end.
    colored = []
    for c, class_mask in enumerate(color_classes):
        members = bits_to_list(class_mask)
        # Within a color class, high candidate-degree first.
        members.sort(key=lambda v: -((candidates & adj[v]).bit_count()))
        colored.extend(members)

    return ColoringResult(
        color_classes=color_classes,
        vertex_order=colored,
        color_of=color_of,
        bound=len(color_classes),
    )


def color_bound_and_branches(
    graph: BitsetGraph,
    candidates: int,
    current_size: int,
    best_size: int,
) -> Tuple[ColoringResult, List[Tuple[int, int]]]:
    """
    Return coloring plus branch list of (vertex, color_number) that can
    improve the incumbent.

    A vertex with color number c can only improve if
    current_size + c > best_size. Vertices are returned in ascending
    color order so BnB may iterate reverse (high color first).
    """
    coloring = greedy_color_candidates(graph, candidates)
    branches: List[Tuple[int, int]] = []
    need = best_size - current_size
    for v in coloring.vertex_order:
        c = coloring.color_of[v]
        if c > need:
            branches.append((v, c))
    return coloring, branches
