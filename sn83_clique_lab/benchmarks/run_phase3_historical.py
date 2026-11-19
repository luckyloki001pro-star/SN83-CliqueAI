"""Phase-3 historical benchmark: F vs G/H/I/J/portfolio on latest20."""

from __future__ import annotations

import argparse
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
# F reused from Phase 2 unless --rerun-f
PHASE3_SOLVERS = (
    "triangle_guided",
    "bls_adaptive",
    "pls_penalty",
    "ikls_variable_depth",
    "pair_anchor",
    "adaptive_portfolio",
)


def run_one(rec: Dict[str, Any], solver: str, seed: int) -> Dict[str, Any]:
    graph = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
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
    valid = bool(CliqueScoreCalculator(view, float(rec["difficulty"]), [result.clique]).is_valid_maximum_clique(result.clique)) and result.valid
    return {
        "uuid": rec["uuid"],
        "timestamp": rec["timestamp"],
        "solver": solver,
        "seed": seed,
        "time_limit": timeout,
        "n": rec["number_of_nodes"],
        "difficulty": rec["difficulty"],
        "density": graph.density(),
        "clique": result.clique,
        "clique_size": result.clique_size,
        "valid": valid,
        "maximal": result.maximal and valid,
        "runtime_ms": result.runtime_ms,
        "e2e_ms": e2e_ms,
        "deadline_reached": result.deadline_reached,
        "timeout": bool(result.deadline_reached),
        "search_incomplete_at_deadline": result.extras.get("search_incomplete_at_deadline"),
        "response_deadline_violation": result.extras.get("response_deadline_violation"),
        "improvement_history": result.extras.get("improvement_history"),
        "checkpoints": result.extras.get("checkpoints"),
        "time_to_first_ms": result.extras.get("time_to_first_ms"),
        "time_to_best_ms": result.extras.get("time_to_best_ms"),
        "plateau_moves": result.extras.get("plateau_moves"),
        "useful_plateau_moves": result.extras.get("useful_plateau_moves"),
        "perturbations": result.extras.get("perturbations"),
        "variable_depth_improvements": result.extras.get("variable_depth_improvements"),
        "pair_starts": result.extras.get("pair_starts"),
        "unique_cliques": result.extras.get("unique_cliques"),
        "extras": {
            k: result.extras.get(k)
            for k in (
                "avg_perturbation_strength",
                "revisited_states",
                "successful_escapes",
                "phase_transitions",
                "pair_prep_time_ms",
                "local_search_time_ms",
                "portfolio_order",
                "best_sized_variants",
            )
            if k in result.extras
        },
    }


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--seeds", type=int, nargs="*", default=None)
    p.add_argument("--solvers", nargs="*", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--reuse-f", action="store_true", default=True)
    p.add_argument("--rerun-f", action="store_true", help="Recompute triangle_guided")
    args = p.parse_args(argv)

    records = load_jsonl(args.history)[: args.limit]
    solvers = list(args.solvers) if args.solvers else list(PHASE3_SOLVERS)
    if args.rerun_f:
        args.reuse_f = False

    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: List[Dict[str, Any]] = []

    # Optionally import Phase-2 F results
    f_cache: Dict[str, Dict[str, Any]] = {}
    f_path = args.output_dir / "anytime_triangle_guided_responses.jsonl"
    if args.reuse_f and "triangle_guided" in solvers and f_path.exists():
        for line in f_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("seed", 42) == args.seed:
                f_cache[row["uuid"]] = row
        print(f"[phase3] reusing {len(f_cache)} triangle_guided Phase-2 rows", flush=True)

    seeds = [args.seed]
    if args.seeds:
        seeds = list(dict.fromkeys([args.seed, *args.seeds]))

    for ri, rec in enumerate(records):
        order = solvers[ri % len(solvers) :] + solvers[: ri % len(solvers)]
        for solver in order:
            for seed in seeds:
                robustness = seed != args.seed
                if (
                    solver == "triangle_guided"
                    and args.reuse_f
                    and seed == args.seed
                    and rec["uuid"] in f_cache
                ):
                    row = dict(f_cache[rec["uuid"]])
                    row["solver"] = "triangle_guided"
                    row["reused_from_phase2"] = True
                else:
                    row = run_one(rec, solver, seed)
                if robustness:
                    row["robustness"] = True
                all_rows.append(row)
                if not robustness:
                    print(
                        f"[phase3] uuid={rec['uuid'][:8]} solver={solver} n={row['n']} "
                        f"size={row['clique_size']} valid={row['valid']} "
                        f"ms={row['runtime_ms']:.1f} viol={row.get('response_deadline_violation')}",
                        flush=True,
                    )

    for solver in solvers:
        primary = [r for r in all_rows if r["solver"] == solver and not r.get("robustness")]
        path = args.output_dir / f"phase3_{solver}_responses.jsonl"
        with path.open("w") as f:
            for r in primary:
                f.write(json.dumps(r) + "\n")
        multi = [r for r in all_rows if r["solver"] == solver]
        if len(seeds) > 1:
            with (args.output_dir / f"phase3_{solver}_responses_multiseed.jsonl").open("w") as f:
                for r in multi:
                    f.write(json.dumps(r) + "\n")

    # time-to-best log
    with (args.output_dir / "phase3_time_to_best.jsonl").open("w") as f:
        for r in all_rows:
            if r.get("robustness"):
                continue
            f.write(
                json.dumps(
                    {
                        "uuid": r["uuid"],
                        "solver": r["solver"],
                        "seed": r["seed"],
                        "clique_size": r["clique_size"],
                        "time_to_first_ms": r.get("time_to_first_ms"),
                        "time_to_best_ms": r.get("time_to_best_ms"),
                        "checkpoints": r.get("checkpoints"),
                        "improvement_history": r.get("improvement_history"),
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
            "deadline_violation_rate": sum(1 for r in primary if r.get("response_deadline_violation"))
            / max(1, len(primary)),
        }
    (args.output_dir / "phase3_run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
