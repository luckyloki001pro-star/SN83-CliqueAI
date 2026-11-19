"""Pure-Python maximum-clique solvers for SN83 research."""

from .solver import solve_clique, solve_clique_detailed, SolverResult

__all__ = ["solve_clique", "solve_clique_detailed", "SolverResult"]
__version__ = "0.1.0"
