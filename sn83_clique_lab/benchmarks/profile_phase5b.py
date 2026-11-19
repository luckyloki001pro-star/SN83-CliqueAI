"""Separate cProfile run for NuMVC (not used in primary timed benchmark)."""

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
from clique.numvc import NuMVCConfig, NuMVCVariant, solve_numvc

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output", type=Path, default=RESULTS / "phase5b_profiling.json")
    p.add_argument("--uuid-prefix", type=str, default="577e9988")
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--variant", type=str, default="numvc_complement")
    args = p.parse_args()

    records = load_jsonl(args.history)
    rec = next((r for r in records if r["uuid"].startswith(args.uuid_prefix)), records[0])
    graph = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
    cfg = NuMVCConfig(
        variant=NuMVCVariant(args.variant),
        timeout_seconds=args.timeout,
        safety_margin_ms=200.0,
        seed=42,
    )
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    res = solve_numvc(graph, cfg)
    wall = time.perf_counter() - t0
    pr.disable()
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(30)
    text = buf.getvalue()
    hotspots = [ln.strip() for ln in text.splitlines() if ".py:" in ln][:20]
    out = {
        "uuid": rec["uuid"],
        "variant": args.variant,
        "timeout": args.timeout,
        "wall_seconds": wall,
        "clique_size": res.clique_size,
        "best_cover_size": res.best_cover_size,
        "search_steps": res.stats.search_steps,
        "steps_per_second": res.stats.steps_per_second,
        "complement_ms": res.stats.complement_ms,
        "complement_edges": res.stats.complement_edge_count,
        "profile_top": hotspots,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
