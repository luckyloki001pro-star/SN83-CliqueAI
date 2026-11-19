"""Insert local solver answers into historical pools and rescore."""

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

from clique.history import graph_checks, load_jsonl
from clique.sn83_scoring import CliqueScoreCalculator, GraphView, competition_rank

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"
SOLVERS = ("baseline", "ulm", "selective_ulm")


def load_solver_map(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    return {row["uuid"]: row for row in load_jsonl(path)}


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--results-dir", type=Path, default=RESULTS)
    args = p.parse_args(argv)

    if not args.history.exists():
        print(json.dumps({"error": f"missing {args.history}"}, indent=2))
        return 2

    history = load_jsonl(args.history)
    solver_maps = {
        s: load_solver_map(args.results_dir / f"{s}_responses.jsonl") for s in SOLVERS
    }
    verification = {}
    ver_path = args.results_dir / "historical_score_verification.json"
    if ver_path.exists():
        for row in json.loads(ver_path.read_text()):
            verification[row["uuid"]] = row

    rounds: List[Dict[str, Any]] = []
    detailed: List[Dict[str, Any]] = []

    for rec in history:
        uuid = rec["uuid"]
        ginfo = graph_checks(rec)
        hist_sizes = []
        view = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
        # Historical best valid size from independent check.
        base_calc = CliqueScoreCalculator(view, float(rec["difficulty"]), rec["miner_ans"])
        base_scores = base_calc.score_detailed()
        hist_best = int(np.max(base_scores.effective_size)) if len(base_scores.effective_size) else 0
        ver = verification.get(uuid, {})

        round_row: Dict[str, Any] = {
            "timestamp": rec["timestamp"],
            "uuid": uuid,
            "vertices": rec["number_of_nodes"],
            "density": ginfo.get("density"),
            "difficulty": rec["difficulty"],
            "time_limit": rec["time_limit"],
            "historical_miner_count": len(rec["miner_uids"]),
            "historical_best_clique_size": hist_best,
            "historical_score_reproduction_status": (
                "ok" if ver.get("reproduction_ok") else ("fail" if ver else "unknown")
            ),
        }

        for solver in SOLVERS:
            mine = solver_maps[solver].get(uuid)
            size_key = f"my_{solver}_size"
            reward_key = f"{solver}_reward"
            rank_key = f"{solver}_rank"
            runtime_key = f"{solver}_runtime_ms"
            if mine is None:
                round_row[size_key] = None
                round_row[reward_key] = None
                round_row[rank_key] = None
                round_row[runtime_key] = None
                continue

            # Counterfactual pool = historical answers + my answer.
            responses = list(rec["miner_ans"]) + [mine["clique"]]
            calc = CliqueScoreCalculator(view, float(rec["difficulty"]), responses)
            scored = calc.score_detailed()
            my_idx = len(responses) - 1
            my_reward = float(scored.rewards[my_idx])
            reward_rank, reward_ties = competition_rank(scored.rewards, my_idx)
            size_rank, size_ties = competition_rank(scored.effective_size, my_idx)
            n_pool = len(responses)
            percentile = 100.0 * (1.0 - (reward_rank - 1) / max(n_pool, 1))

            larger = int(np.sum(scored.effective_size > scored.effective_size[my_idx]))
            equal = int(np.sum(scored.effective_size == scored.effective_size[my_idx])) - 1
            smaller = int(np.sum(scored.effective_size < scored.effective_size[my_idx]))
            canonical = tuple(sorted(mine["clique"]))
            identical = sum(1 for ans in rec["miner_ans"] if tuple(sorted(ans)) == canonical)

            round_row[size_key] = mine["clique_size"]
            round_row[reward_key] = my_reward
            round_row[rank_key] = reward_rank
            round_row[runtime_key] = mine["runtime_ms"]
            round_row[f"{solver}_size_rank"] = size_rank
            round_row[f"{solver}_percentile"] = percentile
            round_row[f"{solver}_optimality"] = float(scored.optimality[my_idx])
            round_row[f"{solver}_diversity"] = float(scored.diversity[my_idx])
            round_row[f"{solver}_valid"] = bool(scored.validity[my_idx])
            round_row[f"{solver}_gap_vs_hist_best"] = hist_best - int(scored.effective_size[my_idx])
            round_row[f"{solver}_unique"] = identical == 0
            round_row[f"{solver}_identical_historical"] = identical
            round_row[f"{solver}_reward_ties"] = reward_ties
            round_row[f"{solver}_larger_cliques"] = larger
            round_row[f"{solver}_equal_cliques"] = equal
            round_row[f"{solver}_smaller_cliques"] = smaller
            round_row[f"{solver}_timeout"] = mine.get("timeout", False)

            detailed.append(
                {
                    "uuid": uuid,
                    "solver": solver,
                    "my_index": my_idx,
                    "pool_size": n_pool,
                    "my_clique": mine["clique"],
                    "my_size": mine["clique_size"],
                    "my_reward": my_reward,
                    "reward_rank": reward_rank,
                    "size_rank": size_rank,
                    "percentile": percentile,
                    "recomputed_all_rewards": scored.rewards.tolist(),
                    "recomputed_all_sizes": scored.effective_size.tolist(),
                    "note": (
                        "Counterfactual evaluation: peer rewards recomputed after insertion; "
                        "not directly comparable to unchanged logged historical rewards."
                    ),
                }
            )

        rounds.append(round_row)

    args.results_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.results_dir / "round_comparison.json"
    csv_path = args.results_dir / "round_comparison.csv"
    json_path.write_text(json.dumps(rounds, indent=2))
    if rounds:
        # Stable column order preference.
        preferred = [
            "timestamp",
            "uuid",
            "vertices",
            "density",
            "difficulty",
            "time_limit",
            "historical_miner_count",
            "historical_best_clique_size",
            "my_baseline_size",
            "my_ulm_size",
            "my_selective_ulm_size",
            "baseline_reward",
            "ulm_reward",
            "selective_ulm_reward",
            "baseline_rank",
            "ulm_rank",
            "selective_ulm_rank",
            "baseline_runtime_ms",
            "ulm_runtime_ms",
            "selective_ulm_runtime_ms",
            "historical_score_reproduction_status",
        ]
        fields = preferred + [k for k in rounds[0].keys() if k not in preferred]
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rounds)

    (args.results_dir / "counterfactual_details.json").write_text(
        json.dumps(detailed, indent=2)
    )
    print(json.dumps({"rounds": len(rounds), "csv": str(csv_path)}, indent=2))
    return 0 if rounds else 2


if __name__ == "__main__":
    raise SystemExit(main())
