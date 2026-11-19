"""Solver independence and no historical leakage."""

from __future__ import annotations

import inspect
import time

from clique import adaptive_dual_portfolio as adp
from clique import portfolio_engine as pe
from clique.graph import BitsetGraph
from clique.portfolio_engine import DualPortfolioEngine


def test_engine_has_no_history_fields():
    src = inspect.getsource(pe) + inspect.getsource(adp)
    assert "miner_ans" not in src


def test_solvers_do_not_share_internal_state():
    g = BitsetGraph.from_edge_list(
        12, [(i, j) for i in range(12) for j in range(i + 1, 12) if (i + j) % 3 != 0]
    )
    t0 = time.perf_counter()
    eng = DualPortfolioEngine(
        g, seed=1, absolute_deadline=t0 + 1.0, safe_deadline=t0 + 0.8, t0=t0
    )
    eng.run_revo_slice(0.25, reason="a")
    eng.run_numvc_slice(0.25, reason="b")
    res = eng.finalize("test")
    assert res.extras.get("historical_access") is False
    assert res.extras.get("resumption_mode") == "restart_based"
    assert eng.stats.revo_slices >= 1 and eng.stats.numvc_slices >= 1
