"""Aggregate counterfactual ranks and cautious competitive prediction."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "results"
SOLVERS = ("baseline", "ulm", "selective_ulm")


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _median(xs: List[float]) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    m = len(ys) // 2
    return ys[m] if len(ys) % 2 else 0.5 * (ys[m - 1] + ys[m])


def _std(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = _mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def bootstrap_ci(
    values: List[float],
    stat_fn,
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> Dict[str, float]:
    rng = random.Random(seed)
    if not values:
        return {"point": float("nan"), "lo": float("nan"), "hi": float("nan")}
    point = stat_fn(values)
    boots = []
    n = len(values)
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        boots.append(stat_fn(sample))
    boots.sort()
    lo = boots[int((alpha / 2) * n_boot)]
    hi = boots[int((1 - alpha / 2) * n_boot) - 1]
    return {"point": point, "lo": lo, "hi": hi}


def summarize_solver(rounds: List[Dict[str, Any]], solver: str) -> Dict[str, Any]:
    rewards = [float(r[f"{solver}_reward"]) for r in rounds if r.get(f"{solver}_reward") is not None]
    ranks = [float(r[f"{solver}_rank"]) for r in rounds if r.get(f"{solver}_rank") is not None]
    percentiles = [
        float(r[f"{solver}_percentile"])
        for r in rounds
        if r.get(f"{solver}_percentile") is not None
    ]
    sizes = [float(r[f"my_{solver}_size"]) for r in rounds if r.get(f"my_{solver}_size") is not None]
    gaps = [
        float(r[f"{solver}_gap_vs_hist_best"])
        for r in rounds
        if r.get(f"{solver}_gap_vs_hist_best") is not None
    ]
    valids = [bool(r.get(f"{solver}_valid")) for r in rounds if f"{solver}_valid" in r]
    timeouts = [bool(r.get(f"{solver}_timeout")) for r in rounds if f"{solver}_timeout" in r]
    runtimes = [
        float(r[f"{solver}_runtime_ms"])
        for r in rounds
        if r.get(f"{solver}_runtime_ms") is not None
    ]
    best_match = [
        1.0
        if r.get(f"{solver}_gap_vs_hist_best") is not None and r[f"{solver}_gap_vs_hist_best"] <= 0
        else 0.0
        for r in rounds
        if r.get(f"{solver}_gap_vs_hist_best") is not None
    ]
    exceed = [
        1.0
        if r.get(f"{solver}_gap_vs_hist_best") is not None and r[f"{solver}_gap_vs_hist_best"] < 0
        else 0.0
        for r in rounds
        if r.get(f"{solver}_gap_vs_hist_best") is not None
    ]
    top1 = [1.0 if x == 1 else 0.0 for x in ranks]
    top3 = [1.0 if x <= 3 else 0.0 for x in ranks]

    verified = [
        r
        for r in rounds
        if r.get("historical_score_reproduction_status") == "ok"
        and r.get(f"{solver}_reward") is not None
    ]

    summary = {
        "solver": solver,
        "rounds": len(rewards),
        "verified_rounds": len(verified),
        "total_reward": sum(rewards) if rewards else 0.0,
        "mean_reward": _mean(rewards),
        "median_reward": _median(rewards),
        "std_reward": _std(rewards),
        "mean_clique_size": _mean(sizes),
        "mean_gap_vs_hist_best": _mean(gaps),
        "rounds_largest_clique": int(sum(1 for g in gaps if g <= 0)),
        "rounds_rank1_reward": int(sum(top1)),
        "rounds_top3_reward": int(sum(top3)),
        "mean_rank": _mean(ranks),
        "mean_rank_percentile": _mean(percentiles),
        "validity_rate": _mean([1.0 if v else 0.0 for v in valids]),
        "timeout_rate": _mean([1.0 if t else 0.0 for t in timeouts]),
        "mean_runtime_ms": _mean(runtimes),
        "hist_best_match_rate": _mean(best_match),
        "hist_best_exceed_rate": _mean(exceed),
        "ci_mean_reward": bootstrap_ci(rewards, _mean),
        "ci_mean_percentile": bootstrap_ci(percentiles, _mean),
        "ci_top3_rate": bootstrap_ci(top3, _mean),
        "ci_best_match_rate": bootstrap_ci(best_match, _mean),
    }
    return summary


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--round-comparison", type=Path, default=RESULTS / "round_comparison.json")
    p.add_argument("--output", type=Path, default=RESULTS / "miner_ranking_summary.csv")
    args = p.parse_args(argv)

    if not args.round_comparison.exists():
        print(json.dumps({"error": f"missing {args.round_comparison}"}, indent=2))
        return 2

    rounds = json.loads(args.round_comparison.read_text())
    summaries = [summarize_solver(rounds, s) for s in SOLVERS]

    # Flatten for CSV.
    flat_rows = []
    for s in summaries:
        row = {
            k: v
            for k, v in s.items()
            if not isinstance(v, dict)
        }
        for key in ("ci_mean_reward", "ci_mean_percentile", "ci_top3_rate", "ci_best_match_rate"):
            ci = s[key]
            row[f"{key}_point"] = ci["point"]
            row[f"{key}_lo"] = ci["lo"]
            row[f"{key}_hi"] = ci["hi"]
        flat_rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(flat_rows[0].keys()) if flat_rows else [])
        if flat_rows:
            w.writeheader()
            w.writerows(flat_rows)

    best = max(
        summaries,
        key=lambda s: (
            s["mean_rank_percentile"] if s["mean_rank_percentile"] == s["mean_rank_percentile"] else -1,
            s["mean_reward"] if s["mean_reward"] == s["mean_reward"] else -1,
        ),
        default=None,
    )

    prediction = {
        "primary_metric": "mean_counterfactual_round_rank_percentile",
        "best_solver": best["solver"] if best else None,
        "summaries": summaries,
        "caveats": [
            "This is mean counterfactual rank among recorded miners in each historical round.",
            "It is NOT current or future on-chain incentive rank.",
            "Debiased EMA (alpha=0.01), miner selection, and sigmoid/power weight-setting alter long-run weights.",
            "With ~20 rounds, bootstrap CIs are preliminary.",
            "Nonparticipation of historical miners in other rounds is not treated as failure.",
        ],
        "on_chain_rank": {
            "estimated_historical_round_position": best["mean_rank_percentile"] if best else None,
            "exact_on_chain_rank": "unavailable",
            "future_on_chain_rank": "uncertain",
        },
    }
    (RESULTS / "miner_ranking_prediction.json").write_text(json.dumps(prediction, indent=2))
    print(json.dumps({"best_solver": prediction["best_solver"], "csv": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
