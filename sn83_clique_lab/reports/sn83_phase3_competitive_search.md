# SN83 Phase 3 — Competitive Local Search Research

Generated: 2026-11-19 (local)  
Branch: `experiment/sn83-anytime-local-search`  
Primary seed: **42** (reported below)  
Additional seeds: 123, 2026 (robustness; see §12 when available)

---

## Executive verdict

**`adaptive_portfolio` beats Phase-2 `triangle_guided` (Method F)** on the retrospective 20-round historical benchmark under identical deadlines and official counterfactual scoring:

| Solver | Mean size | Mean gap | Mean reward | Mean rank % | Top-1 | Hist ties | Hard mean gap | Valid | Deadline viol. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F `triangle_guided` | 36.40 | 0.80 | 2.136 | 25.3% | 3 | 13/20 | 2.80 | 100% | 0% |
| G `bls_adaptive` | 36.30 | 0.90 | 2.066 | 29.3% | 4 | 8/20 | 2.00 | 100% | 0% |
| H `pls_penalty` | 35.70 | 1.50 | 1.946 | 26.2% | 3 | 3/20 | 2.80 | 100% | 0% |
| I `ikls_variable_depth` | 36.50 | **0.70** | **2.188** | **33.0%** | **5** | 12/20 | 2.00 | 100% | 0% |
| J `pair_anchor` | 36.65 | **0.55** | 2.159 | 29.3% | 3 | 13/20 | **1.80** | 100% | 0% |
| P `adaptive_portfolio` | **36.75** | **0.45** | **2.268** | **38.5%** | **5** | **15/20** | **1.60** | 100% | 0% |

Success criteria vs F (gap &lt; 0.80, higher reward, higher percentile, better 700–900, 100% validity, zero hard deadline violations): **met by portfolio**, and also by **pair_anchor** (gap/hard) and **ikls** (gap/reward/percentile).

**Recommendation for the next SN83 miner solver: `adaptive_portfolio`**, with `pair_anchor` + `ikls_variable_depth` as the strongest standalone contributors. Keep `triangle_guided` available as a fallback; do **not** ship standalone PLS as the primary.

---

## 1. Implementation and source references

Code: `clique/competitive_search.py` (wired via `clique/solver.py` variants).

These are **simplified pure-Python adaptations**. They are **not** claimed as exact reproductions of the papers. No third-party C++/source trees were copied (open-pls license checked; ideas only).

| ID | Solver | Inspired by | Core mechanisms implemented |
|---|---|---|---|
| H | `pls_penalty` | Pullan Phased Local Search; DLS-MC penalty ideas (Pullan & Hoos) | Phases random / degree / penalty; C0 add; C1 plateau swap; penalty decay; configurable 50/50/100 step schedule |
| G | `bls_adaptive` | Benlic & Hao Breakout Local Search | Local opt → adaptive directed/random perturbation strength L∈[2,8]; short tabu; stagnation / revisit escape; valid clique preserved under perturbation |
| I | `ikls_variable_depth` | Katayama et al. iterated k-opt / LEC-Kick | Bounded variable-depth add/drop sequences; best intermediate commit; structured LEC-style kick (prefer low edge-connectivity removals), not arbitrary drops |
| J | `pair_anchor` | Experimental + instance-structure intuition | Promising adjacent pairs; common-neighbor restriction; residual-degree build + local exchange; cached static pair scores |
| P | `adaptive_portfolio` | Algorithm-selection / portfolio practice | Single deadline sliced ~25% each G/H/I/J; shared elite/incumbent; not four full sequential deadlines |

### Phase-2 inspection (before Phase 3)

- Phase-2 **1-for-2 / 2-for-3** exchanges in `anytime_search.py` only accept **size-increasing** moves — **no neutral plateau moves**.
- Prior perturbations often returned to the same local optima (flat checkpoints after early best).
- BnB rarely improves the greedy incumbent under soft deadlines (`reports/sn83_anytime_search_report.md`).
- Phase-3 plateau (C0/C1) and adaptive perturbation / variable-depth / pair anchoring are therefore **genuinely different** mechanisms, not triangle-score retunes.

### Correctness

```
pytest tests/test_competitive_search.py  →  6 passed
```

