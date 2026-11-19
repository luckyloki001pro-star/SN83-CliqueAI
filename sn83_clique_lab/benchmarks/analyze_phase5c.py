"""Score Phase 5C schedules and summarize discovery curves."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
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
HARD = {"577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0"}


def load_solver(results_dir: Path, solver: str) -> Dict[str, Dict[str, Any]]:
    path = results_dir / f"phase5c_{solver}_responses.jsonl"
    if not path.exists() and solver == "full_revo":
        for alt in (
            results_dir / "phase4b_revo_no_model_responses.jsonl",
            results_dir / "phase5b_revo_no_model_responses.jsonl",
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
    am, bm = list_to_mask(a), list_to_mask(b)
    inter = (am & bm).bit_count()
    union = (am | bm).bit_count()
    return inter / union if union else 0.0


def rank_of(arr: np.ndarray, idx: int) -> int:
    return int(np.sum(arr > arr[idx]) + 1)


def percentile(rank: int, n: int) -> float:
    return 100.0 * (n - rank) / (n - 1) if n > 1 else 100.0


def analyze_discovery(results_dir: Path) -> Dict[str, Any]:
    path = results_dir / "phase5c_discovery_curves.csv"
    if not path.exists():
        return {}
    rows = list(csv.DictReader(path.open()))
    by = defaultdict(list)
    for r in rows:
        by[(r["uuid8"], r["solver"])].append(r)
    summary = {}
    for (uuid8, solver), rs in by.items():
        sizes = [int(float(r["best_size"])) for r in rs]
        hist = int(float(rs[0]["historical_best"]))
        ttb = [float(r["time_to_best_ms"]) for r in rs]
        summary[f"{uuid8}:{solver}"] = {
            "n_seeds": len(rs),
            "mean_size": sum(sizes) / len(sizes),
            "median_size": float(np.median(sizes)),
            "max_size": max(sizes),
            "match_hist_frac": sum(1 for s in sizes if s >= hist) / len(sizes),
            "mean_ttb_ms": sum(ttb) / len(ttb),
            "size_hist": {str(k): sizes.count(k) for k in sorted(set(sizes))},
        }
    # 577 special
    key = "577e9988:numvc_complement"
    if key in summary:
        summary["577e9988_numvc_57_count"] = summary[key]["size_hist"].get("57", 0)
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--results-dir", type=Path, default=RESULTS)
    p.add_argument("--solvers", nargs="*", default=None)
    args = p.parse_args()

    # discover solvers from files
    if args.solvers:
        solvers = list(args.solvers)
    else:
        solvers = sorted(
            {
                f.name[len("phase5c_") : -len("_responses.jsonl")]
                for f in args.results_dir.glob("phase5c_*_responses.jsonl")
            }
        )
        if "full_revo" not in solvers:
            solvers = ["full_revo", *solvers]

    records = load_jsonl(args.history)
    revo = load_solver(args.results_dir, "full_revo")
    if not revo:
        revo = load_solver(args.results_dir, "revo_no_model")
    summaries: Dict[str, Any] = {}
    rounds_by_uuid: Dict[str, Dict[str, Any]] = {}
    basin: List[Dict[str, Any]] = []

    for rec in records:
        rounds_by_uuid[rec["uuid"]] = {
            "uuid": rec["uuid"],
            "uuid8": rec["uuid"][:8],
            "vertices": rec["number_of_nodes"],
            "time_limit": rec["time_limit"],
            "historical_best_clique_size": max((len(a) for a in rec["miner_ans"]), default=0),
            "hard_graph": rec["uuid"][:8] in HARD,
        }

    for solver in solvers:
        srows = load_solver(args.results_dir, solver)
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
            base = revo.get(rec["uuid"])
            delta = (mine["clique_size"] - base["clique_size"]) if base else None
            jac = jaccard(mine["clique"], base["clique"]) if base else None
            row = {
                "uuid8": rec["uuid"][:8],
                "solver": solver,
                "my_size": mine["clique_size"],
                "gap": hist_best - mine["clique_size"],
                "reward": float(scored.rewards[idx]),
                "diversity": float(scored.diversity[idx]),
                "percentile": percentile(rnk, len(responses)),
                "rank": rnk,
                "valid": mine["valid"],
                "delta_vs_revo": delta,
                "jaccard_vs_revo": jac,
                "source": mine.get("source"),
                "hard": rec["uuid"][:8] in HARD,
            }
            rows.append(row)
            u = rounds_by_uuid[rec["uuid"]]
            u[f"{solver}_size"] = mine["clique_size"]
            u[f"{solver}_reward"] = row["reward"]
            u[f"{solver}_percentile"] = row["percentile"]
            u[f"{solver}_gap"] = row["gap"]
            if jac is not None:
                u[f"{solver}_jac_revo"] = jac
            if delta is not None and solver != "full_revo":
                basin.append(
                    {
                        "uuid8": row["uuid8"],
                        "solver": solver,
                        "delta": delta,
                        "jaccard": jac,
                        "source": row["source"],
                        "hard": row["hard"],
                    }
                )
        n = len(rows)
        deltas = [r["delta_vs_revo"] for r in rows if r["delta_vs_revo"] is not None]
        summaries[solver] = {
            "rounds": n,
            "mean_size": sum(r["my_size"] for r in rows) / max(1, n),
            "mean_gap": sum(r["gap"] for r in rows) / max(1, n),
            "mean_reward": sum(r["reward"] for r in rows) / max(1, n),
            "mean_percentile": sum(r["percentile"] for r in rows) / max(1, n),
            "hist_best_ties": sum(1 for r in rows if r["gap"] == 0),
            "validity_rate": sum(1 for r in rows if r["valid"]) / max(1, n),
            "wins_vs_revo": sum(1 for d in deltas if d > 0),
            "ties_vs_revo": sum(1 for d in deltas if d == 0),
            "losses_vs_revo": sum(1 for d in deltas if d < 0),
            "mean_delta_vs_revo": (sum(deltas) / len(deltas)) if deltas else 0.0,
            "hard_mean_gap": sum(r["gap"] for r in rows if r["hard"]) / max(1, sum(1 for r in rows if r["hard"])),
        }

    rounds = list(rounds_by_uuid.values())
    disc = analyze_discovery(args.results_dir)

    def keyfn(s):
        sm = summaries[s]
        return (-sm["mean_gap"], sm["mean_reward"], -sm["losses_vs_revo"])

    best = max(summaries, key=keyfn) if summaries else None
    base = summaries.get("full_revo") or summaries.get("revo_no_model") or {}
    recommendation = "retain_revo_no_model"
    if best and best not in ("full_revo", "revo_no_model"):
        sm = summaries[best]
        if (
            sm.get("mean_gap", 99) < base.get("mean_gap", 99)
            and sm.get("losses_vs_revo", 99) == 0
            and sm.get("validity_rate", 0) >= 1.0
        ):
            recommendation = "adopt_adaptive_dual_portfolio" if "probe" in best or "stag" in best else "adopt_fixed_dual_portfolio"
        elif sm.get("wins_vs_revo", 0) > 0 and sm.get("losses_vs_revo", 0) <= 1:
            recommendation = "retain_numvc_as_optional_probe"
        else:
            recommendation = "research_further"

    out = {
        "summaries": summaries,
        "best_solver": best,
        "recommendation": recommendation,
        "discovery": disc,
    }
    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / "phase5c_multiseed_summary.json").write_text(json.dumps(out, indent=2))
    if rounds:
        keys = sorted({k for r in rounds for k in r})
        with (args.results_dir / "phase5c_round_comparison.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rounds)
    if basin:
        with (args.results_dir / "phase5c_basin_overlap.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(basin[0].keys()))
            w.writeheader()
            w.writerows(basin)
    abl = [{"config": k, **v} for k, v in summaries.items()]
    if abl:
        with (args.results_dir / "phase5c_ablation.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(abl[0].keys()))
            w.writeheader()
            w.writerows(abl)
        with (args.results_dir / "phase5c_fixed_schedules.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(abl[0].keys()))
            w.writeheader()
            w.writerows(abl)
        with (args.results_dir / "phase5c_adaptive_schedules.csv").open("w", newline="") as f:
            adaptive = [r for r in abl if any(x in r["config"] for x in ("probe", "stag", "adaptive"))]
            if adaptive:
                w = csv.DictWriter(f, fieldnames=list(adaptive[0].keys()))
                w.writeheader()
                w.writerows(adaptive)
    print(json.dumps(summaries, indent=2))
    print("best", best, "recommendation", recommendation)
    if disc:
        print("discovery_keys", list(disc.keys())[:8])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
