"""Score Phase 4A solvers and write comparison artifacts."""

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
    "adaptive_portfolio",
    "global_spectral",
    "anchored_spectral",
    "global_spectral_plus_ikls",
    "anchored_spectral_plus_ikls",
    "spectral_portfolio",
)
HARD = {"1987b6bb", "577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0"}


def load_rows(results_dir: Path, solver: str) -> Dict[str, Dict[str, Any]]:
    path = results_dir / f"phase4a_{solver}_responses.jsonl"
    # portfolio may be copied from phase3
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
    if n <= 1:
        return 100.0
    return 100.0 * (n - rank) / (n - 1)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--results-dir", type=Path, default=RESULTS)
    p.add_argument("--solvers", nargs="*", default=list(SOLVERS))
    args = p.parse_args()

    records = load_jsonl(args.history)
    all_rounds: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}
    diag: Dict[str, Any] = {"per_solver": {}}

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
            row = {
                "uuid": uuid,
                "uuid8": uuid[:8],
                "solver": solver,
                "vertices": rec["number_of_nodes"],
                "time_limit": rec["time_limit"],
                "historical_best_clique_size": hist_best,
                "my_size": mine["clique_size"],
                "gap_vs_hist_best": hist_best - mine["clique_size"],
                "reward": float(scored.rewards[idx]),
                "diversity": float(scored.diversity[idx]),
                "optimality": float(scored.optimality[idx]),
                "reward_rank": rnk,
                "percentile": percentile(rnk, pool),
                "valid": mine["valid"],
                "response_deadline_violation": mine.get("response_deadline_violation"),
                "runtime_ms": mine.get("runtime_ms"),
                "spectral_ms": mine.get("spectral_ms"),
                "hard_graph": uuid[:8] in HARD,
            }
            rows.append(row)
        all_rounds.extend(rows)
        n = len(rows)
        hard_rows = [r for r in rows if r["hard_graph"]]
        summaries[solver] = {
            "rounds": n,
            "mean_clique_size": sum(r["my_size"] for r in rows) / max(1, n),
            "mean_gap": sum(r["gap_vs_hist_best"] for r in rows) / max(1, n),
            "mean_reward": sum(r["reward"] for r in rows) / max(1, n),
            "mean_diversity": sum(r["diversity"] for r in rows) / max(1, n),
            "mean_percentile": sum(r["percentile"] for r in rows) / max(1, n),
            "top1": sum(1 for r in rows if r["reward_rank"] == 1),
            "hist_best_ties": sum(1 for r in rows if r["gap_vs_hist_best"] == 0),
            "validity_rate": sum(1 for r in rows if r["valid"]) / max(1, n),
            "deadline_violation_rate": sum(1 for r in rows if r["response_deadline_violation"]) / max(1, n),
            "hard_mean_gap": sum(r["gap_vs_hist_best"] for r in hard_rows) / max(1, len(hard_rows)),
            "mean_spectral_ms": sum((r.get("spectral_ms") or 0) for r in rows) / max(1, n),
        }
        diag["per_solver"][solver] = {
            "hard_sizes": {r["uuid8"]: r["my_size"] for r in hard_rows},
            "hard_gaps": {r["uuid8"]: r["gap_vs_hist_best"] for r in hard_rows},
        }

    by_uuid: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        by_uuid[rec["uuid"]] = {
            "uuid": rec["uuid"],
            "uuid8": rec["uuid"][:8],
            "vertices": rec["number_of_nodes"],
            "time_limit": rec["time_limit"],
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
    # paired delta vs portfolio
    paired = []
    for r in rounds:
        base = r.get("adaptive_portfolio_size")
        if base is None:
            continue
        for s in args.solvers:
            if s == "adaptive_portfolio":
                continue
            if f"{s}_size" in r:
                paired.append(
                    {
                        "uuid8": r["uuid8"],
                        "solver": s,
                        "delta_size": r[f"{s}_size"] - base,
                        "delta_gap": r[f"{s}_gap"] - r.get("adaptive_portfolio_gap", 0),
                    }
                )

    def keyfn(s):
        sm = summaries[s]
        return (-sm["mean_gap"], sm["mean_reward"], sm["mean_percentile"])

    best = max(summaries, key=keyfn) if summaries else None
    out_csv = args.results_dir / "phase4a_round_comparison.csv"
    out_json = args.results_dir / "phase4a_round_comparison.json"
    out_rank = args.results_dir / "phase4a_rank_summary.json"
    out_diag = args.results_dir / "phase4a_spectral_diagnostics.json"

    out_json.write_text(json.dumps(rounds, indent=2))
    out_rank.write_text(json.dumps({"summaries": summaries, "best_solver": best, "paired_vs_portfolio": paired}, indent=2))
    if rounds:
        keys = sorted({k for r in rounds for k in r})
        with out_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rounds)
    diag["summaries"] = summaries
    diag["best_solver"] = best
    out_diag.write_text(json.dumps(diag, indent=2))
    print(json.dumps(summaries, indent=2))
    print("best_solver", best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