Property checks cover C0/C1 plateau validity, perturbation clique invariance, maximality of public incumbents, and small-graph exhaustive consistency. Independent validator: `clique.validation` + official `CliqueScoreCalculator.is_valid_maximum_clique`.

---

## 2. Historical benchmark conditions

| Item | Value |
|---|---|
| Dataset | `datasets/sn83_history/latest20.jsonl` — **20 real** SN83 challenges |
| Role | **Retrospective comparable benchmark** (already examined in Phases 1–2; **not** untouched held-out) |
| Tuning graphs | Separate synthetic ER graphs in `benchmarks/run_phase3_ablation.py` (`results/phase3_ablation.csv`) |
| Time limits | Original per-round `time_limit` with **500 ms** safety margin |
| Seed (primary) | 42 |
| Scoring | Official `CliqueScoreCalculator`; **independent** counterfactual pool per solver (historical miners + that solver only) |
| Method F | Reused Phase-2 `anytime_triangle_guided_responses.jsonl` for seed 42 |
| Miner / chain | **Not** launched; local only; pure Python |

Artifacts:

- `results/phase3_*_responses.jsonl`
- `results/phase3_round_comparison.csv` / `.json`
- `results/phase3_rank_summary.json`
- `results/phase3_time_to_best.jsonl`
- `results/phase3_diversity_analysis.csv`
- `results/phase3_ablation.csv`
- `results/phase3_profiling.json`

---

## 3. Mean clique sizes and gaps

| Solver | Mean size | Mean gap vs hist best |
|---|---:|---:|
| triangle_guided | 36.40 | 0.80 |
| bls_adaptive | 36.30 | 0.90 |
| pls_penalty | 35.70 | 1.50 |
| ikls_variable_depth | 36.50 | 0.70 |
| pair_anchor | 36.65 | 0.55 |
| **adaptive_portfolio** | **36.75** | **0.45** |

No method exceeded the historical best on any round (`hist_best_exceed = 0` for all). Portfolio tied historical best on **15/20** rounds (F: 13/20).

---

## 4. Reward and rank percentiles

| Solver | Mean reward | Mean diversity | Mean rank | Mean percentile | Top-1 | Top-3 |
|---|---:|---:|---:|---:|---:|---:|
| triangle_guided | 2.136 | 0.713 | 41.05 | 25.3% | 3 | 3 |
| bls_adaptive | 2.066 | 0.867 | 37.90 | 29.3% | 4 | 4 |
| pls_penalty | 1.946 | 0.988 | 40.90 | 26.2% | 3 | 3 |
| ikls_variable_depth | 2.188 | 0.771 | 38.95 | 33.0% | 5 | 5 |
| pair_anchor | 2.159 | 0.729 | 39.25 | 29.3% | 3 | 4 |
| **adaptive_portfolio** | **2.268** | 0.729 | **35.40** | **38.5%** | **5** | **6** |

### Diversity tradeoff (explicit)

- **PLS** has the highest mean diversity (~0.99) because it often returns **smaller / unique** cliques — reward still suffers from weak optimality.
- **BLS** improves diversity vs F but loses size on several ~300-node ties → worse mean gap/reward than F.
- **Portfolio / pair / IKLS** improve size **and** sometimes land on a **different** best-sized clique than the crowded historical mode (example: `fc92cd37` — F diversity 0.33 / reward 2.03 vs portfolio diversity 0.50 / reward 2.20 at the same size 25).
- Lower gap does **not** always imply better rank when many miners share the same clique; portfolio’s rank lift combines fewer gaps **and** occasional structural uniqueness.

Elite pool (`DiverseElitePool`) retains equal-sized structurally diverse maximal cliques (Jaccard overlap). Return policy default: **diverse** among best-sized. Modes implemented: `first`, `random`, `hash`, `diverse`. Post-hoc policy diagnostic: `results/phase3_output_policy.json` (historical answers used **only** after solving for overlap diagnostics — never at solve time).

---

## 5. Performance by graph size

Mean gap by vertex bucket:

