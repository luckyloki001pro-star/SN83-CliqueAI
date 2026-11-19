"""Anytime discovery curves for revo_no_model vs numvc_complement (Phase 5C)."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.graph import BitsetGraph
from clique.history import load_jsonl
from clique.numvc import NuMVCConfig, NuMVCVariant, solve_numvc
from clique.revo import RevoConfig, RevoVariant, solve_revo

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"

HARD = ("577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0")
# Fixed graph-only controls: two small-n (easy-ish) + two mid-n
CONTROL = ("fc92cd37", "53839380", "1987b6bb", "22bc813e")

CHECKPOINTS = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 30.0]


def make_seeds(master: int, n: int) -> List[int]:
    rng = random.Random(master)
    return [rng.randrange(1, 2**31 - 1) for _ in range(n)]


def best_at(history: List[Dict[str, float]], t_ms: float) -> int:
    best = 0
    for row in history:
        if float(row["time_ms"]) <= t_ms + 1e-9:
            best = max(best, int(row["size"]))
        else:
            break
    # history may not be sorted if equal times — scan all
    for row in history:
        if float(row["time_ms"]) <= t_ms + 1e-9:
            best = max(best, int(row["size"]))
    return best


def run_solver(graph: BitsetGraph, solver: str, timeout: float, seed: int) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []

    def on_inc(name, clique, size, elapsed_ms, sd):
        events.append(
            {
                "solver": name,
                "size": size,
                "elapsed_ms": elapsed_ms,
                "seed": sd,
            }
        )

    t0 = time.perf_counter_ns()
    if solver == "revo_no_model":
        cfg = RevoConfig(
            variant=RevoVariant.REVO_NO_MODEL,
            timeout_seconds=timeout,
            safety_margin_ms=500.0,
            seed=seed,
            on_incumbent=on_inc,
        )
        res = solve_revo(graph, cfg)
        hist = res.stats.improvement_history
        init_ms = res.stats.init_ms
        steps = res.stats.total_moves
    else:
        cfg = NuMVCConfig(
            variant=NuMVCVariant.NUMVC_COMPLEMENT,
            timeout_seconds=timeout,
            safety_margin_ms=500.0,
            seed=seed,
            on_incumbent=on_inc,
        )
        res = solve_numvc(graph, cfg)
        hist = res.stats.improvement_history
        init_ms = res.stats.complement_ms + res.stats.init_cover_ms
        steps = res.stats.search_steps
    total_ms = (time.perf_counter_ns() - t0) / 1e6
    cps = {}
    for sec in CHECKPOINTS:
        if sec > timeout + 1e-9:
            continue
        cps[f"{sec:g}s"] = best_at(hist, sec * 1000.0)
    return {
        "solver": solver,
        "seed": seed,
        "best_size": res.clique_size,
        "valid": res.valid,
        "maximal": res.maximal,
        "time_to_first_ms": res.stats.time_to_first_ms,
        "time_to_best_ms": res.stats.time_to_best_ms,
        "init_ms": init_ms,
        "total_ms": total_ms,
        "search_steps": steps,
        "improvements": len(hist),
        "checkpoints": cps,
        "events": events,
        "improvement_history": hist,
        "response_deadline_violation": getattr(res, "response_deadline_violation", False),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=RESULTS)
    p.add_argument("--master-seed", type=int, default=20261119)
    p.add_argument("--n-seeds", type=int, default=10)
    p.add_argument("--hard-only", action="store_true")
    p.add_argument("--graphs", nargs="*", default=None)
    args = p.parse_args()

    records = load_jsonl(args.history)
    by_prefix = {r["uuid"][:8]: r for r in records}
    prefixes = list(HARD) + ([] if args.hard_only else list(CONTROL))
    if args.graphs:
        prefixes = list(args.graphs)
    seeds = make_seeds(args.master_seed, args.n_seeds)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    events_path = args.output_dir / "phase5c_discovery_events.jsonl"
    curve_rows: List[Dict[str, Any]] = []
    with events_path.open("w") as ef:
        for pref in prefixes:
            rec = by_prefix[pref]
            graph = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
            timeout = float(rec["time_limit"])
            hist_best = max((len(a) for a in rec["miner_ans"]), default=0)
            for solver in ("revo_no_model", "numvc_complement"):
                for seed in seeds:
                    row = run_solver(graph, solver, timeout, seed)
                    row.update(
                        {
                            "uuid": rec["uuid"],
                            "uuid8": pref,
                            "n": rec["number_of_nodes"],
                            "time_limit": timeout,
                            "historical_best": hist_best,
                            "hard": pref in HARD,
                        }
                    )
                    for ev in row["events"]:
                        ef.write(
                            json.dumps(
                                {
                                    **ev,
                                    "uuid8": pref,
                                    "time_limit": timeout,
                                }
                            )
                            + "\n"
                        )
                    # flatten checkpoints
                    flat = {k: v for k, v in row.items() if k not in ("events", "improvement_history", "checkpoints")}
                    flat.update(row["checkpoints"])
                    curve_rows.append(flat)
                    print(
                        f"[disc] {pref} {solver} seed={seed} size={row['best_size']} "
                        f"ttb={row['time_to_best_ms']:.0f}ms",
                        flush=True,
                    )

    # write csv
    if curve_rows:
        keys = sorted({k for r in curve_rows for k in r})
        with (args.output_dir / "phase5c_discovery_curves.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(curve_rows)
    meta = {"seeds": seeds, "master_seed": args.master_seed, "n_seeds": args.n_seeds, "graphs": prefixes}
    (args.output_dir / "phase5c_discovery_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
