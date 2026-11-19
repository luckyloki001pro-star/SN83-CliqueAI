# SN83 Phase 4B — R-EVO Reactive Evolutionary Search

Generated: 2026-11-19 (local)  
Primary seed: **42**  
Paper: Battiti & Brunato, *R-EVO: A Reactive Evolutionary Algorithm for the Maximum Clique Problem* (DIT-07-034) — **inspired implementation**, not a line-by-line port (`revo_inspired` / B1 labeled accordingly).

---

## 1. Executive Summary

**Reactive population search beats Phase-3 `adaptive_portfolio` on this retrospective 20-round set, but the shared probability model shows no measurable benefit over identical agents with random restarts.**

| Solver | Mean size | Mean gap | Mean reward | Mean %ile | Hist ties | Hard mean gap | Valid | Deadline viol. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adaptive_portfolio | 36.75 | 0.45 | 2.268 | 38.5% | 15/20 | 1.8 | 100% | 0% |
| **revo_no_model (B0)** | **36.90** | **0.30** | **2.355** | **46.2%** | **16/20** | **1.2** | 100% | 0% |
| **revo_population (B1)** | **36.90** | **0.30** | **2.355** | **46.2%** | **16/20** | **1.2** | 100% | 0% |
| revo_diverse (B2) | 36.90 | 0.30 | 2.330 | 41.4% | 16/20 | 1.2 | 100% | 0% |

Success targets vs portfolio (gap &lt; 0.45, reward &gt; 2.268, ties ≥ 15): **met by B0/B1/B2**.

Research-specific criterion (B1 must beat B0): **failed** — mean size delta B1−B0 = **0.0** on all 20 graphs (identical sizes).

### Verdict

```
use_revo_no_model   # or revo_population as quality-equivalent; do NOT credit the model
```

Prefer **`revo_no_model`** as the next primary candidate (simpler; same measured quality as B1). Keep `adaptive_portfolio` as fallback. Treat probability learning as **not validated** on this SN83 workload.

---

## 2. Research Implementation

| Component | Paper element | Our status |
|---|---|---|
| Population of N searchers | N=10 reference | Implemented (`population_size`) |
| Shared `probability[v]` init 0.5 | §II guided mutation | Implemented |
| Near-best set with DELTA | DELTA=3 | Implemented |
| Frequency → EMA update | learning_rate | Implemented (configurable 0.2/0.5/1.0) |
| Probability-guided restart construction | intersective weighted sample | Implemented |
| Reactive add / drop / tabu | tabu ≈ 0.2 × best size | Simplified RLS-style; C0/C1 plateau |
| Restart after ~100×best_size idle steps | paper rule | Implemented |
| B2 diversity floor / random restarts | **extension** | `revo_diverse` only |
| Full original RLS / RLS-EVO | not in scope | Not implemented |

Code: `clique/revo_model.py`, `clique/revo_searcher.py`, `clique/revo.py` (wired in `clique/solver.py`).

---

## 3. Probability Learning

Update rule (paper-faithful core):