| Bucket | F | BLS | PLS | IKLS | PAIR | PORT |
|---|---:|---:|---:|---:|---:|---:|
| ~300 (n=11) | 0.09 | 0.27 | 0.82 | 0.09 | 0.09 | **0.00** |
| ~500 (n=4) | 0.25 | 1.25 | 1.75 | 0.75 | **0.25** | **0.25** |
| ~700 (n=1) | 3.00 | **2.00** | 3.00 | 3.00 | **2.00** | **2.00** |
| ~900 (n=4) | 2.75 | 2.00 | 2.75 | 1.75 | 1.75 | **1.50** |

Portfolio is uniquely strong on ~300 (zero mean gap) and best on ~900.

---

## 6. Hardest-graph improvements (700–900)

Priority UUIDs (reporting only; **not** used to hardcode solutions):

| UUID | n | hist | F | BLS | PLS | IKLS | PAIR | PORT | Winner vs F |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 577e9988 | 897 | 57 | 54 | **55** | 54 | **55** | **55** | **55** | +1 |
| 1231dc5e | 896 | 34 | 33 | 33 | 32 | **34** | 33 | **34** | +1 (tie hist) |
| 1db8cfb3 | 897 | 44 | 41 | 41 | 41 | **42** | **42** | **42** | +1 |
| 4c69bfb1 | 700 | 48 | 45 | **46** | 45 | 45 | **46** | **46** | +1 |
| 9bd55ea0 | 895 | 45 | 41 | **43** | 42 | 42 | **43** | **43** | +2 |

Hard-set mean gap: F **2.80** → portfolio **1.60**.

Mechanisms that helped:

- **Pair anchoring** repeatedly found +1/+2 on large graphs via common-neighborhood starts.
- **IKLS variable-depth** closed `1231dc5e` to historical best (34) and improved `1db8cfb3`.
- **BLS adaptive perturbation** helped `577e9988` / `4c69bfb1` / `9bd55ea0` vs F, but was weaker on mid-size ties.
- **PLS plateau/penalty alone** did **not** beat F on the hard set (mean gap 2.80, same as F).
- **Portfolio** matched the best of the above on every hard round.

---

## 7. Round-by-round table (all 20)

Sizes: hist | F | BLS | PLS | IKLS | PAIR | PORT

| UUID | n | tl | hist | F | BLS | PLS | IKLS | PAIR | PORT | F gap | PORT gap | PORT reward | PORT %ile |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fc92cd37 | 297 | 15 | 25 | 25 | 24 | 24 | 25 | 25 | 25 | 0 | 0 | 2.200 | 96.9 |
| 53839380 | 292 | 15 | 50 | 50 | 50 | 50 | 50 | 50 | 50 | 0 | 0 | 2.700 | 100.0 |
| 2c36dae9 | 297 | 15 | 32 | 32 | 32 | 31 | 32 | 32 | 32 | 0 | 0 | 2.200 | 79.3 |
| f12351e7 | 298 | 30 | 66 | 66 | 66 | 65 | 66 | 66 | 66 | 0 | 0 | 2.700 | 100.0 |
| 1a5fcb5c | 299 | 15 | 28 | 28 | 28 | 28 | 28 | 28 | 28 | 0 | 0 | 2.200 | 4.9 |
| 188a4272 | 292 | 10 | 23 | 22 | 22 | 21 | 23 | 23 | 23 | 1 | 0 | 2.200 | 6.1 |
| fe10c0b3 | 299 | 15 | 23 | 23 | 23 | 23 | 23 | 23 | 23 | 0 | 0 | 2.450 | 16.0 |
| 42c827b2 | 294 | 10 | 22 | 22 | 22 | 21 | 22 | 22 | 22 | 0 | 0 | 2.200 | 4.4 |
| 7a5ba71a | 292 | 30 | 69 | 69 | 68 | 68 | 69 | 68 | 69 | 0 | 0 | 2.700 | 100.0 |
| b389bbe3 | 297 | 10 | 30 | 30 | 30 | 29 | 30 | 30 | 30 | 0 | 0 | 2.033 | 3.3 |
| 1987b6bb | 497 | 7.5 | 25 | 25 | 24 | 24 | 24 | 24 | 24 | 0 | 1 | 2.733 | 100.0 |
| 22bc813e | 497 | 6 | 37 | 36 | 36 | 35 | 36 | 37 | 37 | 1 | 0 | 2.300 | 11.9 |
| 9645a4e8 | 493 | 15 | 29 | 29 | 28 | 28 | 29 | 29 | 29 | 0 | 0 | 2.300 | 17.1 |
| 577e9988 | 897 | 30 | 57 | 54 | 55 | 54 | 55 | 55 | 55 | 3 | 2 | 1.760 | 0.0 |
| 1231dc5e | 896 | 10 | 34 | 33 | 33 | 32 | 34 | 33 | 34 | 1 | 0 | 3.000 | 100.0 |
| 1db8cfb3 | 897 | 30 | 44 | 41 | 41 | 41 | 42 | 42 | 42 | 3 | 2 | 1.772 | 4.8 |
| 4c69bfb1 | 700 | 30 | 48 | 45 | 46 | 45 | 45 | 46 | 46 | 3 | 2 | 1.687 | 0.0 |
| 9bd55ea0 | 895 | 15 | 45 | 41 | 43 | 42 | 42 | 43 | 43 | 4 | 2 | 1.734 | 0.0 |
| 07965b58 | 495 | 7.5 | 27 | 27 | 25 | 24 | 26 | 27 | 27 | 0 | 0 | 2.300 | 10.4 |
| 225ce3c0 | 299 | 6 | 30 | 30 | 30 | 29 | 29 | 30 | 30 | 0 | 0 | 2.200 | 14.5 |

