"""cProfile + fine timers for Phase-3 solvers on one mid-size and one hard graph."""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.graph import BitsetGraph
from clique.history import load_jsonl
from clique.solver import solve_graph

OUT = ROOT / "results" / "phase3_profiling.json"
HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
SOLVERS = (
    "bls_adaptive",
    "pls_penalty",
    "ikls_variable_depth",
    "pair_anchor",
    "adaptive_portfolio",
)


def profile_one(graph: BitsetGraph, solver: str, timeout: float) -> dict:
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    res = solve_graph(graph, timeout_seconds=timeout, variant=solver, seed=42, safety_margin_ms=500.0)
    wall = (time.perf_counter() - t0) * 1000.0
    pr.disable()
    buf = io.StringIO()
    stats = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    stats.print_stats(25)
    top = []
    for func, (cc, nc, tt, ct, callers) in list(stats.stats.items())[:40]:
        top.append(
            {
                "func": f"{func[0]}:{func[1]}:{func[2]}",
                "cumtime": ct,
                "tottime": tt,
                "ncalls": nc,
            }
        )
    top.sort(key=lambda x: -x["cumtime"])
    return {
        "solver": solver,
        "n": graph.n,
        "uuid": graph.name,
        "timeout": timeout,
        "size": res.clique_size,
        "wall_ms": wall,
        "runtime_ms": res.runtime_ms,
        "extras": {
            k: res.extras.get(k)
            for k in (
                "plateau_moves",
                "useful_plateau_moves",
                "perturbations",
                "avg_perturbation_strength",
                "variable_depth_improvements",
                "pair_starts",
                "pair_prep_time_ms",
                "local_search_time_ms",
                "time_to_first_ms",
                "time_to_best_ms",
            )
        },
        "cprofile_top15": top[:15],
    }


def main() -> int:
    records = load_jsonl(HISTORY)
    by_uuid = {r["uuid"]: r for r in records}
    # mid ~300 and hard ~900
    mid = next(r for r in records if r["number_of_nodes"] < 350)
    hard = next(r for r in records if r["uuid"].startswith("577e9988"))
    selected = [mid, hard]
    out = {"graphs": [], "note": "Profiling uses shortened timeout on hard graph (8s) to bound cost."}
    for rec in selected:
        g = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
        # keep mid at full limit capped 8s; hard use 8s
        timeout = min(float(rec["time_limit"]), 8.0)
        entry = {"uuid": rec["uuid"][:8], "n": rec["number_of_nodes"], "timeout_used": timeout, "solvers": []}
        for solver in SOLVERS:
            print(f"[profile] {rec['uuid'][:8]} {solver}", flush=True)
            entry["solvers"].append(profile_one(g, solver, timeout))
        out["graphs"].append(entry)
    OUT.write_text(json.dumps(out, indent=2))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
