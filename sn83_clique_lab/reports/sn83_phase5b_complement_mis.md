# SN83 Phase 5B — Complement MIS / NuMVC Vertex-Cover Search

Generated: 2026-11-19 (local)  
Primary seed: **42**  
Control: **`revo_no_model`** (unchanged)  
Paper: Cai, Su, Luo & Sattar — *NuMVC: An Efficient Local Search Algorithm for Minimum Vertex Cover* (JAIR 2013 / arXiv:1402.0584). **Inspired implementation**, not a line-by-line port of the reference C code.

---

## 1. Executive Summary

**Solo NuMVC does not beat R-EVO on mean gap/reward, but it delivers the Phase 5B research win condition on the critical hard graph.**

On `577e9988` (n=897), **`numvc_complement` found a verified maximal 57-clique** (historical best = 57; R-EVO = 56). The clique is official-validator valid, maximal, and structurally **far** from R-EVO (Jaccard ≈ **0.037**, overlap **4** vertices) and not identical to recorded historical 57-cliques (best Jaccard ≈ 0.12).

Across all 20 rounds, solo NuMVC mean size **36.7** (gap **0.50**) vs R-EVO **36.9** (gap **0.30**) because of regressions on a few other graphs. Diversified NuMVC and pure MIS baselines are weaker still.

**50/50 `numvc_plus_revo`** recovers mean size **36.9** / gap **0.30**, keeps the **57** on `577e9988`, but loses 1 vertex vs full R-EVO on `1231dc5e` (half-budget R-EVO). Mean reward is slightly below full R-EVO (2.335 vs 2.355).

### Verdict

```
research_further
```

Do **not** replace `revo_no_model` with solo NuMVC. Treat complement NuMVC as a **proven alternate basin explorer** that closed the 577e9988 gap once under seed 42. Next step: robust portfolio scheduling (not naive 50/50) so the NuMVC 57 is kept without starving R-EVO on graphs where NuMVC lags.

---

## 2. Research Foundation

Reproduced from NuMVC Algorithm 1:

| Element | Status |
|---|---|
| Greedy cover construction by max dscore | Yes |
| Two-stage exchange (remove then add) | Yes |
| Configuration checking (`confChange`) | Yes |
| Edge weighting +1 on uncovered edges | Yes |
| Forgetting: \(w \leftarrow \lfloor \rho w \rfloor\) when \(\bar w \ge \gamma\) | Yes |
| Defaults \(\gamma = 0.5\|V\|\), \(\rho = 0.3\) | Yes (paper §6) |
| Age tie-breaks (oldest) | Yes |
| BMS / restarts | B2 only (`numvc_diversified`) |

Deviations / notes:

- Runs on the **complement** of the SN83 graph (paper often tests MVC on complements of DIMACS clique graphs — same duality).
- Pure Python bitsets + edge-ID tables; no reference C source copied.
- Anytime conversion: valid cover \(C^\*\) → clique \(S=V\setminus C^\*\) → greedy maximal extension in \(G\).
- Does **not** initialize from R-EVO.

---

## 3. Mathematical Transformation

For \(G=(V,E)\) and complement \(H=\overline{G}\):

\[
\omega(G)=\alpha(H)=n-\tau(H)
\]

where \(\omega\) = max clique, \(\alpha\) = max independent set, \(\tau\) = min vertex cover.

If NuMVC returns a valid cover \(C\) of \(H\) with \(|C|=840\) on \(n=897\):

\[
|S|=897-840=57
\]

and \(S\) is a clique in \(G\). Verified independently for the seed-42 `577e9988` incumbent.

---

## 4. Implementation

| Module | Role |
|---|---|
| `clique/complement_graph.py` | Bitset complement + edge index |
| `clique/numvc_weights.py` | Weights + forgetting |
| `clique/numvc_state.py` | Cover, uncovered set, dscore, CC |
| `clique/numvc.py` | B1/B2 search loop |
| `clique/mis_baseline.py` | `mis_random_restart`, `mis_configuration_search` |
| `clique/numvc_diversity.py` | Elite pool |
| `clique/solver.py` | Wired + optional `numvc_plus_revo` |

Complement of `577e9988`: **47,734** edges, density ≈ **0.119**, build ≈ 30–140 ms.

Throughput (primary): ~**2.3×10⁵** NuMVC steps/round mean.

---

## 5. Correctness

```
tests/test_complement_graph.py
tests/test_vertex_cover.py
tests/test_numvc_dscore.py
tests/test_numvc_confchange.py
tests/test_numvc_search.py
tests/test_numvc_deadline.py
```

**22/22 passed** (complement XOR, incremental dscore = scratch after random moves, CC proposition-style eligibility, deadline fallbacks, tiny-graph searches).

`577e9988` size-57 output: `is_clique` ✓, `is_maximal_clique` ✓, official `CliqueScoreCalculator.is_valid_maximum_clique` ✓.

---

## 6. Runtime and Throughput

| Solver | Mean steps/round | Notes |
|---|---:|---|
| numvc_complement | 227,204 | Full remove scan over cover |
| numvc_diversified | 185,828 | BMS + restarts (weaker quality) |
| mis_random_restart | 23,796 | |
| mis_configuration_search | 14,134 | |