Notable regression: on `1987b6bb`, portfolio/pair/ikls/bls/pls all miss F’s size-25 tie (portfolio gap 1). Portfolio still wins overall.

---

## 8. Search-activity diagnostics (seed 42 means)

| Solver | Plateau moves | Useful plateau | Perturbations | VD improvements | Pair starts | Time-to-best (ms) |
|---|---:|---:|---:|---:|---:|---:|
| triangle_guided | — | — | — | — | — | 5333 |
| bls_adaptive | 53148 | 87 | 60 | 0 | 0 | 3633 |
| pls_penalty | 9164 | 19 | 0 | 0 | 0 | 4122 |
| ikls_variable_depth | 49854 | 362 | 920 | **281** | 0 | **1984** |
| pair_anchor | 33621 | **1552** | 0 | 0 | **2259** | 3589 |
| adaptive_portfolio | 38997 | 506 | 240 | 69 | 572 | 6235 |

IKLS finds improving variable-depth sequences earlier (lowest mean time-to-best). Portfolio pays a time-to-best cost for strategy switching but ends with the best final sizes.

---

## 9. Ablations (synthetic development graphs)

Source: `results/phase3_ablation.csv` (ER n∈{100,140,180}, timeout 1.5s, seed 42). **Not** the historical 20.

Measured directional evidence (small-n, short timeout):

| Comparison | Observation |
|---|---|
| BLS full vs fixed L=2 | On n=100, adaptive L found size **8** vs fixed-L **7**; on larger graphs both tied |
| PLS with vs without penalty phase | Mixed; removing penalty phase sometimes matched or beat full PLS on these ER graphs — **does not** justify claiming penalties help on SN83 historical graphs (standalone PLS lost there) |
| IKLS full vs shallow depth | Same sizes on these ER instances; VD counters still high on both |
| Pair full vs few pairs | Same sizes; both effective |

Interpretation: ablations support keeping **adaptive L** in BLS; they do **not** overturn the historical ranking that **PLS alone underperforms F**.

---

## 10. Profiling

Source: `results/phase3_profiling.json` (8s budgets on one ~300 and one ~900 graph).

- Dominant cost: local move loops inside each solver (`solve_bls` / `solve_pls` / …).
- Non-trivial overhead: `DiverseElitePool._prune` / overlap maintenance (≈1.3s of ~7.5s in one BLS profile) — candidate for future optimization without changing search semantics.
- BLS example extras (@8s, n=297): ~22k plateau moves, ~23 perturbations, avg L≈5.9, time-to-best ≈3.0s.
- Pair prep time is separately timed when pair scoring runs.

---

## 11. Parameter sensitivity (experimental defaults)

