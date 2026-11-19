# SN83 Pure-Python ULM Clique Benchmark Report

## Executive Summary

Implemented and tested all four methods in pure Python:

| ID | Method | Status |
|----|--------|--------|
| A | Bitset branch-and-bound + greedy coloring | Tested |
| B | A + full unit-weight ULM | Tested (soundness + bench) |
| C | A + selective ULM | Tested |
| R | NetworkX `approximation.max_clique` | Tested |

**Quick-benchmark verdict (64 paired runs, 8 graphs, 6s/10s deadlines):**

- A, B, and C returned **identical clique sizes on every paired trial** (16/16 ties).
- ULM **does** reduce search nodes (~17% for full ULM vs baseline) and records thousands of ULM prunes, but the Python reasoning overhead (~15% of runtime for B, ~10% for C) offsets the gain under SN83-like deadlines.
- **A/B/C beat NetworkX** by ~+3.7 mean clique size (14 wins / 2 ties / 0 losses for baseline vs R).
- **Recommendation for miner development: Method A (`baseline`)**. Keep C as the preferred ULM variant if continuing research.

## Research Interpretation

ULM is based on ULE-MWC (IJCAI 2026) Algorithms 2–3 (`AddCore`, `ULM-MaxSAT`), specialized to **unit weights**:

- Every vertex weight is 1 ⇒ independent-set weight \(w^*(I)=1\) ⇒ conflict penalty \(\beta=1\).
- `split(I, 1)` locks the full set; the remainder \(I''\) is empty (no weighted residue pool).
- Conflict cores preserve locked sets; unlocking when `c.uw >= c.w`; nested conflicts merge cores and accumulate penalties.
- **BES is omitted** (first experiment, as specified).

Differences from the C reference (`ULE-MWC.c`):

- Idiomatic Python + integer bitsets (no C arrays / compiled kernels).
- Local per-call reasoning state (no global solver arena).
- Cooperative `perf_counter` deadlines with safety margin.
- Not a line-by-line port; invariants were re-derived from the paper.

## Correctness Results

```text
84 passed in 0.24s
```

Coverage includes:

- Bitset / graph construction
- Greedy maximal cliques
- Coloring bound validity (independent color classes; bound ≥ exact ω)
- A/B/C vs exhaustive oracle on 15 small graph families (empty, complete, star, path, bipartite, disconnected, ER, planted), n≈5–18
- ULM soundness: `exact_ω ≤ ulm_bound ≤ coloring_bound` on 20 random n=12 graphs + structured cases
- Conflict-core create / merge / unlock / rollback
- Deadline returns valid maximal cliques

No ULM soundness assertion failures; pruning remains enabled.

## Benchmark Environment

- CPU: Intel Core i7-7700 @ 3.60GHz (4c/8t)
- Memory: ~16 GB
- OS: Linux WSL2 (6.18.54.1-microsoft-standard-WSL2)
- Python: 3.12.3
- Key deps: networkx 3.4.2, numpy 2.2.6, pytest 9.2.0
- Timestamp: 2026-11-18T23:06:15

SN83 settings verified from local `CliqueAI/selection/problem_selector.py`:

- n∈[290,300]/[490,500]/[690,700]/[890,900]
- difficulties 0.7 / 0.8 / 0.9 / 1.0
- time limits 6 / 7.5 / 10 / 15 / 30 s; **890–900 excludes 6 s**

Official samples decoded (Base92):

| Graph | n | Density |
|-------|--:|--------:|
| sample | 3 | 1.000 |
| general_0.1 | 90 | 0.805 |
| general_0.2 | 298 | 0.736 |
| general_0.4 | 493 | 0.735 |

## Main Results

Quick mode: official samples + selected n=300 ER graphs; methods A/B/C/R; timeouts 6s & 10s; seed 42; shared incumbent; rotated method order.

| Method | Runs | Mean Size | Median Size | Best Size | Mean Runtime ms | Mean Nodes | Mean ULM ms | Invalid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 16 | 17.562 | 21 | 23 | 5635.7 | 72526 | 0.00 | 0 |
| ulm | 16 | 17.562 | 21 | 23 | 5637.7 | 57510 | 848.86 | 0 |
| selective_ulm | 16 | 17.562 | 21 | 23 | 5637.5 | 57870 | 589.50 | 0 |
| networkx | 16 | 13.875 | 16 | 18 | 1979.9 | 0 | 0.00 | 0 |

### Representative SN83-like rows

