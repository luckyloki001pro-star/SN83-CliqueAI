# SN83 Phase 4A — Graph Fingerprinting + Spectral / Anchored Recovery

Generated: 2026-11-19 (local)  
Primary seed: **42**  
Reference solver (unchanged): Phase-3 `adaptive_portfolio`

---

## 1. Executive Summary

**Spectral recovery is not competitive with `adaptive_portfolio` on these 20 SN83 graphs.**

| Solver | Mean size | Mean gap | Mean reward | Mean %ile | Hist ties | Hard mean gap | Valid | Deadline viol. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **adaptive_portfolio** | **36.75** | **0.45** | **2.268** | **38.5%** | **15/20** | **1.8** | 100% | 0% |
| spectral_portfolio | 36.70 | 0.50 | 2.216 | 32.2% | 14/20 | 1.8 | 100% | 0% |
| global_spectral_plus_ikls | 36.60 | 0.60 | 2.199 | 35.2% | 13/20 | 2.0 | 100% | 0% |
| anchored_spectral_plus_ikls | 36.55 | 0.65 | 2.197 | 35.2% | 12/20 | 2.0 | 100% | 0% |
| anchored_spectral | 34.95 | 2.25 | 1.741 | 11.0% | 1/20 | 3.6 | 100% | 0% |
| global_spectral | 34.25 | 2.95 | 1.680 | 6.3% | 1/20 | 4.4 | 100% | 0% |

Success targets (gap &lt; 0.45, reward &gt; 2.268, ties &gt; 15/20) were **not met**.

**Recommendation: retain `adaptive_portfolio`. Do not adopt global/anchored spectral or spectral_portfolio as the primary miner solver.**

Negative result is reproducible: fingerprints show ER-like structure with little planted-clique spectral signal; pure spectral search wastes budget; hybrids that add IKLS/portfolio mostly recover Phase-3 quality by falling back to local search, not by spectral ranking.

---

## 2. Graph Fingerprints

Source: `results/phase4a_graph_fingerprints.csv` (solver-free; hist/portfolio sizes attached **report-only**).

| UUID | n | dens | deg_std | tri≈dens | cn_edge | cn_non | ER thr | hist | port | hist−ER |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fc92cd37 | 297 | 0.772 | 7.10 | 0.772 | 178 | 176 | 26 | 25 | 25 | −1 |
| 53839380 | 292 | 0.906 | 5.47 | 0.906 | 237 | 238 | 52 | 50 | 50 | −2 |
| 2c36dae9 | 297 | 0.827 | 6.49 | 0.827 | 202 | 202 | 33 | 32 | 32 | −1 |
| f12351e7 | 298 | 0.940 | 4.09 | 0.940 | 261 | 262 | 72 | 66 | 66 | −6 |
| 1a5fcb5c | 299 | 0.801 | 6.64 | 0.801 | 191 | 191 | 29 | 28 | 28 | −1 |
| 188a4272 | 292 | 0.741 | 7.38 | 0.741 | 160 | 160 | 23 | 23 | 23 | 0 |
| fe10c0b3 | 299 | 0.748 | 6.89 | 0.748 | 166 | 167 | 24 | 23 | 23 | −1 |
| 42c827b2 | 294 | 0.733 | 7.68 | 0.733 | 156 | 157 | 22 | 22 | 22 | 0 |
| 7a5ba71a | 292 | 0.945 | 3.98 | 0.945 | 259 | 259 | 76 | 69 | 69 | −7 |
| b389bbe3 | 297 | 0.815 | 6.13 | 0.815 | 198 | 196 | 31 | 30 | 30 | −1 |
| 1987b6bb | 497 | 0.726 | 9.99 | 0.726 | 258 | 260 | 25 | 25 | 24 | 0 |
| 22bc813e | 497 | 0.831 | 8.42 | 0.831 | 339 | 341 | 38 | 37 | 37 | −1 |
| 9645a4e8 | 493 | 0.774 | 9.54 | 0.774 | 294 | 294 | 29 | 29 | 29 | 0 |
| 577e9988 | 897 | 0.881 | 9.83 | 0.881 | 700 | 695 | 58 | 57 | 55 | −1 |
| 1231dc5e | 896 | 0.786 | 12.40 | 0.786 | 553 | 552 | 35 | 34 | 34 | −1 |
| 1db8cfb3 | 897 | 0.835 | 11.21 | 0.835 | 627 | 623 | 44 | 44 | 42 | 0 |
| 4c69bfb1 | 700 | 0.862 | 8.88 | 0.862 | 515 | 519 | 49 | 48 | 46 | −1 |
| 9bd55ea0 | 895 | 0.838 | 11.51 | 0.838 | 626 | 627 | 45 | 45 | 43 | 0 |
| 07965b58 | 495 | 0.742 | 10.18 | 0.742 | 268 | 271 | 26 | 27 | 27 | +1 |
| 225ce3c0 | 299 | 0.815 | 6.35 | 0.815 | 198 | 197 | 31 | 30 | 30 | −1 |

