"""Command-line interface for solve / benchmark / dataset prep."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .datasets import (
    generate_synthetic_suite,
    import_official_samples,
    load_graph_record,
)
from .graph import BitsetGraph
from .networkx_ref import solve_networkx_ref
from .solver import solve_graph, shared_initial_incumbent


def _load_graph(path: Path) -> BitsetGraph:
    data = json.loads(path.read_text())
    if "adjacency_list" in data:
        return BitsetGraph.from_adjacency_list(
            data["adjacency_list"],
            name=data.get("name", path.stem),
            metadata=data.get("metadata", {}),
        )
    if "encoded_matrix" in data:
        from .codec import GraphCodec

        return GraphCodec().decode_graph(
            data["encoded_matrix"], name=data.get("name", path.stem)
        )
    raise ValueError(f"Unrecognized graph format: {path}")


def cmd_solve(args: argparse.Namespace) -> int:
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
            safety_margin_ms=args.safety_margin_ms,
        )
    print(json.dumps(result.to_dict(), indent=2))
    return 0


def cmd_prepare_data(args: argparse.Namespace) -> int:
    official = import_official_samples()
    print(f"Imported {len(official)} official graphs")
    for split in args.splits:
        paths = generate_synthetic_suite(split)
        print(f"Generated {len(paths)} synthetic graphs for split={split}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from benchmarks.run import run_benchmark

    out = run_benchmark(mode=args.mode, output_dir=Path(args.output))
    print(json.dumps({"mode": args.mode, "runs": len(out), "output": args.output}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sn83-clique", description="SN83 clique lab CLI")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("solve", help="Solve one graph")
    s.add_argument("--graph", required=True)
    s.add_argument(
        "--solver",
        default="baseline",
        help="baseline|ulm|selective_ulm|networkx",
    )
    s.add_argument("--timeout", type=float, default=10.0)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--safety-margin-ms", type=float, default=500.0)
    s.add_argument(
        "--fair",
        action="store_true",
        help="Use shared seeded incumbent",
    )
    s.set_defaults(func=cmd_solve)

    d = sub.add_parser("prepare-data", help="Import official + generate synthetic")
    d.add_argument(
        "--splits",
        nargs="+",
        default=["dev", "tune", "eval"],
        choices=["dev", "tune", "eval"],
    )
    d.set_defaults(func=cmd_prepare_data)

    b = sub.add_parser("benchmark", help="Run benchmark suite")
    b.add_argument("--mode", choices=["quick", "full"], default="quick")
    b.add_argument("--output", default="reports")
    b.set_defaults(func=cmd_benchmark)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
