"""Counterfactual official scoring for Phase-3 solvers (independent pools)."""

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
SOLVERS = (
    "triangle_guided",
    "bls_adaptive",
    "pls_penalty",
    "ikls_variable_depth",
    "pair_anchor",
    "adaptive_portfolio",
)
HARD = {"577e9988", "1231dc5e", "1db8cfb3", "4c69bfb1", "9bd55ea0"}


def load_rows(results_dir: Path, solver: str) -> Dict[str, Dict[str, Any]]:
    path = results_dir / f"phase3_{solver}_responses.jsonl"
    out: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["uuid"]] = row
    return out


def rank_of(arr: np.ndarray, idx: int) -> int:
    return int(np.sum(arr > arr[idx]) + 1)


def percentile(rank: int, n: int) -> float:
    if n <= 1:
        return 100.0
    return 100.0 * (n - rank) / (n - 1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--results-dir", type=Path, default=RESULTS)
    p.add_argument("--solvers", nargs="*", default=list(SOLVERS))
    args = p.parse_args(argv)

    records = load_jsonl(args.history)
    all_rounds: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}
    diversity_rows: List[Dict[str, Any]] = []

    for solver in args.solvers:
        srows = load_rows(args.results_dir, solver)
        rows = []
        for rec in records:
            uuid = rec["uuid"]
            mine = srows.get(uuid)
            if not mine:
                continue
            hist_best = max((len(a) for a in rec["miner_ans"]), default=0)
            view = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
            responses = list(rec["miner_ans"]) + [mine["clique"]]
            scored = CliqueScoreCalculator(view, float(rec["difficulty"]), responses).score_detailed()
            idx = len(responses) - 1
            rnk = rank_of(scored.rewards, idx)
            pool = len(responses)
            # unique best-size count among valid
            sizes = scored.effective_size
            best_sz = float(np.max(sizes)) if len(sizes) else 0.0
            unique_best = int(np.sum(sizes == best_sz))
            row = {
                "uuid": uuid,
                "solver": solver,
                "vertices": rec["number_of_nodes"],
                "difficulty": rec["difficulty"],
                "time_limit": rec["time_limit"],
                "historical_best_clique_size": hist_best,
                "my_size": mine["clique_size"],
                "gap_vs_hist_best": hist_best - mine["clique_size"],
                "reward": float(scored.rewards[idx]),
                "diversity": float(scored.diversity[idx]),
                "optimality": float(scored.optimality[idx]),
                "reward_rank": rnk,
                "pool_size": pool,
                "percentile": percentile(rnk, pool),
                "valid": mine["valid"],
                "timeout": mine.get("timeout"),
                "response_deadline_violation": mine.get("response_deadline_violation"),
                "runtime_ms": mine.get("runtime_ms"),
                "time_to_best_ms": mine.get("time_to_best_ms"),
                "unique_best_clique_count": unique_best,
                "hard_graph": uuid[:8] in HARD or any(uuid.startswith(h) for h in HARD),
            }
            rows.append(row)
            diversity_rows.append(
                {
                    "uuid": uuid[:8],
                    "solver": solver,
                    "size": row["my_size"],
                    "hist_best": hist_best,
                    "diversity": row["diversity"],
                    "optimality": row["optimality"],
                    "reward": row["reward"],
                    "rank": rnk,
                    "unique_best_in_pool": unique_best,
                }
            )
        all_rounds.extend(rows)
        n = len(rows)
        hard_rows = [r for r in rows if r["hard_graph"]]
        summaries[solver] = {
            "rounds": n,
            "mean_clique_size": sum(r["my_size"] for r in rows) / max(1, n),
            "mean_gap": sum(r["gap_vs_hist_best"] for r in rows) / max(1, n),
            "mean_reward": sum(r["reward"] for r in rows) / max(1, n),
            "mean_diversity": sum(r["diversity"] for r in rows) / max(1, n),
            "mean_rank": sum(r["reward_rank"] for r in rows) / max(1, n),
            "mean_percentile": sum(r["percentile"] for r in rows) / max(1, n),
            "top1": sum(1 for r in rows if r["reward_rank"] == 1),
            "top3": sum(1 for r in rows if r["reward_rank"] <= 3),
            "hist_best_ties": sum(1 for r in rows if r["gap_vs_hist_best"] == 0),
            "hist_best_exceed": sum(1 for r in rows if r["gap_vs_hist_best"] < 0),
            "validity_rate": sum(1 for r in rows if r["valid"]) / max(1, n),
            "deadline_violation_rate": sum(1 for r in rows if r["response_deadline_violation"]) / max(1, n),
            "hard_mean_gap": sum(r["gap_vs_hist_best"] for r in hard_rows) / max(1, len(hard_rows)),
            "hard_mean_size": sum(r["my_size"] for r in hard_rows) / max(1, len(hard_rows)),
            "hard_rounds": len(hard_rows),
        }

    # pivot
    by_uuid: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        by_uuid[rec["uuid"]] = {
            "uuid": rec["uuid"],
            "vertices": rec["number_of_nodes"],
            "time_limit": rec["time_limit"],
            "difficulty": rec["difficulty"],
            "historical_best_clique_size": max((len(a) for a in rec["miner_ans"]), default=0),
            "hard_graph": rec["uuid"][:8] in HARD,
        }
    for row in all_rounds:
        u = by_uuid[row["uuid"]]
        s = row["solver"]
        u[f"{s}_size"] = row["my_size"]
        u[f"{s}_reward"] = row["reward"]
        u[f"{s}_diversity"] = row["diversity"]
        u[f"{s}_rank"] = row["reward_rank"]
        u[f"{s}_percentile"] = row["percentile"]
        u[f"{s}_gap"] = row["gap_vs_hist_best"]

    rounds = list(by_uuid.values())
    out_json = args.results_dir / "phase3_round_comparison.json"
    out_csv = args.results_dir / "phase3_round_comparison.csv"
    out_rank = args.results_dir / "phase3_rank_summary.json"
    out_div = args.results_dir / "phase3_diversity_analysis.csv"

    # choose best by mean_gap then reward then percentile
    def keyfn(s):
        sm = summaries[s]
        return (-sm["mean_gap"], sm["mean_reward"], sm["mean_percentile"])

    best = max(summaries, key=keyfn) if summaries else None
    out_json.write_text(json.dumps(rounds, indent=2))
    out_rank.write_text(json.dumps({"summaries": summaries, "best_solver": best}, indent=2))
    if rounds:
        keys = sorted({k for r in rounds for k in r})
        with out_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rounds)
    with out_div.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(diversity_rows[0].keys()) if diversity_rows else ["uuid"])
        w.writeheader()
        w.writerows(diversity_rows)

    print(json.dumps(summaries, indent=2))
    print("best_solver", best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
