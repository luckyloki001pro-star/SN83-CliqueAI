"""Generate reports/sn83_latest20_benchmark.md from local artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "results"
REPORTS = ROOT / "reports"
HISTORY_DIR = ROOT / "datasets" / "sn83_history"
SOLVERS = ("baseline", "ulm", "selective_ulm")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=REPORTS / "sn83_latest20_benchmark.md")
    args = p.parse_args(argv)

    manifest = {}
    man_path = HISTORY_DIR / "manifest.json"
    if man_path.exists():
        manifest = json.loads(man_path.read_text())

    access = REPORTS / "data_access_status.md"
    access_text = access.read_text() if access.exists() else "_No access status file._"

    rounds = []
    rc = RESULTS / "round_comparison.json"
    if rc.exists():
        rounds = json.loads(rc.read_text())

    prediction = {}
    pred_path = RESULTS / "miner_ranking_prediction.json"
    if pred_path.exists():
        prediction = json.loads(pred_path.read_text())

    verification = []
    ver_path = RESULTS / "historical_score_verification.json"
    if ver_path.exists():
        verification = json.loads(ver_path.read_text())

    n_hist = len(rounds) or len(manifest.get("selected_uuids") or [])
    access_status = manifest.get("access_status", "unknown")

    lines: list[str] = []
    lines.append("# SN83 Latest-20 Historical Benchmark Report")
    lines.append("")
    lines.append(f"Generated UTC: `{datetime.now(timezone.utc).isoformat()}`")
    lines.append("")
    lines.append("## A. Historical Data Provenance")
    lines.append("")
    lines.append(f"- Source project: `toptensor-ai/CliqueAI`")
    lines.append(f"- Access status: **{access_status}**")
    lines.append(f"- Manifest retrieval timestamp: `{manifest.get('retrieval_timestamp_utc', 'n/a')}`")
    lines.append(f"- Real complete challenges available: **{n_hist}**")
    lines.append(f"- Requested: 20")
    if manifest.get("selected_uuids"):
        lines.append("- Selected UUIDs:")
        for u in manifest["selected_uuids"]:
            lines.append(f"  - `{u}`")
    else:
        lines.append("- Selected UUIDs: **none** (historical data not retrieved)")
    lines.append(f"- Timestamp range: `{manifest.get('timestamp_range')}`")
    lines.append("")
    lines.append("See also `reports/data_access_status.md`.")
    lines.append("")
    lines.append("### Access status excerpt")
    lines.append("")
    lines.append("```")
    lines.append(access_text[:2000])
    lines.append("```")
    lines.append("")

    lines.append("## B. Historical Miner Performance")
    lines.append("")
    if not rounds:
        lines.append(
            "No historical rounds available. Miner performance tables are omitted "
            "rather than fabricated."
        )
    else:
        lines.append(
            "| UUID | n | density | difficulty | t_limit | miners | hist best size | score repro |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
        for r in rounds:
            lines.append(
                f"| `{r['uuid'][:8]}…` | {r['vertices']} | {r.get('density', 0):.3f} | "
                f"{r['difficulty']} | {r['time_limit']} | {r['historical_miner_count']} | "
                f"{r['historical_best_clique_size']} | {r['historical_score_reproduction_status']} |"
            )
        ok = sum(1 for v in verification if v.get("reproduction_ok"))
        lines.append("")
        lines.append(
            f"Score reproduction: {ok}/{len(verification)} rounds within tolerance 1e-6."
        )
    lines.append("")

    lines.append("## C. My Solver Performance")
    lines.append("")
    if not rounds:
        lines.append(
            "Solvers were not run on historical graphs because no real latest-20 "
            "dataset is present. Existing Python solvers in `clique/` "
            "(`baseline`, `ulm`, `selective_ulm`) remain available."
        )
    else:
        lines.append(
            "| Solver | Mean size | Mean runtime ms | Validity rate | Timeout rate |"
        )
        lines.append("|---|---:|---:|---:|---:|")
        for s in prediction.get("summaries", []):
            lines.append(
                f"| {s['solver']} | {s['mean_clique_size']:.3f} | "
                f"{s['mean_runtime_ms']:.1f} | {s['validity_rate']:.3f} | "
                f"{s['timeout_rate']:.3f} |"
            )
    lines.append("")

    lines.append("## D. Recalculated Rewards")
    lines.append("")
    lines.append(
        "Counterfactual rewards are computed by appending the local solver answer "
        "to the historical response list and rescoring the **entire** pool with "
        "`CliqueScoreCalculator`. These are not comparable to unchanged logged rewards."
    )
    lines.append("")
    if rounds:
        lines.append(
            "| UUID | baseline reward | ulm reward | selective_ulm reward |"
        )
        lines.append("|---|---:|---:|---:|")
        for r in rounds:
            lines.append(
                f"| `{r['uuid'][:8]}…` | {r.get('baseline_reward')} | "
                f"{r.get('ulm_reward')} | {r.get('selective_ulm_reward')} |"
            )
    else:
        lines.append("_No counterfactual rewards — no historical rounds._")
    lines.append("")

    lines.append("## E. Round-by-Round Ranking")
    lines.append("")
    if rounds:
        lines.append(
            "| UUID | hist best | base size/rank | ulm size/rank | sel size/rank |"
        )
        lines.append("|---|---:|---|---|---|")
        for r in rounds:
            lines.append(
                f"| `{r['uuid'][:8]}…` | {r['historical_best_clique_size']} | "
                f"{r.get('my_baseline_size')}/{r.get('baseline_rank')} | "
                f"{r.get('my_ulm_size')}/{r.get('ulm_rank')} | "
                f"{r.get('my_selective_ulm_size')}/{r.get('selective_ulm_rank')} |"
            )
    else:
        lines.append("_No rankings — no historical rounds._")
    lines.append("")

    lines.append("## F. Summary Ranking Prediction")
    lines.append("")
    if prediction.get("best_solver"):
        best = next(
            s for s in prediction["summaries"] if s["solver"] == prediction["best_solver"]
        )
        lines.append(f"- Best measured solver: **{prediction['best_solver']}**")
        lines.append(
            f"- Mean counterfactual rank percentile: "
            f"**{best['mean_rank_percentile']:.2f}** "
            f"(bootstrap 95% CI "
            f"{best['ci_mean_percentile']['lo']:.2f}–{best['ci_mean_percentile']['hi']:.2f})"
        )
        lines.append(
            f"- Top-1 / Top-3 rates: {best['rounds_rank1_reward']}/{best['rounds']} , "
            f"{best['rounds_top3_reward']}/{best['rounds']}"
        )
        lines.append(
            f"- Historical-best match / exceed rates: "
            f"{best['hist_best_match_rate']:.3f} / {best['hist_best_exceed_rate']:.3f}"
        )
    else:
        lines.append(
            "- Estimated historical-round position: **unavailable** (no retrieved challenges)"
        )
    lines.append("- Exact on-chain rank: **unavailable**")
    lines.append("- Future on-chain rank: **uncertain**")
    lines.append("")
    lines.append(
        "On-chain weights use debiased EMA (α≈0.01), selection filtering, "
        "min-max normalization, sigmoid, and power scaling; 20 rounds cannot recover UID rank."
    )
    lines.append("")

    lines.append("## G. Recommendation")
    lines.append("")
    if prediction.get("best_solver"):
        lines.append(
            f"Recommend **{prediction['best_solver']}** based on counterfactual "
            "mean rank percentile / reward on the retrieved historical set."
        )
    else:
        lines.append(
            "From the prior local synthetic/official-sample ULM lab "
            "(`reports/benchmark_report.md`), **baseline** was preferred under "
            "SN83-like deadlines because ULM did not improve clique size. "
            "That recommendation stands until real latest-20 historical data is imported "
            "and this pipeline is re-run."
        )
    lines.append("")

    lines.append("## H. Limitations")
    lines.append("")
    lines.append("- Historical latest-20 retrieval blocked: no W&B credentials; proxy 403 to api.wandb.ai.")
    lines.append("- No fabricated historical challenges were inserted.")
    lines.append("- Offline scoring harness is ready and uses official calculator semantics.")
    lines.append("- Docs/`wandb_logging.md` omega naming disagrees with `validator.py` logging; verification detects swaps.")
    lines.append("- Miner selection bias: only sampled miners appear in each round.")
    lines.append("- EMA / weight-setting prevent equating round ranks with live incentive rank.")
    lines.append("")
    lines.append("## Reproduction")
    lines.append("")
    lines.append("```bash")
    lines.append("cd sn83_clique_lab")
    lines.append("export PYTHONPATH=.:.deps")
    lines.append("python -m benchmarks.fetch_sn83_history --limit 20")
    lines.append("python -m benchmarks.import_history --file exported_wandb_data.jsonl")
    lines.append("python -m benchmarks.verify_history")
    lines.append("python -m benchmarks.run_historical --solver all")
    lines.append("python -m benchmarks.recalculate_scores")
    lines.append("python -m benchmarks.predict_rank")
    lines.append("python -m benchmarks.generate_report")
    lines.append("```")
    lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines))
    print(json.dumps({"report": str(args.output), "rounds": n_hist}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
