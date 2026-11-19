"""Separate profiling run for R-EVO (not used in primary timed benchmarks)."""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.graph import BitsetGraph
from clique.history import load_jsonl
from clique.revo import RevoConfig, RevoVariant, solve_revo

OUT = ROOT / "results" / "phase4b_profiling.json"


def main() -> int:
    records = load_jsonl(ROOT / "datasets" / "sn83_history" / "latest20.jsonl")
    mid = next(r for r in records if r["number_of_nodes"] < 350)
    hard = next(r for r in records if r["uuid"].startswith("1987b6bb"))
    out = {"note": "Separate cProfile run; not primary benchmark timings.", "graphs": []}
    for rec in (mid, hard):
        g = BitsetGraph.from_adjacency_list(rec["adjacency_list"], name=rec["uuid"])
        timeout = min(float(rec["time_limit"]), 5.0)
        entry = {"uuid": rec["uuid"][:8], "n": g.n, "timeout": timeout, "solvers": []}
        for variant in (RevoVariant.REVO_NO_MODEL, RevoVariant.REVO_POPULATION):
            cfg = RevoConfig(
                variant=variant,
                timeout_seconds=timeout,
                safety_margin_ms=500.0,
                seed=42,
            )
            pr = cProfile.Profile()
            pr.enable()
            res = solve_revo(g, cfg)
            pr.disable()
            buf = io.StringIO()
            st = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
            st.print_stats(15)
            top = []
            for func, (cc, nc, tt, ct, callers) in list(st.stats.items()):
                top.append({"func": f"{func[0]}:{func[1]}:{func[2]}", "cumtime": ct, "tottime": tt, "ncalls": nc})
            top.sort(key=lambda x: -x["cumtime"])
            entry["solvers"].append(
                {
                    "variant": variant.value,
                    "size": res.clique_size,
                    "stats": {
                        "local_search_ms": res.stats.local_search_ms,
                        "model_update_ms": res.stats.model_update_ms,
                        "restart_ms": res.stats.restart_ms,
                        "elite_ms": res.stats.elite_ms,
                        "sweeps": res.stats.population_sweeps,
                        "restarts": res.stats.restarts,
                    },
                    "cprofile_top10": top[:10],
                }
            )
        out["graphs"].append(entry)
    OUT.write_text(json.dumps(out, indent=2))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
