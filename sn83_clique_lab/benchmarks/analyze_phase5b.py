"""Official scoring, basin overlap, and ablations for Phase 5B."""

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

from clique.bitset import list_to_mask
from clique.history import load_jsonl
from clique.sn83_scoring import CliqueScoreCalculator, GraphView

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"
SOLVERS = (
    "revo_no_model",
    "mis_random_restart",
    "mis_configuration_search",
    "numvc_complement",
    "numvc_diversified",
)
HARD = {"577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0"}


def load_rows(results_dir: Path, solver: str) -> Dict[str, Dict[str, Any]]:
    path = results_dir / f"phase5b_{solver}_responses.jsonl"
    if not path.exists() and solver == "revo_no_model":
        for alt in (
            results_dir / "phase4b_revo_no_model_responses.jsonl",
            results_dir / "phase5a_revo_no_model_responses.jsonl",
        ):
            if alt.exists():
                path = alt
                break
    out: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["uuid"]] = row
    return out


def jaccard(a: List[int], b: List[int]) -> float:
    if not a and not b:
        return 1.0
    am, bm = list_to_mask(a), list_to_mask(b)
    inter = (am & bm).bit_count()
    union = (am | bm).bit_count()
    return inter / union if union else 0.0


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
    revo_rows = load_rows(args.results_dir, "revo_no_model")
    all_rounds: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}
    basin_rows: List[Dict[str, Any]] = []
    edge_diag: Dict[str, Any] = {}

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
            gap = hist_best - mine["clique_size"]
            revo = revo_rows.get(rec["uuid"])
            jac_revo = jaccard(mine["clique"], revo["clique"]) if revo else None
            # post-hoc vs historical best-sized
            hist_best_cliques = [a for a in rec["miner_ans"] if len(a) == hist_best]
            jac_hist = (
                max(jaccard(mine["clique"], h) for h in hist_best_cliques) if hist_best_cliques else None
            )
            row = {
                "uuid": rec["uuid"],
                "uuid8": rec["uuid"][:8],
                "solver": solver,
                "vertices": rec["number_of_nodes"],
                "time_limit": rec["time_limit"],
                "historical_best_clique_size": hist_best,
                "my_size": mine["clique_size"],
                "gap_vs_hist_best": gap,
                "reward": float(scored.rewards[idx]),
                "diversity": float(scored.diversity[idx]),
                "optimality": float(scored.optimality[idx]),
                "reward_rank": rnk,
                "percentile": percentile(rnk, len(responses)),
                "top1": rnk == 1,
                "top3": rnk <= 3,
                "valid": mine["valid"],
                "maximal": mine.get("maximal", True),
                "response_deadline_violation": mine.get("response_deadline_violation"),
                "complement_density": mine.get("complement_density"),
                "search_steps": mine.get("search_steps") or 0,
                "steps_per_second": mine.get("steps_per_second"),
                "jaccard_vs_revo": jac_revo,
                "jaccard_vs_hist_best": jac_hist,
                "hard_graph": rec["uuid"][:8] in HARD,
            }
            rows.append(row)
            if solver != "revo_no_model":
                basin_rows.append(
                    {
                        "uuid8": rec["uuid"][:8],
                        "solver": solver,
                        "size": mine["clique_size"],
                        "revo_size": revo["clique_size"] if revo else None,
                        "jaccard_vs_revo": jac_revo,
                        "jaccard_vs_hist_best": jac_hist,
                        "hard": rec["uuid"][:8] in HARD,
                    }
                )
        all_rounds.extend(rows)
        n = len(rows)
        hard = [r for r in rows if r["hard_graph"]]
        improvements = ties = regressions = 0
        for r in rows:
            base = revo_rows.get(r["uuid"])
            if not base or solver == "revo_no_model":
                continue
            if r["my_size"] > base["clique_size"]:
                improvements += 1
            elif r["my_size"] == base["clique_size"]:
                ties += 1
            else:
                regressions += 1
        jac_vals = [r["jaccard_vs_revo"] for r in rows if r["jaccard_vs_revo"] is not None]
        summaries[solver] = {
            "rounds": n,
            "mean_clique_size": sum(r["my_size"] for r in rows) / max(1, n),
            "mean_gap": sum(r["gap_vs_hist_best"] for r in rows) / max(1, n),
            "mean_reward": sum(r["reward"] for r in rows) / max(1, n),
            "mean_diversity": sum(r["diversity"] for r in rows) / max(1, n),
            "mean_percentile": sum(r["percentile"] for r in rows) / max(1, n),
            "top1": sum(1 for r in rows if r["top1"]),
            "top3": sum(1 for r in rows if r["top3"]),
            "hist_best_ties": sum(1 for r in rows if r["gap_vs_hist_best"] == 0),
            "hist_best_exceeds": sum(1 for r in rows if r["gap_vs_hist_best"] < 0),
            "validity_rate": sum(1 for r in rows if r["valid"]) / max(1, n),
            "deadline_violation_rate": sum(1 for r in rows if r["response_deadline_violation"])
            / max(1, n),
            "hard_mean_gap": sum(r["gap_vs_hist_best"] for r in hard) / max(1, len(hard)),
            "vs_revo_improvements": improvements,
            "vs_revo_ties": ties,
            "vs_revo_regressions": regressions,
            "mean_jaccard_vs_revo": sum(jac_vals) / len(jac_vals) if jac_vals else None,
            "mean_complement_density": sum((r.get("complement_density") or 0) for r in rows) / max(1, n),
            "mean_search_steps": sum(r["search_steps"] for r in rows) / max(1, n),
        }
        edge_diag[solver] = {
            "mean_steps": summaries[solver]["mean_search_steps"],
            "hard": {
                r["uuid8"]: {
                    "size": r["my_size"],
                    "gap": r["gap_vs_hist_best"],
                    "jac_revo": r["jaccard_vs_revo"],
                    "jac_hist": r["jaccard_vs_hist_best"],
                    "cdens": r["complement_density"],
                }
                for r in hard
            },
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
        u[f"{s}_percentile"] = row["percentile"]
        u[f"{s}_rank"] = row["reward_rank"]
        if row["jaccard_vs_revo"] is not None:
            u[f"{s}_jac_revo"] = row["jaccard_vs_revo"]

    rounds = list(by_uuid.values())

    def keyfn(s):
        sm = summaries[s]
        return (-sm["mean_gap"], sm["mean_reward"], sm["mean_percentile"], -sm["vs_revo_regressions"])

    best = max(summaries, key=keyfn) if summaries else None
    recommendation = "retain_revo_no_model"
    if best and best != "revo_no_model":
        sm = summaries[best]
        base = summaries.get("revo_no_model", {})
        if (
            sm.get("mean_gap", 99) < base.get("mean_gap", 99)
            and sm.get("vs_revo_regressions", 99) == 0
            and sm.get("validity_rate", 0) >= 1.0
        ):
            recommendation = f"use_{best}"
        elif sm.get("mean_jaccard_vs_revo") is not None and sm["mean_jaccard_vs_revo"] < 0.3:
            if sm.get("mean_gap", 99) <= base.get("mean_gap", 99) + 0.05:
                recommendation = "research_further"

    out = {
        "summaries": summaries,
        "best_solver": best,
        "recommendation": recommendation,
        "edge_diagnostics": edge_diag,
    }
    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / "phase5b_multiseed_summary.json").write_text(json.dumps(out, indent=2))
    (args.results_dir / "phase5b_edge_weight_diagnostics.json").write_text(json.dumps(edge_diag, indent=2))
    (args.results_dir / "phase5b_round_comparison.json").write_text(json.dumps(rounds, indent=2))
    if rounds:
        keys = sorted({k for r in rounds for k in r})
        with (args.results_dir / "phase5b_round_comparison.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rounds)
    if basin_rows:
        with (args.results_dir / "phase5b_basin_overlap.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(basin_rows[0].keys()))
            w.writeheader()
            w.writerows(basin_rows)
    abl = [{"config": k, **v} for k, v in summaries.items()]
    if abl:
        with (args.results_dir / "phase5b_ablation.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(abl[0].keys()))
            w.writeheader()
            w.writerows(abl)
    print(json.dumps(summaries, indent=2))
    print("best_solver", best)
    print("recommendation", recommendation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
