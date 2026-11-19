"""Phase-3 ablations on separate synthetic development graphs (not the final-20)."""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.competitive_search import CompetitiveConfig, CompetitiveVariant, solve_competitive
from clique.graph import BitsetGraph

OUT = ROOT / "results" / "phase3_ablation.csv"


def make_graph(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    return BitsetGraph.from_edge_list(n, edges, name=f"dev_{n}_{seed}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=float, default=2.0)
    p.add_argument("--output", type=Path, default=OUT)
    args = p.parse_args()

    graphs = [make_graph(100, 0.4, 1), make_graph(140, 0.5, 2), make_graph(180, 0.55, 3)]
    configs = [
        ("PLS_full", CompetitiveConfig(variant=CompetitiveVariant.PLS_PENALTY)),
        ("PLS_no_penalty_phase", CompetitiveConfig(variant=CompetitiveVariant.PLS_PENALTY, pls_steps_penalty=0)),
        ("BLS_full", CompetitiveConfig(variant=CompetitiveVariant.BLS_ADAPTIVE)),
        ("BLS_fixed_L2", CompetitiveConfig(variant=CompetitiveVariant.BLS_ADAPTIVE, bls_L_min=2, bls_L_max=2)),
        ("IKLS_full", CompetitiveConfig(variant=CompetitiveVariant.IKLS_VARIABLE_DEPTH)),
        ("IKLS_shallow", CompetitiveConfig(variant=CompetitiveVariant.IKLS_VARIABLE_DEPTH, ikls_depth_limit=3)),
        ("PAIR_full", CompetitiveConfig(variant=CompetitiveVariant.PAIR_ANCHOR)),
        ("PAIR_few", CompetitiveConfig(variant=CompetitiveVariant.PAIR_ANCHOR, pair_top_k=8, pair_sample=200)),
    ]
    rows = []
    for g in graphs:
        for name, cfg in configs:
            cfg.timeout_seconds = args.timeout
            cfg.safety_margin_ms = 200
            cfg.seed = 42
            t0 = time.perf_counter()
            res = solve_competitive(g, cfg)
            rows.append(
                {
                    "graph": g.name,
                    "n": g.n,
                    "config": name,
                    "size": res.clique_size,
                    "valid": res.valid,
                    "runtime_ms": (time.perf_counter() - t0) * 1000.0,
                    "plateau_moves": res.stats.plateau_moves,
                    "useful_plateau": res.stats.useful_plateau_moves,
                    "perturbations": res.stats.perturbations,
                    "vd_improvements": res.stats.variable_depth_improvements,
                    "pair_starts": res.stats.pair_starts,
                }
            )
            print(f"[ablation] {g.name} {name} size={res.clique_size}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
