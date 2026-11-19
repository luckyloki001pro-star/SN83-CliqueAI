"""Validate historical graphs and reproduce logged SN83 scores."""

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

from clique.history import check_completeness, graph_checks, load_jsonl
from clique.sn83_scoring import CliqueScoreCalculator, GraphView

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"
TOL = 1e-6


def verify_one(rec: Dict[str, Any]) -> Dict[str, Any]:
    comp = check_completeness(rec)
    gcheck = graph_checks(rec) if comp.ok else {}
    out: Dict[str, Any] = {
        "uuid": rec.get("uuid"),
        "timestamp": rec.get("timestamp"),
        "complete": comp.ok,
        "completeness_notes": ";".join(comp.notes),
        "graph_ok": bool(gcheck)
        and gcheck.get("symmetric")
        and gcheck.get("no_self_loops")
        and gcheck.get("index_ok")
        and gcheck.get("codec_match") is not False,
        "codec_match": gcheck.get("codec_match"),
        "n": rec.get("number_of_nodes"),
        "edges": gcheck.get("edges"),
        "density": gcheck.get("density"),
        "miner_count": len(rec.get("miner_uids") or []),
        "reproduction_ok": False,
        "max_abs_err_rel": None,
        "max_abs_err_pr": None,
        "max_abs_err_omega": None,
        "max_abs_err_optimality": None,
        "max_abs_err_diversity": None,
        "max_abs_err_rewards": None,
        "independent_valid_count": None,
        "historical_best_valid_size": None,
        "errors": ";".join(gcheck.get("errors") or []),
    }
    if not comp.ok:
        return out

    graph = GraphView(rec["number_of_nodes"], rec["adjacency_list"])
    calc = CliqueScoreCalculator(graph, float(rec["difficulty"]), rec["miner_ans"])
    scored = calc.score_detailed()

    def max_err(a, b):
        aa = np.asarray(a, dtype=float)
        bb = np.asarray(b, dtype=float)
        if aa.shape != bb.shape:
            return float("inf")
        return float(np.max(np.abs(aa - bb))) if len(aa) else 0.0

    errs = {
        "rel": max_err(scored.rel, rec["miner_rel"]),
        "pr": max_err(scored.pr, rec["miner_pr"]),
        "omega": max_err(scored.omega, rec["miner_omega"]),
        "optimality": max_err(scored.optimality, rec["miner_optimality"]),
        "diversity": max_err(scored.diversity, rec["miner_diversity"]),
        "rewards": max_err(scored.rewards, rec["miner_rewards"]),
    }
    # Docs swap omega/optimality names; detect if logged columns are swapped.
    swap_omega = max_err(scored.omega, rec["miner_optimality"])
    swap_opt = max_err(scored.optimality, rec["miner_omega"])
    used_swap = False
    if errs["omega"] > TOL and errs["optimality"] > TOL:
        if swap_omega <= TOL and swap_opt <= TOL:
            used_swap = True
            errs["omega"] = swap_omega
            errs["optimality"] = swap_opt
            out["errors"] = (out["errors"] + ";" if out["errors"] else "") + (
                "logged miner_omega/miner_optimality appear swapped vs validator.py; "
                "compared using code semantics"
            )

    out.update(
        {
            "max_abs_err_rel": errs["rel"],
            "max_abs_err_pr": errs["pr"],
            "max_abs_err_omega": errs["omega"],
            "max_abs_err_optimality": errs["optimality"],
            "max_abs_err_diversity": errs["diversity"],
            "max_abs_err_rewards": errs["rewards"],
            "reproduction_ok": all(v <= TOL for v in errs.values()),
            "column_swap_detected": used_swap,
            "independent_valid_count": int(np.sum(scored.validity)),
            "historical_best_valid_size": int(np.max(scored.effective_size))
            if len(scored.effective_size)
            else 0,
        }
    )

    # Per-miner independent validity note (do not mutate historical answers).
    miner_rows = []
    for i, ans in enumerate(rec["miner_ans"]):
        miner_rows.append(
            {
                "uuid": rec["uuid"],
                "miner_index": i,
                "uid": rec["miner_uids"][i],
                "hotkey": rec["miner_hotkeys"][i],
                "coldkey": rec["miner_coldkeys"][i],
                "clique_size": len(ans),
                "independent_valid": bool(scored.validity[i]),
                "logged_reward": rec["miner_rewards"][i],
                "recomputed_reward": float(scored.rewards[i]),
            }
        )
    out["_miner_rows"] = miner_rows
    return out


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    args = p.parse_args(argv)

    if not args.history.exists():
        print(
            json.dumps(
                {
                    "error": f"missing history file: {args.history}",
                    "hint": "run fetch_sn83_history or import_history first",
                },
                indent=2,
            )
        )
        return 2

    records = load_jsonl(args.history)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    verifications = [verify_one(r) for r in records]
    miner_rows: List[Dict[str, Any]] = []
    for v in verifications:
        miner_rows.extend(v.pop("_miner_rows", []))

    # historical_miners.csv
    miner_csv = args.output_dir / "historical_miners.csv"
    if miner_rows:
        fields = list(miner_rows[0].keys())
        with miner_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(miner_rows)

    # historical_score_verification.csv
    ver_csv = args.output_dir / "historical_score_verification.csv"
    fields = [k for k in verifications[0].keys()] if verifications else []
    with ver_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in verifications:
            w.writerow(row)

    (args.output_dir / "historical_score_verification.json").write_text(
        json.dumps(verifications, indent=2)
    )

    ok = sum(1 for v in verifications if v.get("reproduction_ok"))
    print(
        json.dumps(
            {
                "challenges": len(verifications),
                "score_reproduction_ok": ok,
                "score_reproduction_failed": len(verifications) - ok,
                "miner_rows": len(miner_rows),
                "outputs": [str(miner_csv), str(ver_csv)],
            },
            indent=2,
        )
    )
    return 0 if ok == len(verifications) and verifications else 1


if __name__ == "__main__":
    raise SystemExit(main())