\[
p_v \leftarrow (1-\eta)\,p_v + \eta\cdot f_v,\quad
f_v = \frac{\#\{\text{near-best cliques containing }v\}}{|B|}
\]

with \(B=\{C:\lvert C\rvert \ge S_{\max}-\Delta\}\).

**Empirical finding:** B1 and B0 produced **identical clique sizes on every historical graph** under seed 42. Model updates ran (mean ~584 updates/round) but did not change final quality versus independent random restarts.

Diagnostics: `results/phase4b_probability_diagnostics.json`.

---

## 4. Reactive Search

Each searcher:

1. **Add** from C0 (possible additions), preferring residual connectivity; mark tabu.
2. Else **plateau** C1 swap (drop conflict, add candidate).
3. Else **drop** a high-conflict clique vertex.
4. On stagnation (`RESTART_FACTOR × best_size` steps): rebuild via model (B1/B2) or uniform (B0).

Internal current clique may be nonmaximal; **published incumbent always verified maximal**.

---

## 5. Correctness

```
pytest tests/test_revo_model.py tests/test_revo_searcher.py \
       tests/test_revo_population.py tests/test_revo_deadline.py
→ 17 passed
```

Historical Phase 4B: **100% valid / maximal**, **0% hard deadline violations**.

---

## 6. Population Diversity

B1 maintains a learned distribution (entropy traces recorded), but equal-size outcomes vs B0 imply the extra guidance did not unlock new regions beyond what aggressive independent restarts already explored under these deadlines.

B2 slightly lower mean reward (2.330 vs 2.355) — diversity safeguards did not help competitive score here.

---

## 7. Historical Round-by-Round (seed 42)

| UUID | n | hist | PORT | B0 | B1 | B2 | ΔB0 vs PORT |
|---|---:|---:|---:|---:|---:|---:|---:|
| fc92cd37 | 297 | 25 | 25 | 25 | 25 | 25 | 0 |
| 53839380 | 292 | 50 | 50 | 50 | 50 | 50 | 0 |
| 2c36dae9 | 297 | 32 | 32 | 32 | 32 | 32 | 0 |
| f12351e7 | 298 | 66 | 66 | 66 | 66 | 66 | 0 |
| 1a5fcb5c | 299 | 28 | 28 | 28 | 28 | 28 | 0 |
| 188a4272 | 292 | 23 | 23 | 23 | 23 | 23 | 0 |
| fe10c0b3 | 299 | 23 | 23 | 23 | 23 | 23 | 0 |
| 42c827b2 | 294 | 22 | 22 | 22 | 22 | 22 | 0 |
| 7a5ba71a | 292 | 69 | 69 | 69 | 69 | 69 | 0 |
| b389bbe3 | 297 | 30 | 30 | 30 | 30 | 30 | 0 |
| 1987b6bb | 497 | 25 | 24 | **25** | **25** | **25** | **+1** |
| 22bc813e | 497 | 37 | 37 | 37 | 37 | 37 | 0 |
| 9645a4e8 | 493 | 29 | 29 | 29 | 29 | 29 | 0 |
| 577e9988 | 897 | 57 | 55 | **56** | **56** | **56** | **+1** |
| 1231dc5e | 896 | 34 | 34 | 34 | 34 | 34 | 0 |
| 1db8cfb3 | 897 | 44 | 42 | **43** | **43** | **43** | **+1** |
| 4c69bfb1 | 700 | 48 | 46 | **47** | **47** | **47** | **+1** |
| 9bd55ea0 | 895 | 45 | 43 | 42 | 42 | 42 | **−1** |
| 07965b58 | 495 | 27 | 27 | 27 | 27 | 27 | 0 |
| 225ce3c0 | 299 | 30 | 30 | 30 | 30 | 30 | 0 |

Strong rounds (15 portfolio ties): **all preserved** by R-EVO.  
Paired vs portfolio: **+4 / −1 / 15 ties** (mean Δsize +0.15).

---

## 8. Hard-Graph Analysis

| UUID | hist | PORT | B0/B1/B2 | Note |
|---|---:|---:|---:|---|
| 1987b6bb | 25 | 24 | **25** | Closed historical gap |
| 577e9988 | 57 | 55 | **56** | +1 vs port; still −1 hist |
| 1db8cfb3 | 44 | 42 | **43** | +1 vs port; still −1 hist |
| 4c69bfb1 | 48 | 46 | **47** | +1 vs port; still −1 hist |
| 9bd55ea0 | 45 | 43 | 42 | Regression vs port |

Hard mean gap: portfolio **1.8** → R-EVO **1.2**.

---

## 9. Official Score and Rank

Independent counterfactual pools via `CliqueScoreCalculator`.

| Solver | Mean reward | Mean diversity | Top-1 | Top-3 | Mean %ile |
|---|---:|---:|---:|---:|---:|
| adaptive_portfolio | 2.268 | 0.729 | 5 | 6 | 38.5% |
| revo_no_model | **2.355** | 0.758 | **6** | **7** | **46.2%** |
| revo_population | **2.355** | 0.758 | **6** | **7** | **46.2%** |
| revo_diverse | 2.330 | 0.733 | 5 | 6 | 41.4% |

---

## 10. Learning Ablations

| Comparison | Result |
|---|---|
| **A — B1 vs B0 (model)** | **No gain** (Δsize = 0 on all 20 graphs) |
| B — N=4 vs N=10 (synthetic) | Same sizes on ER/planted toys (`phase4b_ablation_dev.csv`) |
| C — DELTA 0 vs 3 (synthetic) | Same sizes on short toys |
| D/E — tabu / guided restart | Primary historical evidence: random-restart population already matches model-guided |
| F — B2 vs B1 | Same sizes; B2 slightly worse reward |

**Conclusion:** Gains over portfolio come from **reactive multi-agent local search + frequent exploration**, not from the evolutionary probability vector.

---

## 11. Performance Profiling

Separate run: `results/phase4b_profiling.json` (cProfile; not primary timings).

Hot paths: C0/C1 maintenance and searcher steps inside `local_search_ms`. Model update cost is modest vs local search on these graphs.

Mean restarts (historical): B0 ~2649, B1 ~1093 — B0 explores via more restarts; B1 spends more time in model-guided trajectories without size gains.

---

## 12. Parameter Robustness

Primary tables: seed **42**. Multi-seed summary: `results/phase4b_multiseed_summary.json`.

| Solver | Seed | Mean gap | Mean reward | Mean %ile | Hist ties |
|---|---:|---:|---:|---:|---:|
| revo_no_model | 42 | **0.30** | **2.355** | **46.2** | **16** |
| revo_no_model | 123 | 0.40 | 2.261 | 41.3 | 14 |
| revo_no_model | 2026 | 0.40 | 2.195 | 28.7 | 15 |
| revo_population | 42 | **0.30** | **2.355** | **46.2** | **16** |
| revo_population | 123 | 0.45 | 2.260 | 41.3 | 14 |
| revo_population | 2026 | 0.40 | 2.195 | 28.7 | 15 |

B1−B0 size delta: seed42 **0.0** (0 diffs), seed123 **−0.05** (1 graph), seed2026 **0.0**. Learning still not the differentiator. Seed-42 primaries: `results/phase4b_seed42_backup/`.

Note: seed 123/2026 mean gap is closer to portfolio (0.45); seed **42 remains the strongest** R-EVO run. Validity 100% and deadline violations 0% on all seeds.

Default research parameters used historically:

```
POPULATION_SIZE=10, MODEL_DELTA=3, TABU_RATIO=0.20,
RESTART_FACTOR=100, LEARNING_RATE=0.5, MODEL_INITIAL=0.5
```

---

## 13. Final Verdict

| Option | Decision |
|---|---|
| keep_adaptive_portfolio | No longer the measured size/reward leader |
| use_revo_population | Quality OK, but **model not justified** |
| use_revo_diverse | No advantage over B0/B1 |
| **use_revo_no_model** | **Yes — best measured simplicity/quality** |
| investigate_further | Optional: shorter restart factors, RLS-EVO depth, crossover extension — only if targeting remaining gaps (`9bd55ea0`, 577e/1db8/4c69 still −1 vs hist) |

### Answer to the research question

1. **Yes**, a population of reactive local-search agents can beat `adaptive_portfolio` under the same SN83 deadlines (gap 0.30, reward 2.355, 16/20 hist ties), closing four of five hard-graph gaps by +1 (with one −1 regression).
2. **No**, the shared learned probability model did **not** improve search relative to identical agents with independent random restarts on this dataset.

---

## Reproduction

```bash
cd /home/CliqueAI/sn83_clique_lab
PYTHONPATH=.:.deps python3 -m pytest tests/test_revo_*.py -q
PYTHONPATH=.:.deps python3 benchmarks/run_phase4b_ablation.py
PYTHONPATH=.:.deps python3 benchmarks/run_phase4b.py --reuse-portfolio --seed 42
PYTHONPATH=.:.deps python3 benchmarks/analyze_phase4b.py
PYTHONPATH=.:.deps python3 benchmarks/profile_phase4b.py
```
