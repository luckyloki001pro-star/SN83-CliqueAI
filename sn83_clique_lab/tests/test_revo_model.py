"""Tests for R-EVO probability model."""

from __future__ import annotations

from clique.revo_model import (
    ProbabilityModel,
    binary_entropy_mean,
    jaccard_similarity,
    mean_pairwise_jaccard,
    select_near_best,
)


def test_init_half():
    m = ProbabilityModel(n=5, initial=0.5)
    assert m.probability == [0.5] * 5


def test_update_frequency_example():
    # illustrative calc from the task brief
    m = ProbabilityModel(n=400, learning_rate=0.5, delta=3, initial=0.5)
    # 10 near-best; vertex 120 in 8, 241 in 6, 377 in 1
    cliques = []
    for i in range(10):
        c = [0, 1, 2]
        if i < 8:
            c.append(120)
        if i < 6:
            c.append(241)
        if i < 1:
            c.append(377)
        cliques.append(c)
    used = m.update_from_cliques(cliques)
    assert used == 10
    assert abs(m.probability[120] - 0.65) < 1e-9
    assert abs(m.probability[241] - 0.55) < 1e-9
    assert abs(m.probability[377] - 0.30) < 1e-9
    assert abs(m.probability[3] - 0.25) < 1e-9  # never in selected → freq 0 → 0.25


def test_delta_filters_near_best():
    m = ProbabilityModel(n=10, learning_rate=1.0, delta=1, initial=0.5)
    cliques = [[0, 1, 2, 3], [0, 1], [0, 1, 2]]  # sizes 4,2,3
    used = m.update_from_cliques(cliques)  # Smax=4 → keep size>=3
    assert used == 2
    assert m.probability[3] == 0.5  # only in size-4; freq among 2 = 0.5; lr=1 → 0.5
    assert m.probability[0] == 1.0


def test_entropy_bounds():
    assert binary_entropy_mean([0.0, 1.0]) == 0.0
    h = binary_entropy_mean([0.5, 0.5])
    assert h > 0.6


def test_jaccard():
    assert jaccard_similarity([1, 2, 3], [2, 3, 4]) == 0.5
    assert mean_pairwise_jaccard([[1, 2], [1, 2], [3, 4]]) > 0


def test_select_near_best():
    cliques = [[0], [0, 1], [0, 1, 2]]
    sizes = [1, 2, 3]
    assert len(select_near_best(cliques, sizes, delta=0)) == 1
    assert len(select_near_best(cliques, sizes, delta=3)) == 3