| Parameter | Default | Notes |
|---|---|---|
| BLS L range | 2–8 | Adaptive; fixed L=2 weaker on one ablation graph |
| PLS phase steps | 50 / 50 / 100 | Configurable; historical PLS still trailed F |
| IKLS depth limit | 12 | Bounded; avoid brute-force k-exchanges |
| Pair top-k / sample | 64 / 4000 | Static counts cached when justified |
| Portfolio fractions | 0.25×4 | Equal split; later adaptation possible via improvement rates |
| Safety margin | 500 ms | Unchanged vs Phase 2 |

---

## 12. Multi-seed robustness (123, 2026)

Primary tables above are **seed 42 only**. Aggregate robustness for the three strongest methods (`results/phase3_multiseed_summary.json`):

| Solver | Seed | Mean gap | Mean reward | Mean %ile | Hist ties | Valid | Deadline viol. |
|---|---:|---:|---:|---:|---:|---:|---:|
| adaptive_portfolio | 42 | **0.45** | **2.268** | **38.5** | 15 | 100% | 0% |
| adaptive_portfolio | 123 | 0.80 | 2.164 | 34.4 | 12 | 100% | 0% |
| adaptive_portfolio | 2026 | 0.55 | 2.152 | 27.1 | 14 | 100% | 0% |
| pair_anchor | 42 | 0.55 | 2.159 | 29.3 | 13 | 100% | 0% |
| pair_anchor | 123 | **0.45** | 2.162 | 27.7 | 14 | 100% | 0% |
| pair_anchor | 2026 | 0.65 | 2.139 | 25.2 | 11 | 100% | 0% |
| ikls_variable_depth | 42 | 0.70 | 2.188 | 33.0 | 12 | 100% | 0% |
| ikls_variable_depth | 123 | 0.60 | **2.214** | 34.8 | 12 | 100% | 0% |
| ikls_variable_depth | 2026 | 0.65 | 2.187 | 32.1 | 13 | 100% | 0% |

Notes:

- Across seeds, mean per-UUID size std ≈ 0.14–0.21 vertices — modest.
- Portfolio’s best seed is 42; seed 123 matches F’s gap (0.80) but still beats F on percentile (34.4% vs 25.3%).
- `pair_anchor` seed 123 matches portfolio’s best gap (0.45); IKLS is the most reward-stable across seeds.
- Validity 100% and hard deadline violations 0% on all listed seeds.
- Seed-42 primary artifacts: `results/phase3_seed42_backup/` (and restored live `results/phase3_*` scoring files).

---

## 13. Reproduction commands

```bash
cd /home/CliqueAI/sn83_clique_lab

# Correctness
PYTHONPATH=.:.deps python3 -m pytest tests/test_competitive_search.py -q

# Historical Phase-3 benchmark (reuse Phase-2 F)
PYTHONPATH=.:.deps python3 benchmarks/run_phase3_historical.py --reuse-f --seed 42

# Official counterfactual scoring / ranks
PYTHONPATH=.:.deps python3 benchmarks/score_phase3.py

# Synthetic ablations
PYTHONPATH=.:.deps python3 benchmarks/run_phase3_ablation.py --timeout 1.5

# Profiling
PYTHONPATH=.:.deps python3 benchmarks/run_phase3_profiling.py
```

Do **not** launch a Bittensor miner. Do **not** use C++.

---

## 14. Recommendation for the next SN83 solver

1. **Ship `adaptive_portfolio` as the primary anytime solver** under the existing 500 ms safety margin.
2. Keep **`pair_anchor` and `ikls_variable_depth`** as the high-value components; they drive hard-graph gains.
3. Retain **`triangle_guided`** as a tested fallback (still excellent on many ~300-node rounds; uniquely tied `1987b6bb` at 25).
4. **Do not** use standalone `pls_penalty` as the miner default (highest diversity, worst gap).
5. Next research (optional): reduce elite-prune overhead; allocate portfolio time by online improvement rate; obtain a **fresh** held-out set of 20 real challenges after locking parameters.

### Measured winner

**`adaptive_portfolio`** — mean gap **0.45**, mean reward **2.268**, mean rank percentile **38.5%**, hist ties **15/20**, hard mean gap **1.60**, validity **100%**, hard deadline violations **0**.
