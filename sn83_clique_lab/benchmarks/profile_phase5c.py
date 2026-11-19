"""Profile portfolio scheduling overhead (separate from timed benchmark)."""

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
from clique.adaptive_dual_portfolio import AdaptiveConfig, AdaptivePolicy, run_adaptive_portfolio

HISTORY = ROOT / "datasets" / "sn83_history" / "latest20.jsonl"
RESULTS = ROOT / "results"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output", type=Path, default=RESULTS / "phase5c_profiling.json")
    p.add_argument("--uuid-prefix", default="577e9988")
    p.add_argument("--timeout", type=float, default=3.0)
    args = p.parse_args()
    rec = next(r for r in load_jsonl(args.history) if r["uuid"].startswith(args.uuid_prefix))
    g = BitsetGraph.from_adjacency_list(rec["adjacency_list"])
    cfg = AdaptiveConfig(
        policy=AdaptivePolicy.EARLY_PROBE,
        timeout_seconds=args.timeout,
        safety_margin_ms=200,
        seed=42,
        early_probe_seconds=0.5,
    )
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    res = run_adaptive_portfolio(g, cfg)
    wall = time.perf_counter() - t0
    pr.disable()
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(25)
    hot = [ln.strip() for ln in buf.getvalue().splitlines() if ".py:" in ln][:15]
    out = {
        "uuid": rec["uuid"],
        "wall_seconds": wall,
        "clique_size": res.clique_size,
        "variant": res.variant,
        "revo_active_ms": res.extras.get("revo_active_ms"),
        "numvc_active_ms": res.extras.get("numvc_active_ms"),
        "switches": res.stats.switches,
        "profile_top": hot,
    }
    args.output.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
