"""Small ablation study for anytime search components (separate from final-20 tuning)."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.anytime_search import AnytimeConfig, AnytimeVariant, solve_anytime
from clique.graph import BitsetGraph

OUT = ROOT / "results" / "anytime_parameter_ablation.csv"


def make_dev_graph(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    return BitsetGraph.from_edge_list(n, edges, name=f"dev_{n}_{seed}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--output", type=Path, default=OUT)
    args = p.parse_args()

    graphs = [
        make_dev_graph(80, 0.35, 1),
        make_dev_graph(100, 0.45, 2),
        make_dev_graph(120, 0.55, 3),
    ]
    configs = [
        ("D_rcl", AnytimeConfig(variant=AnytimeVariant.MULTISTART_GREEDY, policy="rcl")),
        ("D_max_residual", AnytimeConfig(variant=AnytimeVariant.MULTISTART_GREEDY, policy="max_residual")),
        ("D_softmax", AnytimeConfig(variant=AnytimeVariant.MULTISTART_GREEDY, policy="softmax")),
        ("E_1for2_only", AnytimeConfig(variant=AnytimeVariant.SWAP_LOCAL_SEARCH, enable_2for3=False)),
        ("E_1for2_2for3", AnytimeConfig(variant=AnytimeVariant.SWAP_LOCAL_SEARCH, enable_2for3=True)),
        ("E_best_improve", AnytimeConfig(variant=AnytimeVariant.SWAP_LOCAL_SEARCH, first_improvement=False)),
        ("F_triangle", AnytimeConfig(variant=AnytimeVariant.TRIANGLE_GUIDED, alpha=0.65, beta=0.35)),
        ("F_degree_only", AnytimeConfig(variant=AnytimeVariant.TRIANGLE_GUIDED, alpha=1.0, beta=0.0, noise=0.0)),
        ("F_triangle_only", AnytimeConfig(variant=AnytimeVariant.TRIANGLE_GUIDED, alpha=0.0, beta=1.0, noise=0.0)),
    ]

    rows = []
    for g in graphs:
        for name, cfg in configs:
            cfg.timeout_seconds = args.timeout
            cfg.safety_margin_ms = 200
            cfg.seed = 42
            t0 = time.perf_counter()
            res = solve_anytime(g, cfg)
            ms = (time.perf_counter() - t0) * 1000.0
            rows.append(
                {
                    "graph": g.name,
                    "n": g.n,
                    "config": name,
                    "size": res.clique_size,
                    "valid": res.valid,
                    "maximal": res.maximal,
                    "runtime_ms": ms,
                    "constructions": res.stats.constructions,
                    "swap_1for2_success": res.stats.swap_1for2_success,
                    "swap_2for3_success": res.stats.swap_2for3_success,
                    "triangle_prep_ms": res.stats.triangle_prep_time_ms,
                }
            )
            print(f"[ablation] {g.name} {name} size={res.clique_size} valid={res.valid}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
