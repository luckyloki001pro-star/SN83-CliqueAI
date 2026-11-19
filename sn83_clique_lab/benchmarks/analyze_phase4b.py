"""Official scoring + ablations summary for Phase 4B."""

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
SOLVERS = ("adaptive_portfolio", "revo_no_model", "revo_population", "revo_diverse")
HARD = {"1987b6bb", "577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0"}


def load_rows(results_dir: Path, solver: str) -> Dict[str, Dict[str, Any]]:
    path = results_dir / f"phase4b_{solver}_responses.jsonl"
    if not path.exists() and solver == "adaptive_portfolio":
        path = results_dir / "phase3_adaptive_portfolio_responses.jsonl"
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
    return 100.0 * (n - rank) / (n - 1) if n > 1 else 100.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--results-dir", type=Path, default=RESULTS)
    p.add_argument("--solvers", nargs="*", default=list(SOLVERS))
    args = p.parse_args()

    records = load_jsonl(args.history)
    all_rounds: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}
    diagnostics: Dict[str, Any] = {"hard": {}, "learning": {}}

    for solver in args.solvers:
        srows = load_rows(args.results_dir, solver)
        rows = []
        for rec in records:
            mine = srows.get(rec["uuid"])
            if not mine:
                continue
            hist_best = max((len(a) for a in rec["miner_ans"]), default=0)
            view = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
            responses = list(rec["miner_ans"]) + [mine["clique"]]
            scored = CliqueScoreCalculator(view, float(rec["difficulty"]), responses).score_detailed()
            idx = len(responses) - 1
            rnk = rank_of(scored.rewards, idx)
            row = {
                "uuid": rec["uuid"],
                "uuid8": rec["uuid"][:8],
                "solver": solver,
                "vertices": rec["number_of_nodes"],
                "historical_best_clique_size": hist_best,
                "my_size": mine["clique_size"],
                "gap_vs_hist_best": hist_best - mine["clique_size"],
                "reward": float(scored.rewards[idx]),
                "diversity": float(scored.diversity[idx]),
                "optimality": float(scored.optimality[idx]),
                "reward_rank": rnk,
                "percentile": percentile(rnk, len(responses)),
                "valid": mine["valid"],
                "response_deadline_violation": mine.get("response_deadline_violation"),
                "time_to_best_ms": mine.get("time_to_best_ms"),
                "restarts": mine.get("restarts"),
                "model_updates": mine.get("model_updates"),
                "final_model_entropy": mine.get("final_model_entropy"),
                "final_jaccard": mine.get("final_jaccard"),
                "hard_graph": rec["uuid"][:8] in HARD,
            }
            rows.append(row)
        all_rounds.extend(rows)
        n = len(rows)
        hard = [r for r in rows if r["hard_graph"]]
        summaries[solver] = {
            "rounds": n,
            "mean_clique_size": sum(r["my_size"] for r in rows) / max(1, n),
            "mean_gap": sum(r["gap_vs_hist_best"] for r in rows) / max(1, n),
            "mean_reward": sum(r["reward"] for r in rows) / max(1, n),
            "mean_diversity": sum(r["diversity"] for r in rows) / max(1, n),
            "mean_percentile": sum(r["percentile"] for r in rows) / max(1, n),
            "top1": sum(1 for r in rows if r["reward_rank"] == 1),
            "top3": sum(1 for r in rows if r["reward_rank"] <= 3),
            "hist_best_ties": sum(1 for r in rows if r["gap_vs_hist_best"] == 0),
            "validity_rate": sum(1 for r in rows if r["valid"]) / max(1, n),
            "deadline_violation_rate": sum(1 for r in rows if r["response_deadline_violation"]) / max(1, n),
            "hard_mean_gap": sum(r["gap_vs_hist_best"] for r in hard) / max(1, len(hard)),
            "mean_restarts": sum((r.get("restarts") or 0) for r in rows) / max(1, n),
            "mean_model_updates": sum((r.get("model_updates") or 0) for r in rows) / max(1, n),
        }
        diagnostics["hard"][solver] = {r["uuid8"]: {"size": r["my_size"], "gap": r["gap_vs_hist_best"]} for r in hard}
        if solver.startswith("revo"):
            diagnostics["learning"][solver] = {
                "mean_entropy": sum((r.get("final_model_entropy") or 0) for r in rows) / max(1, n),
                "mean_jaccard": sum((r.get("final_jaccard") or 0) for r in rows) / max(1, n),
            }

    by_uuid: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        by_uuid[rec["uuid"]] = {
            "uuid": rec["uuid"],
            "uuid8": rec["uuid"][:8],
            "vertices": rec["number_of_nodes"],
            "historical_best_clique_size": max((len(a) for a in rec["miner_ans"]), default=0),
            "hard_graph": rec["uuid"][:8] in HARD,
        }
    for row in all_rounds:
        u = by_uuid[row["uuid"]]
        s = row["solver"]
        u[f"{s}_size"] = row["my_size"]
        u[f"{s}_gap"] = row["gap_vs_hist_best"]
        u[f"{s}_reward"] = row["reward"]
        u[f"{s}_rank"] = row["reward_rank"]
        u[f"{s}_percentile"] = row["percentile"]
        u[f"{s}_diversity"] = row["diversity"]

    rounds = list(by_uuid.values())
    paired = []
    for r in rounds:
        base = r.get("adaptive_portfolio_size")
        if base is None:
            continue
        for s in args.solvers:
            if s == "adaptive_portfolio" or f"{s}_size" not in r:
                continue
            paired.append({"uuid8": r["uuid8"], "solver": s, "delta_size": r[f"{s}_size"] - base})

    # learning ablation: B1 vs B0
    learning_gain = []
    for r in rounds:
        if "revo_population_size" in r and "revo_no_model_size" in r:
            learning_gain.append(
                {
                    "uuid8": r["uuid8"],
                    "delta_model_vs_nomodel": r["revo_population_size"] - r["revo_no_model_size"],
                }
            )

    def keyfn(s):
        sm = summaries[s]
        return (-sm["mean_gap"], sm["mean_reward"], sm["mean_percentile"])

    best = max(summaries, key=keyfn) if summaries else None
    out = {
        "summaries": summaries,
        "best_solver": best,
        "paired_vs_portfolio": paired,
        "learning_ablation_B1_vs_B0": learning_gain,
        "mean_learning_delta": (
            sum(x["delta_model_vs_nomodel"] for x in learning_gain) / len(learning_gain) if learning_gain else None
        ),
    }
    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / "phase4b_rank_summary.json").write_text(json.dumps(out, indent=2))
    (args.results_dir / "phase4b_round_comparison.json").write_text(json.dumps(rounds, indent=2))
    (args.results_dir / "phase4b_probability_diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    if rounds:
        keys = sorted({k for r in rounds for k in r})
        with (args.results_dir / "phase4b_round_comparison.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rounds)
    # ablation csv
    abl = [{"config": k, **v} for k, v in summaries.items()]
    if abl:
        with (args.results_dir / "phase4b_ablation.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(abl[0].keys()))
            w.writeheader()
            w.writerows(abl)
    print(json.dumps(summaries, indent=2))
    print("best_solver", best)
    print("mean_learning_delta B1-B0", out["mean_learning_delta"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
