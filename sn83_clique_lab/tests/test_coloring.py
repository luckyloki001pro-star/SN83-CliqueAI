from clique.coloring import greedy_color_candidates
from clique.exhaustive import exact_omega
from clique.graph import BitsetGraph


def test_coloring_bound_valid_on_complete():
    n = 6
    g = BitsetGraph.empty(n)
    for i in range(n):
        for j in range(i + 1, n):
            g.add_edge(i, j)
    coloring = greedy_color_candidates(g, g.all_vertices_mask())
    assert coloring.bound >= exact_omega(g)
    # Complete graph: each vertex needs own color.
    assert coloring.bound == n


def test_coloring_bound_on_bipartite():
    # Complete bipartite K_{3,3} has omega=2; coloring bound >= 2.
    g = BitsetGraph.empty(6)
    for i in range(3):
        for j in range(3, 6):
            g.add_edge(i, j)
    coloring = greedy_color_candidates(g, g.all_vertices_mask())
    assert coloring.bound >= 2
    assert exact_omega(g) == 2
    assert coloring.bound >= exact_omega(g)


def test_color_classes_are_independent():
    g = BitsetGraph.from_edge_list(
        5, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (0, 2)]
    )
    coloring = greedy_color_candidates(g, g.all_vertices_mask())
    for class_mask in coloring.color_classes:
        verts = []
        tmp = class_mask
        while tmp:
            b = tmp & -tmp
            verts.append(b.bit_length() - 1)
            tmp ^= b
        for i, u in enumerate(verts):
            for v in verts[i + 1 :]:
                assert not g.has_edge(u, v)
