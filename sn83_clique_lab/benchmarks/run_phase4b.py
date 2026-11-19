"""Phase 4B historical benchmark: R-EVO variants vs adaptive_portfolio."""

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

PHASE4B_SOLVERS = (
    "adaptive_portfolio",
    "revo_no_model",
    "revo_population",
    "revo_diverse",
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
    e2e = (time.perf_counter() - t0) * 1000.0
    view = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
    valid = bool(
        CliqueScoreCalculator(view, float(rec["difficulty"]), [result.clique]).is_valid_maximum_clique(
            result.clique
        )
    ) and result.valid
    return {
        "uuid": rec["uuid"],
        "solver": solver,
        "seed": seed,
        "time_limit": timeout,
        "n": rec["number_of_nodes"],
        "difficulty": rec["difficulty"],
        "clique": result.clique,
        "clique_size": result.clique_size,
        "valid": valid,
        "maximal": result.maximal and valid,
        "runtime_ms": result.runtime_ms,
        "e2e_ms": e2e,
        "timeout": bool(result.deadline_reached),
        "response_deadline_violation": result.extras.get("response_deadline_violation"),
        "time_to_best_ms": result.extras.get("time_to_best_ms"),
        "population_sweeps": result.extras.get("population_sweeps"),
        "restarts": result.extras.get("restarts"),
        "model_updates": result.extras.get("model_updates"),
        "model_update_ms": result.extras.get("model_update_ms"),
        "local_search_ms": result.extras.get("local_search_ms"),
        "final_model_entropy": result.extras.get("final_model_entropy"),
        "final_jaccard": result.extras.get("final_jaccard"),
        "unique_personal_bests": result.extras.get("unique_personal_bests"),
        "model_guided_restart_improvements": result.extras.get("model_guided_restart_improvements"),
        "searcher_best_sizes": result.extras.get("searcher_best_sizes"),
        "improvement_history": result.extras.get("improvement_history"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--seeds", type=int, nargs="*", default=None)
    p.add_argument("--solvers", nargs="*", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--reuse-portfolio", action="store_true", default=True)
    p.add_argument("--rerun-portfolio", action="store_true")
    args = p.parse_args()
    if args.rerun_portfolio:
        args.reuse_portfolio = False

    records = load_jsonl(args.history)[: args.limit]
    solvers = list(args.solvers) if args.solvers else list(PHASE4B_SOLVERS)
    seeds = [args.seed]
    if args.seeds:
        seeds = list(dict.fromkeys([args.seed, *args.seeds]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    port_cache: Dict[str, Dict[str, Any]] = {}
    for cand in (
        args.output_dir / "phase3_adaptive_portfolio_responses.jsonl",
        args.output_dir / "phase4a_adaptive_portfolio_responses.jsonl",
    ):
        if args.reuse_portfolio and "adaptive_portfolio" in solvers and cand.exists():
            for line in cand.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("seed", 42) == args.seed:
                        port_cache[row["uuid"]] = row
            if port_cache:
                print(f"[phase4b] reusing {len(port_cache)} adaptive_portfolio from {cand.name}", flush=True)
                break

    all_rows: List[Dict[str, Any]] = []
    for ri, rec in enumerate(records):
        order = solvers[ri % len(solvers) :] + solvers[: ri % len(solvers)]
        for solver in order:
            for seed in seeds:
                robustness = seed != args.seed
                if (
                    solver == "adaptive_portfolio"
                    and args.reuse_portfolio
                    and seed == args.seed
                    and rec["uuid"] in port_cache
                ):
                    row = dict(port_cache[rec["uuid"]])
                    row["solver"] = "adaptive_portfolio"
                    row["reused"] = True
                else:
                    row = run_one(rec, solver, seed)
                if robustness:
                    row["robustness"] = True
                all_rows.append(row)
                if not robustness:
                    print(
                        f"[phase4b] {rec['uuid'][:8]} {solver} n={row['n']} "
                        f"size={row['clique_size']} valid={row['valid']} "
                        f"restarts={row.get('restarts')} updates={row.get('model_updates')} "
                        f"viol={row.get('response_deadline_violation')}",
                        flush=True,
                    )

    for solver in solvers:
        primary = [r for r in all_rows if r["solver"] == solver and not r.get("robustness")]
        with (args.output_dir / f"phase4b_{solver}_responses.jsonl").open("w") as f:
            for r in primary:
                f.write(json.dumps(r) + "\n")
        if len(seeds) > 1:
            multi = [r for r in all_rows if r["solver"] == solver]
            with (args.output_dir / f"phase4b_{solver}_responses_multiseed.jsonl").open("w") as f:
                for r in multi:
                    f.write(json.dumps(r) + "\n")

    summary = {
        s: {
            "rounds": len(p),
            "mean_size": sum(r["clique_size"] for r in p) / max(1, len(p)),
            "valid_rate": sum(1 for r in p if r["valid"]) / max(1, len(p)),
            "deadline_violation_rate": sum(1 for r in p if r.get("response_deadline_violation"))
            / max(1, len(p)),
        }
        for s in solvers
        for p in [[r for r in all_rows if r["solver"] == s and not r.get("robustness")]]
    }
    (args.output_dir / "phase4b_run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
