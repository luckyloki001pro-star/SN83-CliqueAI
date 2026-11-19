"""Controlled Phase 4B ablations on synthetic development graphs."""

from __future__ import annotations

import csv
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.graph import BitsetGraph
from clique.revo import RevoConfig, RevoVariant, solve_revo

OUT = ROOT / "results" / "phase4b_ablation_dev.csv"


def er(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    return BitsetGraph.from_edge_list(n, edges, name=f"er_{n}_{seed}")


def planted(n: int, k: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    for i in range(k):
        for j in range(i + 1, k):
            edges.append((i, j))
    return BitsetGraph.from_edge_list(n, edges, name=f"planted_{n}_{k}")


def main() -> int:
    graphs = [er(60, 0.35, 1), er(80, 0.4, 2), planted(70, 12, 0.12, 3)]
    configs = [
        ("B0_N10", RevoConfig(variant=RevoVariant.REVO_NO_MODEL, population_size=10)),
        ("B1_N10", RevoConfig(variant=RevoVariant.REVO_POPULATION, population_size=10)),
        ("B1_N4", RevoConfig(variant=RevoVariant.REVO_POPULATION, population_size=4)),
        ("B1_delta0", RevoConfig(variant=RevoVariant.REVO_POPULATION, model_delta=0)),
        ("B1_lr1", RevoConfig(variant=RevoVariant.REVO_POPULATION, learning_rate=1.0)),
        ("B1_tabu01", RevoConfig(variant=RevoVariant.REVO_POPULATION, tabu_ratio=0.10)),
        ("B2", RevoConfig(variant=RevoVariant.REVO_DIVERSE, population_size=10)),
    ]
    rows = []
    for g in graphs:
        for name, cfg in configs:
            cfg.timeout_seconds = 1.5
            cfg.safety_margin_ms = 100.0
            cfg.seed = 42
            cfg.restart_factor = 40  # denser restarts on short synthetic budgets
            t0 = time.perf_counter()
            r = solve_revo(g, cfg)
            rows.append(
                {
                    "graph": g.name,
                    "n": g.n,
                    "config": name,
                    "size": r.clique_size,
                    "valid": r.valid,
                    "runtime_ms": (time.perf_counter() - t0) * 1000.0,
                    "restarts": r.stats.restarts,
                    "model_updates": r.stats.model_updates,
                    "entropy": r.stats.extras.get("final_model_entropy"),
                    "jaccard": r.stats.extras.get("final_jaccard"),
                }
            )
            print(f"[abl] {g.name} {name} size={r.clique_size}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
