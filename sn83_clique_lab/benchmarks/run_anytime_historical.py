"""Benchmark baseline + anytime solvers D/E/F on historical SN83 challenges."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.graph import BitsetGraph
from clique.history import load_jsonl
from clique.sn83_scoring import CliqueScoreCalculator, GraphView
from clique.solver import solve_graph

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"
SOLVERS = ("baseline", "multistart_greedy", "swap_local_search", "triangle_guided")


def run_one(rec: Dict[str, Any], solver: str, seed: int) -> Dict[str, Any]:
    graph = BitsetGraph.from_adjacency_list(
        rec["adjacency_list"], name=rec["uuid"], metadata={"uuid": rec["uuid"]}
    )
    timeout = float(rec["time_limit"])
    t0 = time.perf_counter()
    result = solve_graph(
        graph,
        timeout_seconds=timeout,
        variant=solver,
        seed=seed,
        safety_margin_ms=500.0,
    )
    e2e_ms = (time.perf_counter() - t0) * 1000.0
    view = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
    calc = CliqueScoreCalculator(view, float(rec["difficulty"]), [result.clique])
    valid = bool(calc.is_valid_maximum_clique(result.clique)) and result.valid
    return {
        "uuid": rec["uuid"],
        "timestamp": rec["timestamp"],
        "solver": solver,
        "seed": seed,
        "time_limit": timeout,
        "n": rec["number_of_nodes"],
        "difficulty": rec["difficulty"],
        "density": graph.density(),
        "graph_hash": result.extras.get("graph_hash") or graph.content_hash(),
        "clique": result.clique,
        "clique_size": result.clique_size,
        "valid": valid,
        "maximal": result.maximal and valid,
        "proven_optimal": result.proven_optimal,
        "runtime_ms": result.runtime_ms,
        "e2e_ms": e2e_ms,
        "deadline_reached": result.deadline_reached,
        "timeout": bool(result.deadline_reached),
        "search_incomplete_at_deadline": result.extras.get("search_incomplete_at_deadline"),
        "response_deadline_violation": result.extras.get("response_deadline_violation"),
        "search_nodes": result.search_nodes,
        "ulm_time_ms": result.ulm_time_ms,
        "ulm_prunes": result.ulm_prunes,
        "ulm_calls": result.ulm_calls,
        "improvement_history": result.extras.get("improvement_history"),
        "checkpoints": result.extras.get("checkpoints"),
        "time_to_first_ms": result.extras.get("time_to_first_ms"),
        "time_to_best_ms": result.extras.get("time_to_best_ms"),
        "best_from_phase": result.extras.get("best_from_phase"),
        "constructions": result.extras.get("constructions"),
        "swap_1for2_success": result.extras.get("swap_1for2_success"),
        "swap_2for3_success": result.extras.get("swap_2for3_success"),
        "construction_time_ms": result.extras.get("construction_time_ms"),
        "local_search_time_ms": result.extras.get("local_search_time_ms"),
        "triangle_prep_time_ms": result.extras.get("triangle_prep_time_ms"),
    }


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--seeds", type=int, nargs="*", default=None)
    p.add_argument(
        "--solvers",
        nargs="*",
        default=list(SOLVERS),
        help="Solvers to run (default: all four)",
    )
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args(argv)

    records = load_jsonl(args.history)[: args.limit]
    if len(records) < args.limit:
        print(json.dumps({"error": f"expected {args.limit} records, got {len(records)}"}))
        return 2

    solvers = list(args.solvers)
    seeds = [args.seed]
    robustness = False
    if args.seeds:
        seeds = list(dict.fromkeys([args.seed, *args.seeds]))
        robustness = len(seeds) > 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: List[Dict[str, Any]] = []
    # Rotate solver order each round for fairness.
    for ri, rec in enumerate(records):
        order = solvers[ri % len(solvers) :] + solvers[: ri % len(solvers)]
        for solver in order:
            row = run_one(rec, solver, args.seed)
            all_rows.append(row)
            print(
                f"[anytime] uuid={rec['uuid'][:8]} solver={solver} n={row['n']} "
                f"t={row['time_limit']} size={row['clique_size']} valid={row['valid']} "
                f"ms={row['runtime_ms']:.1f} viol={row['response_deadline_violation']}",
                flush=True,
            )
            if robustness:
                for seed in seeds:
                    if seed == args.seed:
                        continue
                    extra = run_one(rec, solver, seed)
                    extra["robustness"] = True
                    all_rows.append(extra)

    # Write per-solver jsonl (primary seed only) without clobbering prior phase-1 names
    # for baseline: write anytime_baseline_responses.jsonl; keep old baseline_responses.jsonl
    for solver in solvers:
        primary = [r for r in all_rows if r["solver"] == solver and not r.get("robustness")]
        path = args.output_dir / f"anytime_{solver}_responses.jsonl"
        with path.open("w") as f:
            for r in primary:
                f.write(json.dumps(r) + "\n")

    hist_path = args.output_dir / "anytime_improvement_history.jsonl"
    with hist_path.open("w") as f:
        for r in all_rows:
            if r.get("robustness"):
                continue
            f.write(
                json.dumps(
                    {
                        "uuid": r["uuid"],
                        "solver": r["solver"],
                        "seed": r["seed"],
                        "improvement_history": r.get("improvement_history"),
                        "checkpoints": r.get("checkpoints"),
                        "clique_size": r["clique_size"],
                        "time_limit": r["time_limit"],
                    }
                )
                + "\n"
            )

    summary = {}
    for solver in solvers:
        primary = [r for r in all_rows if r["solver"] == solver and not r.get("robustness")]
        summary[solver] = {
            "rounds": len(primary),
            "mean_size": sum(r["clique_size"] for r in primary) / max(1, len(primary)),
            "valid_rate": sum(1 for r in primary if r["valid"]) / max(1, len(primary)),
            "timeout_rate": sum(1 for r in primary if r["timeout"]) / max(1, len(primary)),
            "deadline_violation_rate": sum(
                1 for r in primary if r.get("response_deadline_violation")
            )
            / max(1, len(primary)),
        }
    (args.output_dir / "anytime_run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
