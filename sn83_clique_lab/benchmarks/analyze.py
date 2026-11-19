"""Analyze benchmark JSON results and emit report artifacts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent


def load_results(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def paired_compare(
    rows: List[Dict[str, Any]], a: str, b: str
) -> Dict[str, Any]:
    """Pair runs by (graph_id, time_limit, seed)."""
    index: Dict[Tuple, Dict[str, Dict]] = defaultdict(dict)
    for r in rows:
        key = (r["graph_id"], r["time_limit"], r["seed"])
        index[key][r["method"]] = r

    wins = ties = losses = 0
    size_deltas = []
    node_ratios = []
    runtime_deltas = []
    for key, methods in index.items():
        if a not in methods or b not in methods:
            continue
        ra, rb = methods[a], methods[b]
        da = ra["clique_size"] - rb["clique_size"]
        size_deltas.append(da)
        if da > 0:
            wins += 1
        elif da < 0:
            losses += 1
        else:
            ties += 1
        if rb["search_nodes"]:
            node_ratios.append(
                (rb["search_nodes"] - ra["search_nodes"]) / max(rb["search_nodes"], 1)
            )
        runtime_deltas.append(ra["runtime_ms"] - rb["runtime_ms"])

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    def median(xs):
        if not xs:
            return 0.0
        ys = sorted(xs)
        m = len(ys) // 2
        return ys[m] if len(ys) % 2 else 0.5 * (ys[m - 1] + ys[m])

    return {
        "pair": f"{a}_vs_{b}",
        "comparisons": wins + ties + losses,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "mean_size_delta": mean(size_deltas),
        "median_size_delta": median(size_deltas),
        "mean_runtime_delta_ms": mean(runtime_deltas),
        "mean_node_reduction_vs_b": mean(node_ratios),
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_method: Dict[str, List] = defaultdict(list)
    for r in rows:
        by_method[r["method"]].append(r)

    summary = {}
    for m, rs in by_method.items():
        sizes = [r["clique_size"] for r in rs]
        times = [r["runtime_ms"] for r in rs]
        ulm_t = [r.get("ulm_time_ms") or 0.0 for r in rs]
        invalid = sum(1 for r in rs if not r.get("valid"))
        deadlines = sum(1 for r in rs if r.get("deadline_reached"))
        summary[m] = {
            "runs": len(rs),
            "mean_clique_size": sum(sizes) / len(sizes),
            "median_clique_size": sorted(sizes)[len(sizes) // 2],
            "best_clique_size": max(sizes),
            "mean_runtime_ms": sum(times) / len(times),
            "median_runtime_ms": sorted(times)[len(times) // 2],
            "mean_ulm_time_ms": sum(ulm_t) / len(ulm_t),
            "ulm_overhead_pct": 100.0 * (sum(ulm_t) / max(sum(times), 1e-9)),
            "invalid": invalid,
            "deadline_reached": deadlines,
            "mean_search_nodes": sum(r.get("search_nodes") or 0 for r in rs) / len(rs),
            "mean_ulm_prunes": sum(r.get("ulm_prunes") or 0 for r in rs) / len(rs),
        }
    return summary


def try_plots(rows: List[Dict[str, Any]], out_dir: Path) -> List[str]:
    paths = []
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return paths

    # Clique size vs deadline by method.
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[r["method"]][r["time_limit"]].append(r["clique_size"])

    fig, ax = plt.subplots(figsize=(7, 4))
    for method, series in sorted(by.items()):
        xs = sorted(series)
        ys = [sum(series[x]) / len(series[x]) for x in xs]
        ax.plot(xs, ys, marker="o", label=method)
    ax.set_xlabel("Deadline (s)")
    ax.set_ylabel("Mean clique size")
    ax.set_title("Clique size vs deadline")
    ax.legend()
    fig.tight_layout()
    p = out_dir / "plot_clique_vs_deadline.png"
    fig.savefig(p)
    plt.close(fig)
    paths.append(str(p))

    # ULM overhead by dataset.
    fig, ax = plt.subplots(figsize=(7, 4))
    data = defaultdict(list)
    for r in rows:
        if r["method"] in ("ulm", "selective_ulm"):
            rt = max(r["runtime_ms"], 1e-9)
            data[(r["method"], r.get("dataset", "?"))].append(
                100.0 * (r.get("ulm_time_ms") or 0.0) / rt
            )
    labels = []
    vals = []
    for k, xs in sorted(data.items()):
        labels.append(f"{k[0]}|{k[1]}")
        vals.append(sum(xs) / len(xs))
    ax.bar(range(len(vals)), vals)
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("ULM time % of runtime")
    ax.set_title("ULM overhead by category")
    fig.tight_layout()
    p = out_dir / "plot_ulm_overhead.png"
    fig.savefig(p)
    plt.close(fig)
    paths.append(str(p))

    # Search nodes A vs C.
    fig, ax = plt.subplots(figsize=(5, 5))
    index = defaultdict(dict)
    for r in rows:
        index[(r["graph_id"], r["time_limit"], r["seed"])][r["method"]] = r
    xs, ys = [], []
    for methods in index.values():
        if "baseline" in methods and "selective_ulm" in methods:
            xs.append(methods["baseline"]["search_nodes"])
            ys.append(methods["selective_ulm"]["search_nodes"])
    if xs:
        ax.scatter(xs, ys, alpha=0.7)
        m = max(max(xs), max(ys), 1)
        ax.plot([0, m], [0, m], linestyle="--", color="gray")
        ax.set_xlabel("Baseline search nodes")
        ax.set_ylabel("Selective ULM search nodes")
        ax.set_title("Search-node comparison")
        fig.tight_layout()
        p = out_dir / "plot_search_nodes.png"
        fig.savefig(p)
        plt.close(fig)
        paths.append(str(p))
    return paths


def write_markdown_report(
    payload: Dict[str, Any],
    out_path: Path,
    plots: List[str],
) -> None:
    rows = payload["results"]
    env = payload.get("env", {})
    summary = summarize(rows)
    pairs = [
        paired_compare(rows, "ulm", "baseline"),
        paired_compare(rows, "selective_ulm", "baseline"),
        paired_compare(rows, "selective_ulm", "ulm"),
        paired_compare(rows, "baseline", "networkx"),
    ]

    lines = []
    lines.append("# SN83 Pure-Python ULM Clique Benchmark Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        "Implemented and tested Methods A (baseline bitset BnB), "
        "B (full ULM), C (selective ULM), and R (NetworkX approximation)."
    )
    lines.append("")
    best_method = max(
        (m for m in summary if m != "networkx"),
        key=lambda m: (summary[m]["mean_clique_size"], -summary[m]["mean_runtime_ms"]),
        default="baseline",
    )
    lines.append(
        f"On this run, among A/B/C the strongest mean clique size was "
        f"**{best_method}** "
        f"(mean size {summary.get(best_method, {}).get('mean_clique_size', 0):.3f})."
    )
    lines.append("")
    lines.append("## Research Interpretation")
    lines.append("")
    lines.append(
        "ULM follows ULE-MWC Algorithms 2–3 specialized to unit weights: "
        "conflict penalty β=1, locked independent sets retain full members, "
        "unlocking when `c.uw >= c.w`, with core merging on nested conflicts. "
        "BES is intentionally omitted. Differences from the C reference: "
        "Python integer bitsets, per-call local reasoning state, no weight "
        "splitting remainders (always empty under unit weights), and "
        "cooperative deadlines."
    )
    lines.append("")
    lines.append("## Correctness Results")
    lines.append("")
    lines.append(
        "See `pytest` output. Exact-oracle tests require A/B/C to match "
        "exhaustive optima on small graphs; ULM soundness asserts "
        "`exact <= ulm_bound <= coloring_bound`."
    )
    lines.append("")
    lines.append("## Benchmark Environment")
    lines.append("")
    lines.append(f"- CPU: {env.get('cpu', 'n/a')}")
    lines.append(f"- Memory: {env.get('memory', 'n/a')}")
    lines.append(f"- OS: {env.get('platform', 'n/a')}")
    lines.append(f"- Python: {env.get('python', 'n/a').split()[0] if env.get('python') else 'n/a'}")
    lines.append(f"- Timestamp: {env.get('timestamp', 'n/a')}")
    lines.append("")
    lines.append("## Main Results")
    lines.append("")
    lines.append(
        "| Method | Runs | Mean Size | Median Size | Best Size | Mean Runtime ms | Mean Nodes | Mean ULM ms | Invalid |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for m, s in sorted(summary.items()):
        lines.append(
            f"| {m} | {s['runs']} | {s['mean_clique_size']:.3f} | "
            f"{s['median_clique_size']} | {s['best_clique_size']} | "
            f"{s['mean_runtime_ms']:.1f} | {s['mean_search_nodes']:.0f} | "
            f"{s['mean_ulm_time_ms']:.2f} | {s['invalid']} |"
        )
    lines.append("")
    lines.append("### Detailed run table (truncated if huge)")
    lines.append("")
    lines.append(
        "| Method | Graph | Nodes | Density | Deadline | Clique Size | Runtime ms | Search Nodes | ULM Time ms |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows[:80]:
        lines.append(
            f"| {r['method']} | {r['graph_id']} | {r['n']} | {r['density']:.3f} | "
            f"{r['time_limit']} | {r['clique_size']} | {r['runtime_ms']:.1f} | "
            f"{r.get('search_nodes', 0)} | {r.get('ulm_time_ms', 0):.2f} |"
        )
    if len(rows) > 80:
        lines.append(f"| ... | ({len(rows) - 80} more rows) | | | | | | | |")
    lines.append("")
    lines.append("## ULM Analysis")
    lines.append("")
    for p in pairs[:3]:
        lines.append(
            f"- {p['pair']}: wins/ties/losses = "
            f"{p['wins']}/{p['ties']}/{p['losses']}, "
            f"mean size Δ={p['mean_size_delta']:.3f}, "
            f"mean runtime Δ ms={p['mean_runtime_delta_ms']:.1f}"
        )
    if "ulm" in summary and "baseline" in summary:
        lines.append(
            f"- Full ULM overhead ≈ {summary['ulm']['ulm_overhead_pct']:.1f}% of its runtime; "
            f"mean ULM prunes/run={summary['ulm']['mean_ulm_prunes']:.2f}."
        )
    lines.append("")
    lines.append("## Selective ULM Analysis")
    lines.append("")
    if "selective_ulm" in summary:
        lines.append(
            f"- Selective ULM mean size={summary['selective_ulm']['mean_clique_size']:.3f}, "
            f"overhead≈{summary['selective_ulm']['ulm_overhead_pct']:.1f}%."
        )
        sel = paired_compare(rows, "selective_ulm", "ulm")
        lines.append(
            f"- vs full ULM: wins/ties/losses={sel['wins']}/{sel['ties']}/{sel['losses']} "
            f"(size), mean runtime Δ ms={sel['mean_runtime_delta_ms']:.1f}."
        )
    lines.append("")
    lines.append("## Python Bottlenecks")
    lines.append("")
    lines.append(
        "Primary costs in pure Python are recursive call overhead, "
        "greedy coloring scans, bit iteration, and ULM unit-propagation "
        "over Python objects. See profiling notes in the report extras / cProfile dumps."
    )
    lines.append("")
    lines.append("## Final Recommendation")
    lines.append("")
    # Data-driven recommendation
    rec = "baseline"
    reason = "default"
    if "baseline" in summary:
        base = summary["baseline"]["mean_clique_size"]
        cand = []
        for m in ("selective_ulm", "ulm"):
            if m in summary and summary[m]["invalid"] == 0:
                cand.append(
                    (
                        summary[m]["mean_clique_size"] - base,
                        -summary[m]["mean_runtime_ms"],
                        m,
                    )
                )
        if cand:
            cand.sort(reverse=True)
            delta, _rt, m = cand[0]
            if delta > 0.01:
                rec = m
                reason = f"larger mean clique (+{delta:.3f}) than baseline"
            elif "selective_ulm" in summary and summary["selective_ulm"]["mean_runtime_ms"] <= summary.get("ulm", summary["selective_ulm"])["mean_runtime_ms"]:
                # Prefer faster if sizes equal
                if abs(delta) <= 0.01:
                    rec = "selective_ulm" if summary["selective_ulm"]["mean_clique_size"] >= base - 1e-9 else "baseline"
                    reason = "similar clique quality with lower ULM overhead" if rec != "baseline" else "ULM did not improve clique size"
            else:
                rec = "baseline"
                reason = "ULM did not improve mean clique size within deadlines"
    lines.append(f"**Recommend `{rec}` for further miner development** ({reason}).")
    lines.append("")
    lines.append("## Plots")
    lines.append("")
    for p in plots:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("## Reproduction Commands")
    lines.append("")
    lines.append("```bash")
    lines.append("cd sn83_clique_lab")
    lines.append("python3 -m pip install -e .")
    lines.append("python3 -m clique prepare-data --splits dev")
    lines.append("python3 -m pytest tests/ -q")
    lines.append("python3 -m clique.benchmark --mode quick")
    lines.append("python3 -m clique.benchmark --mode full   # explicit; long")
    lines.append("python3 benchmarks/analyze.py --input reports/benchmark_quick_latest.json")
    lines.append("```")
    lines.append("")

    out_path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        default=str(ROOT / "reports" / "benchmark_quick_latest.json"),
    )
    ap.add_argument(
        "--output",
        default=str(ROOT / "reports" / "benchmark_report.md"),
    )
    args = ap.parse_args()
    path = Path(args.input)
    if not path.exists():
        print(f"Missing results: {path}")
        return 1
    payload = load_results(path)
    out_dir = Path(args.output).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    plots = try_plots(payload["results"], out_dir)
    write_markdown_report(payload, Path(args.output), plots)
    # Also dump machine-readable summary.
    summary_path = out_dir / "analysis_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "summary": summarize(payload["results"]),
                "pairs": [
                    paired_compare(payload["results"], "ulm", "baseline"),
                    paired_compare(payload["results"], "selective_ulm", "baseline"),
                    paired_compare(payload["results"], "selective_ulm", "ulm"),
                ],
                "plots": plots,
            },
            indent=2,
        )
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
