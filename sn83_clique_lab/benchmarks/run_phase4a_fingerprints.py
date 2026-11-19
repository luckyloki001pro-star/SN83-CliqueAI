"""Phase 4A — fingerprint all historical SN83 graphs (offline diagnostics)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.graph import BitsetGraph
from clique.graph_fingerprint import fingerprint_graph
from clique.history import load_jsonl

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
PORTFOLIO = ROOT / "results" / "phase3_adaptive_portfolio_responses.jsonl"
OUT_CSV = ROOT / "results" / "phase4a_graph_fingerprints.csv"
OUT_JSON = ROOT / "results" / "phase4a_graph_fingerprints.json"


def load_portfolio_sizes(path: Path) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["uuid"]] = int(row["clique_size"])
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", type=Path, default=OUT_CSV)
    args = p.parse_args()

    portfolio = load_portfolio_sizes(PORTFOLIO)
    records = load_jsonl(args.history)
    rows: list[Dict[str, Any]] = []
    for rec in records:
        g = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
        fp = fingerprint_graph(g, seed=args.seed)
        hist_best = max((len(a) for a in rec["miner_ans"]), default=0)
        row = fp.to_row()
        # report-only fields — never used by solvers
        row["uuid"] = rec["uuid"]
        row["uuid8"] = rec["uuid"][:8]
        row["time_limit"] = rec["time_limit"]
        row["difficulty"] = rec["difficulty"]
        row["observed_historical_best_size"] = hist_best
        row["observed_portfolio_size"] = portfolio.get(rec["uuid"])
        row["gap_portfolio"] = (
            hist_best - portfolio[rec["uuid"]] if rec["uuid"] in portfolio else None
        )
        row["hist_vs_er_threshold"] = hist_best - fp.er_expected_count_threshold
        rows.append(row)
        print(
            f"[fp] {rec['uuid'][:8]} n={fp.n} dens={fp.density:.4f} "
            f"deg_std={fp.degree_std:.2f} tri={fp.sampled_triangle_density:.4f} "
            f"ER_thr={fp.er_expected_count_threshold} hist={hist_best} "
            f"port={row['observed_portfolio_size']} ms={fp.fingerprint_ms:.1f}",
            flush=True,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for r in rows for k in r})
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    OUT_JSON.write_text(json.dumps(rows, indent=2))
    print("wrote", args.output)
    print("wrote", OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
