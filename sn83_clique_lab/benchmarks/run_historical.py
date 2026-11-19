"""Run local Python solvers on historical SN83 challenge graphs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.history import load_jsonl
from clique.sn83_scoring import CliqueScoreCalculator, GraphView
from clique.solver import solve_graph
from clique.graph import BitsetGraph

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"
SOLVERS = ("baseline", "ulm", "selective_ulm")


def run_solver_on_record(
    rec: Dict[str, Any],
    solver: str,
    seed: int,
) -> Dict[str, Any]:
    graph = BitsetGraph.from_adjacency_list(
        rec["adjacency_list"],
        name=rec["uuid"],
        metadata={"dataset": "sn83_history", "uuid": rec["uuid"]},
    )
    timeout = float(rec["time_limit"])
    t0 = time.perf_counter()
    # Do NOT use historical answers as incumbents.
    result = solve_graph(
        graph,
        timeout_seconds=timeout,
        variant=solver,
        seed=seed,
        shared_incumbent=None,
        safety_margin_ms=500.0,
    )
    total_ms = (time.perf_counter() - t0) * 1000.0

    # Independent validity via official scorer semantics.
    view = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
    calc = CliqueScoreCalculator(view, float(rec["difficulty"]), [result.clique])
    valid = bool(calc.is_valid_maximum_clique(result.clique))

    return {
        "uuid": rec["uuid"],
        "timestamp": rec["timestamp"],
        "solver": solver,
        "seed": seed,
        "time_limit": timeout,
        "n": rec["number_of_nodes"],
        "difficulty": rec["difficulty"],
        "clique": result.clique,
        "clique_size": result.clique_size,
        "valid": valid and result.valid,
        "maximal": result.maximal and valid,
        "proven_optimal": result.proven_optimal,
        "runtime_ms": result.runtime_ms,
        "e2e_ms": total_ms,
        "deadline_reached": result.deadline_reached,
        "timeout": bool(result.deadline_reached),
        "search_nodes": result.search_nodes,
        "ulm_time_ms": result.ulm_time_ms,
        "ulm_prunes": result.ulm_prunes,
        "ulm_calls": result.ulm_calls,
    }


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--solver", choices=[*SOLVERS, "all"], default="all")
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--seeds",
        type=int,
        nargs="*",
        default=None,
        help="Optional robustness seeds; primary remains --seed",
    )
    args = p.parse_args(argv)

    if not args.history.exists():
        print(
            json.dumps(
                {
                    "error": f"missing history file: {args.history}",
                    "hint": "fetch or import historical challenges first",
                },
                indent=2,
            )
        )
        return 2

    records = load_jsonl(args.history)
    if not records:
        print(json.dumps({"error": "history file empty"}, indent=2))
        return 2

    solvers = list(SOLVERS) if args.solver == "all" else [args.solver]
    seeds = [args.seed]
    robustness = False
    if args.seeds:
        seeds = list(dict.fromkeys([args.seed, *args.seeds]))
        robustness = len(seeds) > 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    by_solver: Dict[str, List[Dict[str, Any]]] = {s: [] for s in solvers}

    for rec in records:
        for solver in solvers:
            # Primary seed first.
            row = run_solver_on_record(rec, solver, args.seed)
            by_solver[solver].append(row)
            print(
                f"[historical] uuid={rec['uuid'][:8]}… solver={solver} "
                f"n={rec['number_of_nodes']} t={rec['time_limit']} "
                f"size={row['clique_size']} valid={row['valid']} "
                f"ms={row['runtime_ms']:.1f}",
                flush=True,
            )
            if robustness:
                for seed in seeds:
                    if seed == args.seed:
                        continue
                    extra = run_solver_on_record(rec, solver, seed)
                    extra["robustness"] = True
                    by_solver[solver].append(extra)

    for solver, rows in by_solver.items():
        primary = [r for r in rows if not r.get("robustness")]
        path = args.output_dir / f"{solver}_responses.jsonl"
        with path.open("w") as f:
            for r in primary:
                f.write(json.dumps(r) + "\n")
        if robustness:
            path_r = args.output_dir / f"{solver}_responses_multiseed.jsonl"
            with path_r.open("w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")

    summary = {
        solver: {
            "rounds": len([r for r in rows if not r.get("robustness")]),
            "mean_size": sum(r["clique_size"] for r in rows if not r.get("robustness"))
            / max(1, len([r for r in rows if not r.get("robustness")])),
            "valid_rate": sum(
                1 for r in rows if not r.get("robustness") and r["valid"]
            )
            / max(1, len([r for r in rows if not r.get("robustness")])),
            "timeout_rate": sum(
                1 for r in rows if not r.get("robustness") and r["timeout"]
            )
            / max(1, len([r for r in rows if not r.get("robustness")])),
        }
        for solver, rows in by_solver.items()
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