`ER thr` = largest \(k\) with \(\mathbb{E}[X_k]\ge 1\) under \(G(n,p)\) with \(p=\) observed density (log-space via `lgamma`). This is an **expected-count threshold**, not \(\omega(G)\).

---

## 3. Structural Evidence

These challenges look **close to dense ER**, not classic planted-clique instances:

- Sampled triangle density ≈ edge density.
- Common-neighbor means on edges ≈ non-edges.
- Degree std ≈ binomial ER prediction (`degree_vs_er_z ≈ 0`).
- Historical best sizes sit near the ER expected-count threshold (usually within ±1; very dense rounds fall a few below because the threshold overestimates realizable cliques).

**We do not claim planted cliques.** The remaining portfolio gaps of 1–2 vertices are consistent with hard dense-search noise, not a clear spectral community that pure-Python Lanczos can isolate inside the deadline.

---

## 4. Spectral Implementation

Pure Python (no NumPy/SciPy/C++/Numba):

| Module | Role |
|---|---|
| `clique/graph_fingerprint.py` | Offline structure diagnostics |
| `clique/spectral_rank.py` | Centered \(B=A-p\) matvec; Lanczos + Jacobi tridiagonal eigensolve; power-iteration **control** (largest \(\lvert\lambda\rvert\)) |
| `clique/spectral_clique.py` | Global spectral-seeded exact-intersection construction + purification |
| `clique/anchored_spectral.py` | Pair seeds → common-neighborhood induced \(G'\) → spectral rank inside \(G'\) |
| `clique/spectral_solve.py` | Variants + `spectral_portfolio` time split |

Centered matvec identity used:

\[
(Bx)_i = (Ax)_i - p\Big(\sum_j x_j - x_i\Big)
\]

Rankings: largest / smallest / absolute coordinates + \(\alpha\) spectral + \(\beta\) degree (\(\alpha=0.6,\beta=0.4\) experimental).  
Spectral budget ceiling: `SPECTRAL_MAX_TIME_FRACTION=0.15` (experimental).  
Labeled as **simplified adaptations**, not exact reproductions of arXiv:2210.02121 / planted-clique color-coding algorithms.

---

## 5. Correctness

```
pytest tests/test_graph_fingerprint.py tests/test_spectral_rank.py tests/test_spectral_clique.py
→ 17 passed
```

All historical Phase-4A responses: **100% valid maximal**, **0% hard deadline violations**.

---

## 6. Synthetic Development Results

`results/phase4a_synthetic.json` (timeout 1.5s):

| Graph | global | anchored | A+IKLS | pair_anchor | portfolio |
|---|---:|---:|---:|---:|---:|
| planted K12 in n=80, p=0.12 | 12 (100% planted) | 12 | 12 | 12 | 12 |
| planted K10 in n=100, p=0.15 | 10 | 10 | 10 | 10 | 10 |
| ER negative control | 5 | 5 | 5 | 5 | 5 |
| dense ER | 8 | 8 | 8 | 8 | 8 |

When a planted clique is obvious, **all** methods recover it. Spectral adds no unique advantage versus pair-anchor / portfolio on these toys.

---

## 7. Historical Round-by-Round Sizes

| UUID | n | hist | PORT | Gspec | Aspec | G+IKLS | A+IKLS | SPort |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fc92cd37 | 297 | 25 | 25 | 23 | 23 | 25 | 25 | 25 |
| 53839380 | 292 | 50 | 50 | 50 | 50 | 50 | 50 | 50 |
| 2c36dae9 | 297 | 32 | 32 | 31 | 31 | 32 | 32 | 32 |
| f12351e7 | 298 | 66 | 66 | 61 | 64 | 66 | 66 | 66 |
| 1a5fcb5c | 299 | 28 | 28 | 27 | 27 | 28 | 28 | 28 |
| 188a4272 | 292 | 23 | 23 | 20 | 21 | 23 | 22 | 23 |
| fe10c0b3 | 299 | 23 | 23 | 22 | 21 | 23 | 23 | 23 |
| 42c827b2 | 294 | 22 | 22 | 20 | 21 | 22 | 22 | 22 |
| 7a5ba71a | 292 | 69 | 69 | 65 | 67 | 69 | 69 | 69 |
| b389bbe3 | 297 | 30 | 30 | 28 | 28 | 30 | 30 | 30 |
| 1987b6bb | 497 | 25 | 24 | 22 | 23 | 24 | 24 | 24 |
| 22bc813e | 497 | 37 | 37 | 33 | 34 | 37 | 37 | 37 |
| 9645a4e8 | 493 | 29 | 29 | 26 | 27 | 29 | 29 | 29 |
| 577e9988 | 897 | 57 | 55 | 51 | 54 | 55 | 55 | **56** |
| 1231dc5e | 896 | 34 | 34 | 31 | 31 | 33 | 33 | 33 |
| 1db8cfb3 | 897 | 44 | 42 | 39 | 39 | 42 | 42 | 41 |
| 4c69bfb1 | 700 | 48 | 46 | 44 | 44 | 46 | 46 | 46 |
| 9bd55ea0 | 895 | 45 | 43 | 41 | 41 | 42 | 42 | 43 |
| 07965b58 | 495 | 27 | 27 | 23 | 24 | 27 | 27 | 27 |
| 225ce3c0 | 299 | 30 | 30 | 28 | 29 | 29 | 29 | 30 |

