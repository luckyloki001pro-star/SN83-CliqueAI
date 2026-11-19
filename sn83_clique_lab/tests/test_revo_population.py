"""Population independence and model-learning integration tests."""

from __future__ import annotations

from clique.datasets import erdos_renyi
from clique.revo import RevoConfig, RevoVariant, solve_revo
from clique.validation import is_clique, is_maximal_clique


def test_population_independent_seeds():
    g = erdos_renyi(40, 0.35, seed=9)
    cfg = RevoConfig(
        variant=RevoVariant.REVO_POPULATION,
        timeout_seconds=0.6,
        safety_margin_ms=50.0,
        seed=42,
        population_size=4,
        restart_factor=20,
        steps_per_searcher_per_sweep=4,
    )
    a = solve_revo(g, cfg)
    b = solve_revo(g, cfg)
    assert a.clique == b.clique  # deterministic
    assert a.valid and a.maximal


def test_no_model_vs_model_both_valid():
    g = erdos_renyi(50, 0.4, seed=11)
    for variant in (RevoVariant.REVO_NO_MODEL, RevoVariant.REVO_POPULATION, RevoVariant.REVO_DIVERSE):
        cfg = RevoConfig(
            variant=variant,
            timeout_seconds=0.8,
            safety_margin_ms=50.0,
            seed=7,
            population_size=4,
            restart_factor=30,
        )
        r = solve_revo(g, cfg)
        assert r.valid and r.maximal
        assert is_clique(g, r.clique) and is_maximal_clique(g, r.clique)
        assert r.clique_size >= 2


def test_model_updates_occur():
    g = erdos_renyi(35, 0.45, seed=3)
    cfg = RevoConfig(
        variant=RevoVariant.REVO_POPULATION,
        timeout_seconds=1.0,
        safety_margin_ms=50.0,
        seed=1,
        population_size=6,
        restart_factor=15,
        steps_per_searcher_per_sweep=6,
    )
    r = solve_revo(g, cfg)
    assert r.stats.population_sweeps >= 1
    assert r.stats.model_updates >= 1
    assert r.stats.extras["use_model"] is True
