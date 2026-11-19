"""Synthetic development graphs for Phase 4A (planted / ER / decoy)."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.graph import BitsetGraph
from clique.solver import solve_graph

OUT = ROOT / "results" / "phase4a_synthetic.json"


def planted(n: int, k: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    for i in range(k):
        for j in range(i + 1, k):
            edges.append((i, j))
    return BitsetGraph.from_edge_list(n, edges, name=f"planted_n{n}_k{k}")


def er(n: int, p: float, seed: int) -> BitsetGraph:
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    return BitsetGraph.from_edge_list(n, edges, name=f"er_n{n}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=float, default=2.0)
    args = p.parse_args()
    graphs = [
        ("planted_k12", planted(80, 12, 0.12, 1), 12),
        ("planted_k10", planted(100, 10, 0.15, 2), 10),
        ("er_neg", er(80, 0.2, 3), None),
        ("dense_er", er(60, 0.55, 4), None),
    ]
    solvers = [
        "global_spectral",
        "anchored_spectral",
        "anchored_spectral_plus_ikls",
        "pair_anchor",
        "adaptive_portfolio",
    ]
    rows = []
    for name, g, planted_k in graphs:
        for sol in solvers:
            t0 = time.perf_counter()
            r = solve_graph(g, timeout_seconds=args.timeout, variant=sol, seed=42, safety_margin_ms=200.0)
            planted_frac = None
            if planted_k:
                top = set(range(planted_k))
                planted_frac = len(top & set(r.clique)) / planted_k
            rows.append(
                {
                    "graph": name,
                    "n": g.n,
                    "planted_k": planted_k,
                    "solver": sol,
                    "size": r.clique_size,
                    "valid": r.valid,
                    "planted_fraction_in_clique": planted_frac,
                    "runtime_ms": (time.perf_counter() - t0) * 1000.0,
                    "spectral_ms": r.extras.get("spectral_ms"),
                }
            )
            print(f"[syn] {name} {sol} size={r.clique_size} planted_frac={planted_frac}", flush=True)
    OUT.write_text(json.dumps(rows, indent=2))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