Paired vs portfolio: spectral_portfolio **+1 once** (`577e9988`), **−1 twice** (`1231dc5e`, `1db8cfb3`), else ties → mean Δsize ≈ −0.05.

Exact sizes: `results/phase4a_round_comparison.csv`.

---

## 8. Score and Rank

Official `CliqueScoreCalculator`, independent counterfactual pools.

Winner by (gap, reward, percentile): **`adaptive_portfolio`**.

`spectral_portfolio` is closest hybrid (gap 0.50) but still worse on reward and percentile because splitting the deadline dilutes the Phase-3 search that was already near-optimal on 15/20 rounds.

---

## 9. Hard Graph Analysis

Gap graphs (portfolio gaps of 1–2):

| UUID | hist | PORT | best spectral family | Closed gap? |
|---|---:|---:|---|---|
| 1987b6bb | 25 | 24 | 24 | No (still −1 hist) |
| 577e9988 | 57 | 55 | **56 (spectral_portfolio)** | Partial (+1 vs port; still −1 hist) |
| 1db8cfb3 | 44 | 42 | 42 (G/A+IKLS) | No; Sport regressed to 41 |
| 4c69bfb1 | 48 | 46 | 46 | No |
| 9bd55ea0 | 45 | 43 | 43 (Sport) | No |

One hard-graph size improvement (`577e9988`: 56 vs port 55) did **not** outweigh regressions elsewhere; mean metrics still favor pure portfolio.

---

## 10. Runtime and Overhead

Mean spectral preprocessing (`results/phase4a_profiling.json`):

| Solver | mean spectral_ms | mean size |
|---|---:|---:|
| global_spectral | ~965 | 34.25 |
| anchored_spectral | ~2162 | 34.95 |
| spectral_portfolio | ~2448 | 36.70 |

On large \(n\approx 900\) graphs, pure-Python Lanczos matvecs are costly; the 15% budget often buys rankings that do not beat degree/pair heuristics. IKLS/portfolio phases carry the hybrids.

---

## 11. Ablation

`results/phase4a_ablation.csv`:

1. **Global degree / spectral-only**: weak (gap 2.95 / 2.25).
2. **+ IKLS**: recovers most quality (gap 0.60–0.65) — benefit is local search, not the eigenvector.
3. **Anchored without strong LS**: still weak vs portfolio.
4. **Spectral + portfolio shared deadline**: slightly behind pure portfolio (gap 0.50 vs 0.45).

Failure mode on SN83: **weak graph signal + spectral overhead**, not invalid cliques or missed deadlines.

---

## 12. Recommendation

| Option | Decision |
|---|---|
| retain `adaptive_portfolio` | **Yes — measured winner** |
| add `anchored_spectral` | No |
| add `global_spectral` | No |
| adopt `spectral_portfolio` | No (strictly worse under equal total time) |

Optional future work (only if new graph regimes appear denser/community-structured): accelerate matvecs carefully, or use spectral **only** as a cheap tie-break among equal-sized elite cliques — not as the primary search engine.

---

## Reproduction

```bash
cd /home/CliqueAI/sn83_clique_lab
PYTHONPATH=.:.deps python3 -m pytest tests/test_graph_fingerprint.py tests/test_spectral_rank.py tests/test_spectral_clique.py -q
PYTHONPATH=.:.deps python3 benchmarks/run_phase4a_fingerprints.py
PYTHONPATH=.:.deps python3 benchmarks/run_phase4a_synthetic.py --timeout 1.5
PYTHONPATH=.:.deps python3 benchmarks/run_phase4a.py --reuse-portfolio --seed 42
PYTHONPATH=.:.deps python3 benchmarks/analyze_phase4a.py
```

Artifacts: `results/phase4a_graph_fingerprints.csv`, `phase4a_round_comparison.csv`, `phase4a_rank_summary.json`, `phase4a_spectral_diagnostics.json`, `phase4a_profiling.json`, `phase4a_ablation.csv`, `phase4a_multiseed_summary.json`, `phase4a_synthetic.json`.

---

## Final answer to the research question

**No** — on this retrospective SN83 set, neither global centered spectral ranking nor spectral analysis inside pair common-neighborhoods revealed the missing 1–2 vertices that `adaptive_portfolio` leaves on the hard graphs, and hybrids did not improve mean gap/reward/percentile under a shared deadline.
