"""Document restart-based scheduling (not true pause/resume)."""

from __future__ import annotations

from clique.portfolio_engine import DualPortfolioEngine
import inspect


def test_engine_documents_restart_mode():
    src = inspect.getsource(DualPortfolioEngine)
    assert "restart" in src.lower()
    assert "True cooperative pause" not in src or "NOT claimed" in src or "NOT" in src
