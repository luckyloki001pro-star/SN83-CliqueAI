"""Offline scoring harness tests (not historical W&B data)."""

import numpy as np

from clique.sn83_scoring import CliqueScoreCalculator, GraphView, competition_rank


def test_scoring_matches_official_semantics_on_toy():
    # Triangle + isolated vertex. Max clique size 3.
    adj = [
        [1, 2],
        [0, 2],
        [0, 1],
        [],
    ]
    responses = [
        [0, 1, 2],  # valid maximal size 3
        [0, 1],  # valid clique but NOT maximal
        [0, 1, 2],  # duplicate best
        [3],  # single vertex maximal? isolated is maximal size 1
        [],  # invalid empty
    ]
    calc = CliqueScoreCalculator(GraphView(4, adj), difficulty=0.8, responses=responses)
    scored = calc.score_detailed()
    assert scored.validity.tolist() == [1, 0, 1, 1, 0]
    assert scored.effective_size.tolist() == [3, 0, 3, 1, 0]
    # max size 3
    assert np.isclose(scored.rel[0], 1.0)
    assert np.isclose(scored.rel[3], 1 / 3)
    # rewards use normalized omega
    assert scored.rewards.shape == (5,)
    assert scored.rewards[1] == 0.0  # invalid non-maximal
    assert scored.rewards[0] > 0


def test_competition_rank_ties():
    scores = [0.5, 0.9, 0.9, 0.1]
    r0, t0 = competition_rank(scores, 0)
    r1, t1 = competition_rank(scores, 1)
    assert r1 == 1 and t1 == 2
    assert r0 == 3