| Method | Graph | Nodes | Density | Deadline | Clique Size | Runtime ms | Search Nodes | ULM Time ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | general_0.2 | 298 | 0.736 | 6.0 | 21 | 5500.6 | 73528 | 0.00 |
| ulm | general_0.2 | 298 | 0.736 | 6.0 | 21 | 5501.6 | 56412 | 837.51 |
| selective_ulm | general_0.2 | 298 | 0.736 | 6.0 | 21 | 5500.3 | 61662 | 529.66 |
| networkx | general_0.2 | 298 | 0.736 | 6.0 | 16 | 1811.8 | 0 | 0.00 |
| baseline | general_0.4 | 493 | 0.735 | 10.0 | 23 | 9500.7 | 103803 | 0.00 |
| ulm | general_0.4 | 493 | 0.735 | 10.0 | 23 | 9502.2 | 86128 | 1319.01 |
| selective_ulm | general_0.4 | 493 | 0.735 | 10.0 | 23 | 9500.7 | 44527 | 746.94 |
| networkx | general_0.4 | 493 | 0.735 | 10.0 | 18 | 6654.1 | 0 | 0.00 |

Full machine-readable tables: `reports/benchmark_quick_latest.json` / `.csv`.

## ULM Analysis

Paired comparisons (same graph, deadline, seed, incumbent):

| Pair | Wins / Ties / Losses (clique size) | Mean size Δ | Mean node reduction |
|------|-------------------------------------|------------:|--------------------:|
| B vs A | 0 / 16 / 0 | 0.000 | ~17% fewer nodes for B |
| C vs A | 0 / 16 / 0 | 0.000 | ~14% fewer nodes for C |
| C vs B | 0 / 16 / 0 | 0.000 | similar |

Answers to the research questions:

1. **Larger cliques in 6s?** No — ties everywhere.
2. **Improve 10s results?** No — same sizes; more nodes explored but not enough to beat the shared incumbent/search path.
3. **Help more at 30s?** Not measured in quick mode; full suite command is provided. Node reduction suggests possible benefit only if search depth becomes the limiter.
4. **Full ULM too expensive?** Yes in Python: ~15% of wall time in ULM reasoning on average; up to ~1.7s ULM time inside a 10s run.
5. **Selective ULM avoid overhead?** Partially — ~10% overhead vs ~15%, with nearly the same sizes and similar node counts.
6. **Dense vs structured?** Quick set is mostly dense ER / official; no size separation observed.
7. **Fewer nodes without larger cliques?** Yes — clear node reduction / ULM prunes without size gains under these deadlines.
8. **Python overhead make ULM impractical?** For SN83 miner deadlines aiming at larger cliques: **yes, currently impractical as a size booster**. Useful as a pruning research tool, not yet a quality win.

## Selective ULM Analysis

Policy defaults: `gap∈(0,2]`, `candidates≥16`, `remaining≥150ms`, `ULM_MAX_TIME_FRACTION=0.15`.

- Same clique quality as full ULM.
- Lower mean ULM time (589ms vs 849ms).
- Prefer **C over B** if ULM is retained; prefer **A** for production miner code today.

## Python Bottlenecks

`cProfile` on ER n=120, p=0.7, 2s timeout (`reports/profile_*.txt`):

| Hot spot | Role |
|----------|------|
| `greedy_color_candidates` | Dominates BnB time |
| `bits_to_list` / per-class sorts | Coloring support cost |
| `ULMReasoner.tighten_bound` | Extra cost in B/C |
| Python recursion in `expand` | Noticeable but secondary |

Coloring is the first optimization target for the baseline; ULM object/propagation cost is the barrier for B/C.

## Final Recommendation

**Use Method A (`baseline`) for further SN83 miner development.**

Reasons (measured):

- Matches B/C clique sizes under 6–10s SN83-like deadlines.
- No ULM overhead → more search nodes per second.
- Already far stronger than the official NetworkX reference (R).
- B/C pass correctness tests, so they remain valid research branches; if continuing ULM work, prefer **C (selective)** over full B.

ULM in pure Python tightens bounds and prunes, but does **not** currently improve returned clique size on dense 90–500 vertex instances within SN83 deadlines.

## Plots

- `reports/plot_clique_vs_deadline.svg`
- `reports/plot_ulm_overhead.svg`
- `reports/plot_search_nodes.svg`

Generated as SVG without matplotlib (local `.venv` site-packages is read-only here).

## Reproduction Commands

```bash
cd sn83_clique_lab
PYTHONPATH=. /home/CliqueAI/.venv/bin/python3 -m pip install -e .   # if venv writable
# otherwise:
export PYTHONPATH=/home/CliqueAI/sn83_clique_lab

python3 -m clique prepare-data --splits dev tune eval
python3 -m pytest tests/ -q
python3 -m clique.benchmark --mode quick
python3 -m clique.benchmark --mode full    # explicit; long-running
python3 benchmarks/analyze.py --input reports/benchmark_quick_latest.json

# single solve
python3 -m clique.solve --graph datasets/official/general_0.2.adj.json --solver baseline --timeout 10 --fair
python3 -m clique.solve --graph datasets/official/general_0.2.adj.json --solver selective_ulm --timeout 10 --fair
```

Miner-facing API:

```python
from clique import solve_clique
clique = solve_clique(adjacency_list, timeout_seconds=10.0, variant="baseline", seed=42)
```
