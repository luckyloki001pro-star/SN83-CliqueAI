# sn83_clique_lab

Pure-Python maximum-clique research lab for Bittensor SN83 (CliqueAI).

Compares:

| ID | Method |
|----|--------|
| A | Bitset branch-and-bound + greedy coloring |
| B | A + full unit-weight ULM conflict-core reasoning |
| C | A + selective ULM activation |
| R | Official NetworkX approximation |

No Bittensor mining, no C/C++/Cython/Numba solver backends.

## Setup

```bash
cd sn83_clique_lab
python3 -m pip install -e .
# or use the workspace venv:
# /home/CliqueAI/.venv/bin/python3 -m pip install -e .
```

## Commands

```bash
# Import official SN83 samples + generate synthetic graphs
python3 -m clique prepare-data --splits dev

# Correctness tests
python3 -m pytest tests/ -q

# Solve one graph
python3 -m clique.solve --graph datasets/official/sample.adj.json --solver baseline --timeout 10
python3 -m clique.solve --graph datasets/official/sample.adj.json --solver ulm --timeout 10
python3 -m clique.solve --graph datasets/official/sample.adj.json --solver selective_ulm --timeout 10

# Quick benchmark (runs automatically after tests in the research workflow)
python3 -m clique.benchmark --mode quick

# Full benchmark (explicit only; long-running)
python3 -m clique.benchmark --mode full

# Analyze + write reports/benchmark_report.md
python3 benchmarks/analyze.py --input reports/benchmark_quick_latest.json
```

## Miner-facing API

```python
from clique import solve_clique

clique = solve_clique(adjacency_list, timeout_seconds=10.0, variant="selective_ulm", seed=42)
```

## SN83 time limits (from public `problem_selector.py`)

- 290–300, 490–500, 690–700 vertices: 6 / 7.5 / 10 / 15 / 30 s
- 890–900 vertices: 7.5 / 10 / 15 / 30 s (no 6 s)

## Historical SN83 evaluation (latest 20 W&B challenges)

```bash
cd sn83_clique_lab
export PYTHONPATH=.:.deps

# 1) Fetch latest complete challenges from W&B (requires wandb login / WANDB_API_KEY)
python3 -m benchmarks.fetch_sn83_history --limit 20

# 1b) Or import a manual W&B table/history export (JSON / JSONL / CSV)
python3 -m benchmarks.import_history --file /path/to/exported_wandb_data.jsonl

# 2) Verify graphs + reproduce logged scores
python3 -m benchmarks.verify_history

# 3) Run local solvers on historical graphs (uses each record's time_limit)
python3 -m benchmarks.run_historical --solver all
# or one variant:
python3 -m benchmarks.run_historical --solver baseline

# 4) Insert answers into historical pools and rescore
python3 -m benchmarks.recalculate_scores

# 5) Aggregate ranks / cautious prediction
python3 -m benchmarks.predict_rank

# 6) Write reports/sn83_latest20_benchmark.md
python3 -m benchmarks.generate_report
```

Outputs:

- `datasets/sn83_history/latest20.jsonl`
- `datasets/sn83_history/manifest.json`
- `results/historical_miners.csv`
- `results/historical_score_verification.csv`
- `results/{baseline,ulm,selective_ulm}_responses.jsonl`
- `results/round_comparison.csv`
- `results/miner_ranking_summary.csv`
- `reports/data_access_status.md`
- `reports/sn83_latest20_benchmark.md`

If W&B access fails, the fetch step documents the blocker and does **not** invent historical challenges.

## Layout

See `clique/`, `datasets/`, `benchmarks/`, `tests/`, `reports/`.