Profiling hotspots (`results/phase5b_profiling.json`): `remove_vertex`, `add_vertex`, `choose_remove_vertex`, complement build, weight increments.

---

## 7. Historical Comparison (seed 42)

| Solver | Mean size | Mean gap | Mean reward | Mean %ile | Hist ties | vs R-EVO +/ = / − |
|---|---:|---:|---:|---:|---:|---|
| **revo_no_model** | **36.90** | **0.30** | **2.355** | **46.2%** | **16/20** | — |
| mis_random_restart | 36.40 | 0.80 | — | — | — | weaker |
| mis_configuration_search | 35.25 | — | — | — | — | weaker |
| numvc_complement | 36.70 | 0.50 | 2.274 | 41.2% | 15/20 | **1 / 16 / 3** |
| numvc_diversified | 35.10 | 2.10 | 2.092 | 34.2% | 9/20 | 0 / 9 / 11 |
| numvc_plus_revo | 36.90 | 0.30 | 2.335 | 46.5% | 16/20 | **1 / 18 / 1** |

Round CSV: `results/phase5b_round_comparison.csv`.

---

## 8. Hard Graphs

| UUID | Hist | R-EVO | MIS-rand | NuMVC | NuMVC-div | Hybrid |
|---|---:|---:|---:|---:|---:|---:|
| **577e9988** | **57** | 56 | 55 | **57** | 55 | **57** |
| 1db8cfb3 | 44 | 43 | 41 | 42 | 36 | 43 |
| 4c69bfb1 | 48 | 47 | 46 | 47 | 43 | 47 |
| 9bd55ea0 | 45 | 42 | 42 | 42 | 36 | 42 |

Hard mean gap: R-EVO **1.5**, NuMVC **1.5**, hybrid **1.25**.

### Multi-seed NuMVC on hard graphs

| UUID | seed 42 | 123 | 2026 |
|---|---:|---:|---:|
| 577e9988 | **57** | 56 | 56 |
| 1db8cfb3 | 42 | 42 | 42 |
| 4c69bfb1 | 47 | 47 | 47 |
| 9bd55ea0 | 42 | 43 | 42 |

The size-57 discovery is **seed-sensitive** (only seed 42 in this trio). Still a real, validated solution for that run.

---

## 9. Structural Difference

`577e9988` NuMVC-57 vs R-EVO-56:

- Jaccard ≈ **0.037** (overlap 4)
- vs historical 57-cliques: best Jaccard ≈ **0.12** (new basin, not a copy of a stored miner answer)

Mean Jaccard(NuMVC, R-EVO) over 20 rounds ≈ **0.40** — often related, but the breakthrough instance is nearly disjoint.

Basin file: `results/phase5b_basin_overlap.csv`.

---

## 10. Reward and Rank

Independent counterfactual scoring (historical miners + one candidate):

- R-EVO remains best on mean reward (**2.355**).
- Hybrid percentile ≈ **46.5%** (slightly above R-EVO’s 46.2%) with slightly lower mean reward (diversity mix on the new 57).
- Solo NuMVC loses mean reward due to size regressions elsewhere despite the 57.

---

## 11. Ablations (synthetic ER n=80, 1.5 s × 3 seeds)

| Config | Mean size |
|---|---:|
| full (weights+forget+CC) | 6.00 |
| no_weights | 5.67 |
| no_forget | 6.00 |
| no_CC | 6.00 |
| BMS-50 | 6.00 |

Weights helped slightly on this toy graph; forgetting/CC/BMS were quality-neutral here. On SN83, **B2 diversified (BMS+restarts) clearly hurt** vs B1 — do not prefer `numvc_diversified`.

File: `results/phase5b_component_ablation.csv`.

---

## 12. Multi-Seed Stability

Hard-graph NuMVC: 57 appears on seed 42 only among {42,123,2026}. Hybrid inherits that win when NuMVC’s half-budget finds it (seed 42). Portfolio robustness needs more seeds / adaptive time split.

---

## 13. Final Verdict

```
research_further
```

| Option | Decision |
|---|---|
| retain_revo_no_model | **Keep as primary** until portfolio is stable |
| use_numvc_complement | No — mean gap/reward regression |
| use_numvc_diversified | No — clearly worse |
| use_numvc_plus_revo | **Promising**, not yet a clean upgrade (one regression; reward ≤ R-EVO) |
| research_further | **Yes** — NuMVC found a true alternate-basin 57 |

### Answers to the central question

> Can complement NuMVC find strong cliques in regions R-EVO misses?

**Yes, on at least one critical instance (`577e9988`), with a validated 57-clique nearly disjoint from R-EVO’s 56.** It does not yet dominate overall; the right productization path is a **shared-incumbent portfolio** with adaptive time allocation, not replacing R-EVO wholesale.

---

## Artifacts

- Code: `clique/complement_graph.py`, `numvc*.py`, `mis_baseline.py`
- Benchmarks: `benchmarks/run_phase5b.py`, `analyze_phase5b.py`, `profile_phase5b.py`
- Results: `results/phase5b_*`
- Tests: 22 passed under `tests/test_*numvc*`, `test_complement_graph.py`, `test_vertex_cover.py`
