"""Reproducible local benchmark runner."""

from __future__ import annotations

import csv
import json
import platform
import sys
import time
from itertools import cycle
from pathlib import Path
from typing import Any, Dict, List, Sequence

from clique.datasets import (
    generate_synthetic_suite,
    import_official_samples,
    iter_quick_benchmark_graphs,
    load_graph_record,
    OFFICIAL,
    SYNTHETIC,
)
from clique.graph import BitsetGraph
from clique.networkx_ref import solve_networkx_ref
from clique.solver import shared_initial_incumbent, solve_graph

ROOT = Path(__file__).resolve().parent.parent


def _env_info() -> Dict[str, Any]:
    cpu = platform.processor() or ""
    try:
        cpu_model = Path("/proc/cpuinfo").read_text()
        for line in cpu_model.splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem = ""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                mem = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": cpu,
        "memory": mem,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _timeouts_for(n: int, mode: str, cfg: dict) -> List[float]:
    if mode == "quick":
        return list(cfg.get("timeouts", [6.0, 10.0]))
    by = cfg.get("timeouts_by_n", {})
    if n >= 890:
        return list(by.get("n_ge_890", [7.5, 10.0, 15.0, 30.0]))
    return list(by.get("default", [6.0, 7.5, 10.0, 15.0, 30.0]))


def _run_one(
    graph: BitsetGraph,
    method: str,
    timeout: float,
    seed: int,
    safety_margin_ms: float,
) -> Dict[str, Any]:
    incumbent = shared_initial_incumbent(graph, seed=seed)
    t0 = time.perf_counter()
    if method in ("networkx", "networkx_approx", "r"):
        result = solve_networkx_ref(graph, timeout_seconds=timeout)
    else:
        result = solve_graph(
            graph,
            timeout_seconds=timeout,
            variant=method,
            seed=seed,
            shared_incumbent=incumbent,
            safety_margin_ms=safety_margin_ms,
        )
    e2e_ms = (time.perf_counter() - t0) * 1000.0
    row = result.to_dict()
    row.update(
        {
            "graph_id": graph.name,
            "graph_hash": graph.content_hash() if graph.n <= 1200 else "",
            "n": graph.n,
            "edges": graph.edge_count(),
            "density": graph.density(),
            "dataset": graph.metadata.get("dataset", "unknown"),
            "seed": seed,
            "time_limit": timeout,
            "e2e_ms": e2e_ms,
            "method": method,
            "incumbent_size": len(incumbent),
        }
    )
    return row


def _collect_quick_graphs(max_graphs: int) -> List[BitsetGraph]:
    graphs = list(iter_quick_benchmark_graphs())
    # Prefer smaller first for smoke, but keep official + a few large.
    graphs.sort(key=lambda g: (0 if g.metadata.get("dataset") == "official" else 1, g.n))
    return graphs[:max_graphs]


def _collect_full_graphs(cfg: dict) -> List[BitsetGraph]:
    graphs: List[BitsetGraph] = []
    if cfg.get("include_official", True):
        import_official_samples()
        for path in sorted(OFFICIAL.glob("*.adj.json")):
            graphs.append(load_graph_record(path))
    for split in cfg.get("splits", ["eval"]):
        generate_synthetic_suite(split)
        for path in sorted((SYNTHETIC / split).glob("*.json")):
            if path.name == "manifest.json":
                continue
            graphs.append(load_graph_record(path))
    return graphs


def run_benchmark(mode: str = "quick", output_dir: Path | None = None) -> List[Dict[str, Any]]:
    output_dir = Path(output_dir or ROOT / "reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = ROOT / "benchmarks" / "configs" / f"{mode}.json"
    cfg = json.loads(cfg_path.read_text())

    if mode == "quick":
        graphs = _collect_quick_graphs(cfg.get("max_graphs", 12))
    else:
        graphs = _collect_full_graphs(cfg)

    methods: Sequence[str] = list(cfg.get("methods", ["baseline", "ulm", "selective_ulm"]))
    seeds = list(cfg.get("seeds", [42]))
    safety = float(cfg.get("safety_margin_ms", 500))
    rotate = bool(cfg.get("rotate_methods", True))

    rows: List[Dict[str, Any]] = []
    method_cycle = cycle(range(len(methods)))

    for graph in graphs:
        for seed in seeds:
            for timeout in _timeouts_for(graph.n, mode, cfg):
                order = list(methods)
                if rotate:
                    shift = next(method_cycle) % len(order)
                    order = order[shift:] + order[:shift]
                for method in order:
                    print(
                        f"[bench] {mode} graph={graph.name} n={graph.n} "
                        f"method={method} t={timeout}s seed={seed}",
                        flush=True,
                    )
                    row = _run_one(graph, method, timeout, seed, safety)
                    rows.append(row)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"benchmark_{mode}_{stamp}.json"
    csv_path = output_dir / f"benchmark_{mode}_{stamp}.csv"
    latest_json = output_dir / f"benchmark_{mode}_latest.json"
    latest_csv = output_dir / f"benchmark_{mode}_latest.csv"

    payload = {"env": _env_info(), "config": cfg, "results": rows}
    json_path.write_text(json.dumps(payload, indent=2))
    latest_json.write_text(json.dumps(payload, indent=2))

    fieldnames = sorted({k for r in rows for k in r.keys() if k != "extras"})
    # Flatten a few extras.
    fieldnames.extend(
        [
            "max_depth",
            "selective_activated",
            "selective_skipped",
            "selective_additional_prunes",
        ]
    )
    fieldnames = list(dict.fromkeys(fieldnames))

    def flat(r: Dict[str, Any]) -> Dict[str, Any]:
        out = {k: v for k, v in r.items() if k != "extras"}
        extras = r.get("extras") or {}
        out["max_depth"] = extras.get("max_depth")
        sel = extras.get("selective") or {}
        out["selective_activated"] = sel.get("activated")
        out["selective_skipped"] = sel.get("skipped")
        out["selective_additional_prunes"] = sel.get("additional_prunes")
        # Drop large clique vertex lists from CSV readability? keep size only.
        if "clique" in out and isinstance(out["clique"], list) and len(out["clique"]) > 40:
            out["clique"] = out["clique"][:40] + ["..."]
        return out

    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(flat(r))
    with latest_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(flat(r))

    print(f"Wrote {json_path} ({len(rows)} runs)")
    return rows


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["quick", "full"], default="quick")
    ap.add_argument("--output", default=str(ROOT / "reports"))
    args = ap.parse_args()
    run_benchmark(args.mode, Path(args.output))
