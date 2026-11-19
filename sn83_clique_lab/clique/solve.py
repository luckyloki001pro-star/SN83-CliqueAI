"""python -m clique.solve --graph ... --solver ... --timeout ..."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cli import _load_graph
from .networkx_ref import solve_networkx_ref
from .solver import shared_initial_incumbent, solve_graph


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Solve a single graph")
    p.add_argument("--graph", required=True)
    p.add_argument("--solver", default="baseline")
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--fair", action="store_true")
    args = p.parse_args(argv)

    graph = _load_graph(Path(args.graph))
    if args.solver in ("networkx", "networkx_approx", "r"):
        result = solve_networkx_ref(graph, timeout_seconds=args.timeout)
    else:
        shared = shared_initial_incumbent(graph, seed=args.seed) if args.fair else None
        result = solve_graph(
            graph,
            timeout_seconds=args.timeout,
            variant=args.solver,
            seed=args.seed,
            shared_incumbent=shared,
        )
    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
