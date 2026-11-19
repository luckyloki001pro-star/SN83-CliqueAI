"""Phase 5B historical benchmark: complement MIS / NuMVC vs revo_no_model."""

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

PHASE5B_SOLVERS = (
    "revo_no_model",
    "mis_random_restart",
    "mis_configuration_search",
    "numvc_complement",
    "numvc_diversified",
)

HARD_PREFIXES = ("577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0")


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
    ex = result.extras or {}
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
        "response_deadline_violation": ex.get("response_deadline_violation"),
        "time_to_best_ms": ex.get("time_to_best_ms"),
        "complement_edge_count": ex.get("complement_edge_count"),
        "complement_density": ex.get("complement_density"),
        "complement_ms": ex.get("complement_ms"),
        "search_steps": ex.get("search_steps"),
        "steps_per_second": ex.get("steps_per_second"),
        "best_cover_size": ex.get("best_cover_size"),
        "forgetting_events": ex.get("forgetting_events"),
        "weight_increments": ex.get("weight_increments"),
        "mean_edge_weight": ex.get("mean_edge_weight"),
        "valid_cover_discoveries": ex.get("valid_cover_discoveries"),
        "best_cover_improvements": ex.get("best_cover_improvements"),
        "restarts": ex.get("restarts"),
        "elite": ex.get("elite"),
        "improvement_history": ex.get("improvement_history"),
        "winner": ex.get("winner"),
        "numvc_size": ex.get("numvc_size"),
        "revo_size": ex.get("revo_size"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--seeds", type=int, nargs="*", default=None)
    p.add_argument("--solvers", nargs="*", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--hard-only", action="store_true")
    p.add_argument("--reuse-revo", action="store_true", default=True)
    p.add_argument("--rerun-revo", action="store_true")
    args = p.parse_args()
    if args.rerun_revo:
        args.reuse_revo = False

    records = load_jsonl(args.history)[: args.limit]
    if args.hard_only:
        records = [r for r in records if r["uuid"][:8] in HARD_PREFIXES]
    solvers = list(args.solvers) if args.solvers else list(PHASE5B_SOLVERS)
    seeds = [args.seed]
    if args.seeds:
        seeds = list(dict.fromkeys([args.seed, *args.seeds]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    revo_cache: Dict[str, Dict[str, Any]] = {}
    for cand in (
        args.output_dir / "phase4b_revo_no_model_responses.jsonl",
        args.output_dir / "phase5a_revo_no_model_responses.jsonl",
        args.output_dir / "phase5b_revo_no_model_responses.jsonl",
    ):
        if args.reuse_revo and "revo_no_model" in solvers and cand.exists():
            for line in cand.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("seed", 42) == args.seed:
                        revo_cache[row["uuid"]] = row
            if len(revo_cache) >= len(records):
                print(f"[phase5b] reusing {len(revo_cache)} revo_no_model from {cand.name}", flush=True)
                break
            revo_cache.clear()

    all_rows: List[Dict[str, Any]] = []
    for ri, rec in enumerate(records):
        order = solvers[ri % len(solvers) :] + solvers[: ri % len(solvers)]
        for solver in order:
            for seed in seeds:
                robustness = seed != args.seed
                if (
                    solver == "revo_no_model"
                    and args.reuse_revo
                    and seed == args.seed
                    and rec["uuid"] in revo_cache
                ):
                    row = dict(revo_cache[rec["uuid"]])
                    row["solver"] = "revo_no_model"
                    row["reused"] = True
                else:
                    row = run_one(rec, solver, seed)
                if robustness:
                    row["robustness"] = True
                all_rows.append(row)
                if not robustness:
                    print(
                        f"[phase5b] {rec['uuid'][:8]} {solver} n={row['n']} "
                        f"size={row['clique_size']} valid={row['valid']} "
                        f"steps={row.get('search_steps')} "
                        f"cdens={row.get('complement_density')} "
                        f"viol={row.get('response_deadline_violation')}",
                        flush=True,
                    )

    for solver in solvers:
        primary = [r for r in all_rows if r["solver"] == solver and not r.get("robustness")]
        with (args.output_dir / f"phase5b_{solver}_responses.jsonl").open("w") as f:
            for r in primary:
                f.write(json.dumps(r) + "\n")
        if len(seeds) > 1:
            multi = [r for r in all_rows if r["solver"] == solver]
            with (args.output_dir / f"phase5b_{solver}_responses_multiseed.jsonl").open("w") as f:
                for r in multi:
                    f.write(json.dumps(r) + "\n")

    summary = {
        s: {
            "rounds": len(p),
            "mean_size": sum(r["clique_size"] for r in p) / max(1, len(p)),
            "valid_rate": sum(1 for r in p if r["valid"]) / max(1, len(p)),
            "deadline_violation_rate": sum(1 for r in p if r.get("response_deadline_violation"))
            / max(1, len(p)),
            "mean_steps": sum((r.get("search_steps") or 0) for r in p) / max(1, len(p)),
        }
        for s in solvers
        for p in [[r for r in all_rows if r["solver"] == s and not r.get("robustness")]]
    }
    (args.output_dir / "phase5b_run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
