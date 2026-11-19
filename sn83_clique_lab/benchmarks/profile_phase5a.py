"""Separate profiling run for ONE (not used during primary timed benchmark)."""

from __future__ import annotations

import argparse
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
from clique.one_repair import OneConfig, OneVariant, solve_one

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"
HARD = ("577e9988", "1db8cfb3", "4c69bfb1", "9bd55ea0")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output", type=Path, default=RESULTS / "phase5a_profiling.json")
    p.add_argument("--uuid-prefix", type=str, default="577e9988")
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--variant", type=str, default="one_conflict_repair")
    args = p.parse_args()

    records = load_jsonl(args.history)
    rec = next((r for r in records if r["uuid"].startswith(args.uuid_prefix)), records[0])
    graph = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
    variant = OneVariant(args.variant)
    cfg = OneConfig(
        variant=variant,
        timeout_seconds=args.timeout,
        safety_margin_ms=200.0,
        seed=42,
        revo_fraction=0.65,
    )

    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    res = solve_one(graph, cfg)
    wall = time.perf_counter() - t0
    pr.disable()

    buf = io.StringIO()
    stats = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    stats.print_stats(40)
    text = buf.getvalue()

    # Extract top function names heuristically
    hotspots = []
    for line in text.splitlines():
        line = line.strip()
        if "(" in line and "/" in line or ".py:" in line:
            hotspots.append(line)
        if len(hotspots) >= 25:
            break

    out = {
        "uuid": rec["uuid"],
        "variant": args.variant,
        "timeout": args.timeout,
        "wall_seconds": wall,
        "clique_size": res.clique_size,
        "neighborhoods_attempted": res.stats.neighborhoods_attempted,
        "search_nodes_total": res.stats.search_nodes_total,
        "revo_ms": res.stats.revo_ms,
        "repair_ms": res.stats.repair_ms,
        "profile_top": hotspots[:25],
        "profile_text_tail": "\n".join(text.splitlines()[-60:]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in out if k != "profile_text_tail"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
