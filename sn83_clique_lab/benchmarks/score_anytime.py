"""Counterfactual official scoring for anytime solvers (independent pools)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.history import load_jsonl
from clique.sn83_scoring import CliqueScoreCalculator, GraphView

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"
SOLVERS = ("baseline", "multistart_greedy", "swap_local_search", "triangle_guided")


def load_solver_rows(results_dir: Path, solver: str) -> Dict[str, Dict[str, Any]]:
    path = results_dir / f"anytime_{solver}_responses.jsonl"
    out: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["uuid"]] = row
    return out


def rank_of(rewards: np.ndarray, idx: int) -> int:
    """1 = best reward."""
    my = rewards[idx]
    return int(np.sum(rewards > my) + 1)


def percentile(rank: int, n: int) -> float:
    if n <= 1:
        return 100.0
    return 100.0 * (n - rank) / (n - 1)


def evaluate_solver(
    records: List[Dict[str, Any]],
    solver_rows: Dict[str, Dict[str, Any]],
    solver: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in records:
        uuid = rec["uuid"]
        mine = solver_rows.get(uuid)
        if mine is None:
            continue
        hist_sizes = [len(a) for a in rec["miner_ans"]]
        hist_best = max(hist_sizes) if hist_sizes else 0
        view = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
        responses = list(rec["miner_ans"]) + [mine["clique"]]
        calc = CliqueScoreCalculator(view, float(rec["difficulty"]), responses)
        scored = calc.score_detailed()
        my_index = len(responses) - 1
        my_reward = float(scored.rewards[my_index])
        my_div = float(scored.diversity[my_index])
        my_opt = float(scored.optimality[my_index])
        pool = len(responses)
        rnk = rank_of(scored.rewards, my_index)
        size_rank = rank_of(scored.effective_size, my_index)
        rows.append(
            {
                "uuid": uuid,
                "solver": solver,
                "vertices": rec["number_of_nodes"],
                "density": mine.get("density"),
                "difficulty": rec["difficulty"],
                "time_limit": rec["time_limit"],
                "historical_miner_count": len(rec["miner_uids"]),
                "historical_best_clique_size": hist_best,
                "my_size": mine["clique_size"],
                "gap_vs_hist_best": hist_best - mine["clique_size"],
                "reward": my_reward,
                "diversity": my_div,
                "optimality": my_opt,
                "reward_rank": rnk,
                "size_rank": size_rank,
                "pool_size": pool,
                "percentile": percentile(rnk, pool),
                "valid": mine["valid"],
                "timeout": mine.get("timeout"),
                "response_deadline_violation": mine.get("response_deadline_violation"),
                "runtime_ms": mine.get("runtime_ms"),
                "checkpoints": mine.get("checkpoints"),
            }
        )
    return rows


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if not n:
        return {"rounds": 0}
    return {
        "rounds": n,
        "mean_clique_size": sum(r["my_size"] for r in rows) / n,
        "mean_gap": sum(r["gap_vs_hist_best"] for r in rows) / n,
        "mean_reward": sum(r["reward"] for r in rows) / n,
        "mean_rank": sum(r["reward_rank"] for r in rows) / n,
        "mean_percentile": sum(r["percentile"] for r in rows) / n,
        "top1": sum(1 for r in rows if r["reward_rank"] == 1),
        "top3": sum(1 for r in rows if r["reward_rank"] <= 3),
        "hist_best_ties": sum(1 for r in rows if r["gap_vs_hist_best"] == 0),
        "hist_best_exceed": sum(1 for r in rows if r["gap_vs_hist_best"] < 0),
        "validity_rate": sum(1 for r in rows if r["valid"]) / n,
        "timeout_rate": sum(1 for r in rows if r["timeout"]) / n,
        "deadline_violation_rate": sum(1 for r in rows if r["response_deadline_violation"]) / n,
    }


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--results-dir", type=Path, default=RESULTS)
    p.add_argument("--solvers", nargs="*", default=list(SOLVERS))
    args = p.parse_args(argv)

    records = load_jsonl(args.history)
    all_rounds: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}
    for solver in args.solvers:
        srows = load_solver_rows(args.results_dir, solver)
        rows = evaluate_solver(records, srows, solver)
        all_rounds.extend(rows)
        summaries[solver] = summarize(rows)

    # Pivot round comparison
    by_uuid: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        by_uuid[rec["uuid"]] = {
            "uuid": rec["uuid"],
            "vertices": rec["number_of_nodes"],
            "time_limit": rec["time_limit"],
            "difficulty": rec["difficulty"],
            "historical_best_clique_size": max((len(a) for a in rec["miner_ans"]), default=0),
        }
    for row in all_rounds:
        u = by_uuid[row["uuid"]]
        s = row["solver"]
        u[f"{s}_size"] = row["my_size"]
        u[f"{s}_reward"] = row["reward"]
        u[f"{s}_rank"] = row["reward_rank"]
        u[f"{s}_percentile"] = row["percentile"]
        u[f"{s}_gap"] = row["gap_vs_hist_best"]
        u[f"{s}_diversity"] = row["diversity"]

    rounds = list(by_uuid.values())
    out_json = args.results_dir / "anytime_round_comparison.json"
    out_csv = args.results_dir / "anytime_round_comparison.csv"
    out_rank = args.results_dir / "anytime_rank_summary.json"
    out_json.write_text(json.dumps(rounds, indent=2))
    out_rank.write_text(json.dumps({"summaries": summaries, "best_solver": max(
        summaries, key=lambda s: (summaries[s].get("mean_percentile", -1), summaries[s].get("mean_reward", -1))
    ) if summaries else None}, indent=2))

    if rounds:
        keys = sorted({k for r in rounds for k in r})
        with out_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rounds:
                w.writerow(r)

    print(json.dumps(summaries, indent=2))
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
