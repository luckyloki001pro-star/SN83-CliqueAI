"""Phase 5A historical benchmark: ONE repair variants vs revo_no_model."""

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

PHASE5A_SOLVERS = (
    "revo_no_model",
    "one_random_repair",
    "one_conflict_repair",
    "one_adaptive_repair",
    "one_diverse_repair",
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
        "time_to_first_improvement_ms": ex.get("time_to_first_improvement_ms"),
        "neighborhoods_attempted": ex.get("neighborhoods_attempted"),
        "neighborhoods_completed": ex.get("neighborhoods_completed"),
        "neighborhoods_timed_out": ex.get("neighborhoods_timed_out"),
        "proven_impossible_neighborhoods": ex.get("proven_impossible_neighborhoods"),
        "target_cliques_found": ex.get("target_cliques_found"),
        "improvements_of_one": ex.get("improvements_of_one"),
        "improvements_of_two_or_more": ex.get("improvements_of_two_or_more"),
        "cache_hits": ex.get("cache_hits"),
        "revo_ms": ex.get("revo_ms"),
        "repair_ms": ex.get("repair_ms"),
        "search_nodes_total": ex.get("search_nodes_total"),
        "color_prunes_total": ex.get("color_prunes_total"),
        "elite_count": (ex.get("elite") or {}).get("elite_count") if isinstance(ex.get("elite"), dict) else ex.get("elite_count"),
        "candidate_count_distribution": ex.get("candidate_count_distribution"),
        "improvement_rate_by_r": ex.get("improvement_rate_by_r"),
        "adaptive_r": ex.get("adaptive_r"),
        "selector_mode": ex.get("selector_mode"),
        "revo_fraction": ex.get("revo_fraction"),
        "improvement_history": ex.get("improvement_history"),
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
    solvers = list(args.solvers) if args.solvers else list(PHASE5A_SOLVERS)
    seeds = [args.seed]
    if args.seeds:
        seeds = list(dict.fromkeys([args.seed, *args.seeds]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    revo_cache: Dict[str, Dict[str, Any]] = {}
    for cand in (
        args.output_dir / "phase4b_revo_no_model_responses.jsonl",
        args.output_dir / "phase5a_revo_no_model_responses.jsonl",
    ):
        if args.reuse_revo and "revo_no_model" in solvers and cand.exists():
            for line in cand.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("seed", 42) == args.seed:
                        revo_cache[row["uuid"]] = row
            if revo_cache:
                print(f"[phase5a] reusing {len(revo_cache)} revo_no_model from {cand.name}", flush=True)
                break

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
                        f"[phase5a] {rec['uuid'][:8]} {solver} n={row['n']} "
                        f"size={row['clique_size']} valid={row['valid']} "
                        f"nb={row.get('neighborhoods_attempted')} "
                        f"imp1={row.get('improvements_of_one')} "
                        f"viol={row.get('response_deadline_violation')}",
                        flush=True,
                    )

    for solver in solvers:
        primary = [r for r in all_rows if r["solver"] == solver and not r.get("robustness")]
        with (args.output_dir / f"phase5a_{solver}_responses.jsonl").open("w") as f:
            for r in primary:
                f.write(json.dumps(r) + "\n")
        if len(seeds) > 1:
            multi = [r for r in all_rows if r["solver"] == solver]
            with (args.output_dir / f"phase5a_{solver}_responses_multiseed.jsonl").open("w") as f:
                for r in multi:
                    f.write(json.dumps(r) + "\n")

    summary = {
        s: {
            "rounds": len(p),
            "mean_size": sum(r["clique_size"] for r in p) / max(1, len(p)),
            "valid_rate": sum(1 for r in p if r["valid"]) / max(1, len(p)),
            "deadline_violation_rate": sum(1 for r in p if r.get("response_deadline_violation"))
            / max(1, len(p)),
            "mean_neighborhoods": sum((r.get("neighborhoods_attempted") or 0) for r in p) / max(1, len(p)),
            "total_improvements_one": sum((r.get("improvements_of_one") or 0) for r in p),
            "total_improvements_two_plus": sum((r.get("improvements_of_two_or_more") or 0) for r in p),
        }
        for s in solvers
        for p in [[r for r in all_rows if r["solver"] == s and not r.get("robustness")]]
    }
    (args.output_dir / "phase5a_run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
