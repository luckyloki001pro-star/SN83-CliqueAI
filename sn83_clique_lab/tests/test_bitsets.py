from clique.bitset import (
    bit_count,
    bits_to_list,
    clear_bit,
    full_mask,
    has_bit,
    iter_bits,
    list_to_mask,
    lowest_vertex,
)
from clique.graph import BitsetGraph


def test_bit_ops():
    m = list_to_mask([0, 2, 5])
    assert bit_count(m) == 3
    assert bits_to_list(m) == [0, 2, 5]
    assert list(iter_bits(m)) == [0, 2, 5]
    assert lowest_vertex(m) == 0
    assert has_bit(m, 2)
    assert not has_bit(m, 1)
    assert bits_to_list(clear_bit(m, 2)) == [0, 5]
    assert full_mask(4) == 0b1111


def test_graph_edges():
    g = BitsetGraph.empty(4)
    g.add_edge(0, 1)
    g.add_edge(1, 2)
    assert g.has_edge(0, 1) and g.has_edge(1, 0)
    assert not g.has_edge(0, 2)
    assert g.edge_count() == 2
    assert g.validate_undirected()
    g2 = BitsetGraph.from_adjacency_list([[1], [0, 2], [1], []])
    assert g2.n == 4
    assert g2.degree(1) == 2
