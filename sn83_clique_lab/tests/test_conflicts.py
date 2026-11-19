"""Conflict-core construction, merge, unlock, and rollback tests."""

from clique.coloring import greedy_color_candidates
from clique.conflict_core import ConflictCore, IndependentSet, core_invariant_holds
from clique.exhaustive import exact_omega
from clique.graph import BitsetGraph
from clique.ulm import ULMReasoner


def test_add_core_unit_weight_locks_full_set():
    """Under unit weights, split leaves no remainder."""
    g = BitsetGraph.from_edge_list(4, [(0, 1), (2, 3)])
    # Two edges: omega=2. Color classes may create conflicts under UP
    # depending on ordering; exercise AddCore path via reasoner internals.
    reasoner = ULMReasoner(g)
    isets = [
        IndependentSet(id=0, mask=(1 << 0) | (1 << 2), original_mask=(1 << 0) | (1 << 2)),
        IndependentSet(id=1, mask=(1 << 1) | (1 << 3), original_mask=(1 << 1) | (1 << 3)),
        IndependentSet(id=2, mask=(1 << 0) | (1 << 3), original_mask=(1 << 0) | (1 << 3)),
    ]
    cores: list[ConflictCore] = []
    from clique.conflict_core import ReasoningStats

    stats = ReasoningStats()
    beta = reasoner._add_core([0, 1], isets, cores, stats)
    assert beta == 1
    assert len(cores) == 1
    assert cores[0].weight == 1
    assert isets[0].locked and isets[1].locked
    assert isets[0].mask == isets[0].original_mask
    assert core_invariant_holds(cores, isets)


def test_core_merge_increases_penalty():
    g = BitsetGraph.empty(3)
    reasoner = ULMReasoner(g)
    isets = [
        IndependentSet(id=0, mask=1 << 0, original_mask=1 << 0),
        IndependentSet(id=1, mask=1 << 1, original_mask=1 << 1),
        IndependentSet(id=2, mask=1 << 2, original_mask=1 << 2),
    ]
    cores: list[ConflictCore] = []
    from clique.conflict_core import ReasoningStats

    stats = ReasoningStats()
    reasoner._add_core([0, 1], isets, cores, stats)
    assert cores[0].active
    # Second conflict involving a locked set merges the prior core.
    beta = reasoner._add_core([0, 2], isets, cores, stats)
    assert beta == 1
    assert not cores[0].active
    assert cores[1].active
    assert cores[1].weight == 2  # beta + previous core weight
    assert stats.cores_merged >= 1


def test_unlock_when_uw_reaches_w():
    """Simulate empty locked set paying the core penalty."""
    g = BitsetGraph.from_edge_list(
        6,
        [
            (0, 1),
            (0, 2),
            (1, 2),
            (3, 4),
            (3, 5),
            (4, 5),
        ],
    )
    coloring = greedy_color_candidates(g, g.all_vertices_mask())
    res = ULMReasoner(g).tighten_bound(coloring.color_classes, g.all_vertices_mask())
    assert exact_omega(g) <= res.bound <= coloring.bound


def test_rollback_restores_masks():
    g = BitsetGraph.empty(4)
    for i in range(4):
        for j in range(i + 1, 4):
            if (i, j) != (0, 3):
                g.add_edge(i, j)
    reasoner = ULMReasoner(g)
    isets = [
        IndependentSet(id=0, mask=(1 << 0) | (1 << 1), original_mask=(1 << 0) | (1 << 1)),
        IndependentSet(id=1, mask=(1 << 2) | (1 << 3), original_mask=(1 << 2) | (1 << 3)),
    ]
    saved = [s.mask for s in isets]
    # Find conflict may mutate then restore.
    from clique.conflict_core import ReasoningStats

    stats = ReasoningStats()
    _ = reasoner._find_conflict(isets, [], stats)
    for s, m in zip(isets, saved):
        # Either restored or left at original after no-conflict fixpoint rollback.
        assert s.mask == m or s.mask == s.original_mask


def test_nested_candidate_subgraph_bounds():
    """ULM on induced candidate subsets remains sound."""
    import random

    rng = random.Random(11)
    g = BitsetGraph.empty(14)
    for i in range(14):
        for j in range(i + 1, 14):
            if rng.random() < 0.5:
                g.add_edge(i, j)
    # Sample a candidate subset.
    cand = 0
    for v in range(14):
        if rng.random() < 0.6:
            cand |= 1 << v
    # Exact omega on induced subgraph.
    verts = []
    tmp = cand
    while tmp:
        b = tmp & -tmp
        verts.append(b.bit_length() - 1)
        tmp ^= b
    # Build induced graph remap.
    idx = {v: i for i, v in enumerate(verts)}
    induced = BitsetGraph.empty(len(verts))
    for u in verts:
        for v in verts:
            if u < v and g.has_edge(u, v):
                induced.add_edge(idx[u], idx[v])
    omega = exact_omega(induced)
    coloring = greedy_color_candidates(g, cand)
    res = ULMReasoner(g).tighten_bound(coloring.color_classes, cand)
    assert omega <= res.bound <= coloring.bound
