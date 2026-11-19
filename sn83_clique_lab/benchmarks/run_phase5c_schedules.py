"""Fixed + adaptive portfolio schedules on historical SN83 graphs."""

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

# Stage A quick candidates
STAGE_A = (
    "full_revo",
    "full_numvc",
    "revo_90_numvc_10",
    "revo_80_numvc_20",
    "revo_50_numvc_50",
    "early_probe_0.5s",
    "early_probe_1.0s",
    "late_probe",
    "stagnation_trigger",
)


def run_one(rec: Dict[str, Any], solver: str, seed: int) -> Dict[str, Any]:
    graph = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
    timeout = float(rec["time_limit"])
    t0 = time.perf_counter()
    # Map full_revo/full_numvc to portfolio variants; also allow raw revo/numvc reuse
    variant = solver
    if solver == "revo_no_model":
        variant = "revo_no_model"
    result = solve_graph(
        graph,
        timeout_seconds=timeout,
        variant=variant,
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
        "response_deadline_violation": ex.get("response_deadline_violation"),
        "revo_best_size": ex.get("revo_best_size"),
        "numvc_best_size": ex.get("numvc_best_size"),
        "revo_active_ms": ex.get("revo_active_ms"),
        "numvc_active_ms": ex.get("numvc_active_ms"),
        "switches": ex.get("switches"),
        "probe_count": ex.get("probe_count"),
        "successful_probe_count": ex.get("successful_probe_count"),
        "incumbent": ex.get("incumbent"),
        "resumption_mode": ex.get("resumption_mode"),
        "policy": ex.get("policy"),
        "source": (ex.get("incumbent") or {}).get("source") if isinstance(ex.get("incumbent"), dict) else None,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--seeds", type=int, nargs="*", default=None)
    p.add_argument("--solvers", nargs="*", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--reuse-revo", action="store_true", default=True)
    p.add_argument("--hard-only", action="store_true")
    args = p.parse_args()

    records = load_jsonl(args.history)[: args.limit]
    if args.hard_only:
        hard = {"577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0"}
        records = [r for r in records if r["uuid"][:8] in hard]
    solvers = list(args.solvers) if args.solvers else list(STAGE_A)
    seeds = [args.seed]
    if args.seeds:
        seeds = list(dict.fromkeys([args.seed, *args.seeds]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    revo_cache: Dict[str, Dict[str, Any]] = {}
    for cand in (
        args.output_dir / "phase4b_revo_no_model_responses.jsonl",
        args.output_dir / "phase5b_revo_no_model_responses.jsonl",
    ):
        if args.reuse_revo and ("full_revo" in solvers or "revo_no_model" in solvers) and cand.exists():
            for line in cand.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("seed", 42) == args.seed:
                        revo_cache[row["uuid"]] = row
            if len(revo_cache) >= len(records):
                print(f"[phase5c] reusing {len(revo_cache)} revo from {cand.name}", flush=True)
                break
            revo_cache.clear()

    all_rows: List[Dict[str, Any]] = []
    for ri, rec in enumerate(records):
        order = solvers[ri % len(solvers) :] + solvers[: ri % len(solvers)]
        for solver in order:
            for seed in seeds:
                robustness = seed != args.seed
                if (
                    solver in ("full_revo", "revo_no_model")
                    and args.reuse_revo
                    and seed == args.seed
                    and rec["uuid"] in revo_cache
                ):
                    row = dict(revo_cache[rec["uuid"]])
                    row["solver"] = solver
                    row["reused"] = True
                else:
                    row = run_one(rec, solver, seed)
                if robustness:
                    row["robustness"] = True
                all_rows.append(row)
                if not robustness:
                    print(
                        f"[phase5c] {rec['uuid'][:8]} {solver} size={row['clique_size']} "
                        f"src={row.get('source')} revo={row.get('revo_best_size')} "
                        f"numvc={row.get('numvc_best_size')} viol={row.get('response_deadline_violation')}",
                        flush=True,
                    )

    for solver in solvers:
        primary = [r for r in all_rows if r["solver"] == solver and not r.get("robustness")]
        with (args.output_dir / f"phase5c_{solver}_responses.jsonl").open("w") as f:
            for r in primary:
                f.write(json.dumps(r) + "\n")
        if len(seeds) > 1:
            multi = [r for r in all_rows if r["solver"] == solver]
            with (args.output_dir / f"phase5c_{solver}_responses_multiseed.jsonl").open("w") as f:
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
    (args.output_dir / "phase5c_run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
