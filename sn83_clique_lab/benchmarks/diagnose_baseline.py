"""Diagnose baseline anytime incumbent discovery on historical SN83 graphs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.history import load_jsonl
from clique.solver import solve_graph
from clique.graph import BitsetGraph

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
OUT = ROOT / "results" / "baseline_diagnosis.json"


def diagnose_one(rec: Dict[str, Any], seed: int) -> Dict[str, Any]:
    graph = BitsetGraph.from_adjacency_list(
        rec["adjacency_list"], name=rec["uuid"], metadata={"uuid": rec["uuid"]}
    )
    timeout = float(rec["time_limit"])
    result = solve_graph(
        graph,
        timeout_seconds=timeout,
        variant="baseline",
        seed=seed,
        safety_margin_ms=500.0,
    )
    hist = result.extras.get("improvement_history") or []
    return {
        "uuid": rec["uuid"],
        "n": rec["number_of_nodes"],
        "time_limit": timeout,
        "difficulty": rec["difficulty"],
        "clique_size": result.clique_size,
        "valid": result.valid,
        "maximal": result.maximal,
        "runtime_ms": result.runtime_ms,
        "e2e_budget_ms": timeout * 1000.0,
        "deadline_reached": result.deadline_reached,
        "search_incomplete_at_deadline": result.extras.get("search_incomplete_at_deadline"),
        "response_deadline_violation": result.extras.get("response_deadline_violation"),
        "proven_optimal": result.proven_optimal,
        "search_nodes": result.search_nodes,
        "initial_heuristic_ms": result.extras.get("initial_heuristic_ms"),
        "branch_bound_ms": result.extras.get("branch_bound_ms"),
        "best_from_phase": result.extras.get("best_from_phase"),
        "incumbent_improvements": result.extras.get("incumbent_improvements"),
        "improvement_history": hist,
        "checkpoints": result.extras.get("checkpoints"),
        "time_to_first_ms": hist[0]["time_ms"] if hist else None,
        "time_to_best_ms": hist[-1]["time_ms"] if hist else None,
        "bnb_improved_over_greedy": any(h.get("phase") == "bnb" for h in hist),
    }


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output", type=Path, default=OUT)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args(argv)

    records = load_jsonl(args.history)[: args.limit]
    rows = []
    for rec in records:
        row = diagnose_one(rec, args.seed)
        rows.append(row)
        print(
            f"[diagnose] {rec['uuid'][:8]} n={row['n']} size={row['clique_size']} "
            f"phase={row['best_from_phase']} t_best={row['time_to_best_ms']:.1f}ms "
            f"incomplete={row['search_incomplete_at_deadline']} "
            f"viol={row['response_deadline_violation']} "
            f"cps={row['checkpoints']}",
            flush=True,
        )

    summary = {
        "rounds": len(rows),
        "mean_size": sum(r["clique_size"] for r in rows) / max(1, len(rows)),
        "timeout_rate": sum(1 for r in rows if r["deadline_reached"]) / max(1, len(rows)),
        "incomplete_rate": sum(1 for r in rows if r["search_incomplete_at_deadline"])
        / max(1, len(rows)),
        "deadline_violation_rate": sum(1 for r in rows if r["response_deadline_violation"])
        / max(1, len(rows)),
        "bnb_improved_rate": sum(1 for r in rows if r["bnb_improved_over_greedy"])
        / max(1, len(rows)),
        "best_from_greedy_rate": sum(1 for r in rows if r["best_from_phase"] == "greedy")
        / max(1, len(rows)),
        "mean_time_to_best_ms": sum(float(r["time_to_best_ms"] or 0) for r in rows)
        / max(1, len(rows)),
        "mean_improvements": sum(int(r["incumbent_improvements"] or 0) for r in rows)
        / max(1, len(rows)),
    }
    payload = {"summary": summary, "rounds": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
