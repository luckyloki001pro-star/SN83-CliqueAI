# SN83 Phase 5A — Optimal-Neighborhood Exploration (ONE)

Generated: 2026-11-19 (local)  
Primary seed: **42**  
Control: **`revo_no_model`** (unchanged)  
Inspiration: Borowitz et al., *Optimal Neighborhood Exploration* (arXiv:2407.06912 / ALENEX 2025) — **adapted to static max-clique**, not a reproduction of the independent-set algorithm.

---

## 1. Executive Summary

**ONE did not beat R-EVO on the retrospective 20-round SN83 set.**

All four exact-repair hybrids matched `revo_no_model` clique sizes on every graph under seed 42 (mean size 36.90, mean gap 0.30, 16/20 historical ties). Across ~1.5M bounded exact neighborhood searches, **zero target improvements** (`|Q| > r`) were found. Official counterfactual reward and percentile are therefore identical to R-EVO (mean reward **2.355**, mean percentile **46.2%**).

Hard gaps (577e9988→56, 1db8cfb3→43, 4c69bfb1→47, 9bd55ea0→42) were **not closed**.

### Verdict

```
retain_revo_no_model
```

Do **not** replace the production candidate with ONE repair. Exact local repair is mathematically sound and correctly implemented, but on this workload the R-EVO incumbents already sit in basins where bounded removable sets (`r ∈ {3,4,6,8,10}` and conflict-derived R) almost never contain a larger replacement clique—and the historically better solutions are often **structurally far** from the R-EVO clique (e.g. Jaccard ≈ 0.05 on 577e9988).

---

## 2. Mathematical Explanation

Given incumbent clique \(C\) with \(|C|=K\) and removable set \(R\subset C\) with \(|R|=r\):

\[
F = C\setminus R,\qquad
H = \bigcap_{u\in F} N(u)\setminus F
\]

Any clique \(Q\subseteq H\) yields a valid clique \(C'=F\cup Q\). Improvement requires \(|Q|>r\) (equivalently target \(t=r+1\) for a one-vertex gain).

**Critical distinction:** exhaustive search in \(G[H]\) proves only that neighborhood; it does **not** prove global optimality of \(C\).

Conflict-union shortcut: for outside set \(A\) that is itself a clique,

\[
R(A)=\bigcup_{v\in A}(C\setminus N(v)),\qquad
|A|>|R(A)| \implies (C\setminus R(A))\cup A
\]

is a strictly larger clique.

---

## 3. Implementation

| Module | Role |
|---|---|
| `clique/optimal_neighborhood.py` | Bitset \(F,R,H\); conflict masks; assemble |
| `clique/neighborhood_exact.py` | Target BnB + greedy coloring UB + degree prune |
| `clique/neighborhood_selector.py` | Random / conflict / adaptive-\(r\) scheduling |
| `clique/neighborhood_diversity.py` | Elite pool + equal-size enumeration |
| `clique/one_repair.py` | R-EVO init + bounded repair loop |
| `clique/solver.py` | Wired as `one_*_repair`, `revo_plus_exact_repair` |

Default hybrid budget: **65% R-EVO / 35% repair**, 500 ms safety margin, per-neighborhood slice 2–100 ms. Incumbents are greedily extended to maximality and verified before publish. `revo_no_model` code path is unmodified.

Statuses from exact search: `TARGET_FOUND` | `PROVEN_NO_TARGET_IN_NEIGHBORHOOD` | `TIMEOUT` | `INVALID_INPUT` (timeout never labeled proven).

---

## 4. Correctness

Small-graph suite (brute-force / exhaustive oracles):

```
tests/test_optimal_neighborhood.py
tests/test_neighborhood_exact.py
tests/test_conflict_repair.py
tests/test_neighborhood_deadline.py
```

**16/16 passed**, including:

- \(R\subseteq H\) sanity on cliques  
- Conflict-union improvement construction  
- Target search matches `exact_omega` on random \(n\le 14\)  
- Max search matches exhaustive on random \(n\le 12\)  
- Planted 2-for-3 style repair  
- Artificial short deadlines → valid maximal fallback, no hard violation, no false proofs  

---

## 5. Historical Results (seed 42)

| Solver | Mean size | Mean gap | Mean reward | Mean %ile | Hist ties | vs R-EVO Δsize | Exact +1 | Valid | Deadline viol. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **revo_no_model** | **36.90** | **0.30** | **2.355** | **46.2%** | **16/20** | — | — | 100% | 0% |
| one_random_repair | 36.90 | 0.30 | 2.355 | 46.2% | 16/20 | 0/20 | 0 | 100% | 0% |
| one_conflict_repair | 36.90 | 0.30 | 2.355 | 46.2% | 16/20 | 0/20 | 0 | 100% | 0% |
| one_adaptive_repair | 36.90 | 0.30 | 2.355 | 46.2% | 16/20 | 0/20 | 0 | 100% | 0% |
| one_diverse_repair | 36.90 | 0.30 | 2.355 | 46.2% | 16/20 | 0/20 | 0 | 100% | 0% |

Round table: `results/phase5a_round_comparison.csv`.

Regression control: **0 improvements, 20 ties, 0 regressions** vs R-EVO on primary seed (identical sizes).

---

## 6. Hard-Graph Results

| UUID | \(n\) | Hist best | R-EVO | ONE (all variants) | Gap |
|---|---:|---:|---:|---:|---:|
| 577e9988 | 897 | 57 | 56 | 56 | 1 |
| 1db8cfb3 | 897 | 44 | 43 | 43 | 1 |
| 4c69bfb1 | 700 | 48 | 47 | 47 | 1 |
| 9bd55ea0 | 895 | 45 | 42 | 42 | 3 |

### Why 577e9988 resists local exact repair

Diagnostic (not used inside the solver): best Jaccard between R-EVO’s 56-clique and historical 57-answers ≈ **0.046** (overlap **5** vertices). Reaching that 57 requires removing ~51 clique vertices; the induced \(H\) then has hundreds of candidates and timed out under a 2 s oracle slice. Bounded \(r\le 10\) neighborhoods around the R-EVO incumbent are the wrong basin.

### Multi-seed hard check (42 / 123 / 2026)

| UUID | revo sizes | conflict sizes |
|---|---|---|
| 577e9988 | 56 / 55 / 56 | 56 / 55 / 56 |
| 1db8cfb3 | 43 / 43 / 42 | 43 / 43 / 42 |
| 4c69bfb1 | 47 / 46 / 46 | 47 / 46 / 46 |
| 9bd55ea0 | 42 / **44** / 43 | 42 / **43** / 43 |

On seed 123 / 9bd55ea0, **R-EVO alone found 44** while conflict-hybrid found **43** — a regression from giving R-EVO only ~65% of the deadline. Exact repair did not recover the lost size.

---

## 7. Exact Search Diagnostics

Primary seed totals (all 20 rounds):

| Variant | Neighborhoods attempted | Proven impossible | Timeouts | Target hits |
|---|---:|---:|---:|---:|
| one_random_repair | 967,765 | 967,765 | 0 | **0** |
| one_conflict_repair | 249,346 | 249,346 | 0 | **0** |
| one_adaptive_repair | 102,081 | 102,081 | 0 | **0** |
| one_diverse_repair | 248,318 | 248,238 | 0 | **0** |

Typical feasible random neighborhoods on 577e9988 after a strong incumbent: \(|H|\approx r+1\ldots r+3\) with low density — coloring/size bounds prove \(\omega(H)<r+1\) in sub-millisecond time. Conflict guidance preferentially samples tiny \(r=1,2\) neighborhoods that also prove empty of improving \(Q\).

Files: `results/phase5a_neighborhood_diagnostics.json`.

---

## 8. Time Allocation

Capped 8 s ablation on `fc92cd37` and `577e9988` (`results/phase5a_allocation_ablation.csv`):

| Config | fc92 size | 577e size | Exact +1 |
|---|---:|---:|---:|
| full_revo | 25 | 56 | — |
| 80/20 ONE | 25 | 56 | 0 |
| 80/20 continue-R-EVO | 25 | 56 | — |
| 65/35 ONE | 25 | 56 | 0 |
| 65/35 continue-R-EVO | 25 | 56 | — |
| 50/50 ONE | 25 | 56 | 0 |
| 50/50 continue-R-EVO | 25 | 56 | — |

Spending more wall time on exact repair increased neighborhood attempts but **never** increased clique size versus continuing R-EVO for the same budget.

---

## 9. Conflict-Guided Selection

Conflict guidance explores fewer neighborhoods than random (~12k vs ~48k mean/round) and focuses on small conflict masks, but **neither** produced a verified improvement on this dataset. Random sampling of larger \(r\) also uniformly proved non-improving. Conclusion: **selection policy is not the bottleneck** once R-EVO has reached these incumbents—the improving exchanges are absent from the sampled \(H\) sets (or require \(r\) far beyond practical exact search).

---

## 10. Diversity Results

`one_diverse_repair` mean elite pool size **2.3** (vs 1.0 for other ONE variants). Focused ablation on `fc92cd37`: elite count 3 at best size 25, mean pairwise Jaccard ≈ 0.90 (near-duplicates), methods `{revo, equal_enum}`.

Equal-size enumeration can add alternate maximal cliques of the same size without hurting primary size under seed 42, but **did not improve simulated diversity reward** versus R-EVO (same published clique / uniqueness class in the counterfactual pool). Structural diversity among our own elites does **not** guarantee a better SN83 uniqueness term against the historical miner pool.

---

## 11. Official Reward and Rank

Independent counterfactual scoring (historical miners + one hypothetical response):

- All Phase 5A solvers: mean reward **2.355**, mean percentile **46.2%**, top1 **6/20**, top3 **7/20**  
- Identical to Phase 4B `revo_no_model`  
- Validity 100%, hard deadline violations 0%

Primary success targets vs R-EVO baseline (**gap < 0.30**, **reward > 2.355**, **ties > 16/20**): **not met** (tied, not improved).

---

## 12. Profiling

Separate `cProfile` on 577e9988 / `one_conflict_repair` / 3 s (`results/phase5a_profiling.json`):

Hotspots:

1. R-EVO local search / `is_clique` validation  
2. `conflict_guided_removals` (outside conflict scans)  
3. `build_neighborhood` / bitset list conversion  
4. Exact expansion is **cheap** here because almost all calls prove via size/color before deep recursion (`search_nodes_total` ≪ neighborhoods)

Bottleneck for this experiment is **neighborhood proposal volume**, not Tomita branching depth.

---

## 13. Ablation

| Factor | Finding |
|---|---|
| A Random vs conflict | Neither improves size; conflict is cheaper per proposal |
| B Exact vs continue-R-EVO | Exact adds no size; stealing R-EVO time can regress (multiseed) |
| C \(r=4/6/8\) | All prove empty of improving \(Q\) at scale on these incumbents |
| D Coloring bound | Enables mass proven-impossible (0 timeouts at seed 42) |
| E Slice budget | Neighborhoods finish via proof long before 100 ms |
| F R-EVO fraction | 50–80% ONE allocations match full R-EVO size here but risk regression |
| G Diversity enum | Extra best-sized elites; no reward gain in this pool |

---

## 14. Final Recommendation

```
retain_revo_no_model
```

**Evidence:** zero exact improvements on 20/20 historical graphs; identical reward/rank to R-EVO; multi-seed evidence that reducing R-EVO time for repair can **lose** clique size; hard historical optima often lie in distant vertex sets that bounded ONE exchanges cannot reach.

**Keep ONE code** as a research tool / optional post-processor for future graphs where local \(r\)-exchanges exist, but do **not** promote it over `revo_no_model` for SN83 mining on this evidence.

### Answers to diagnostic questions

1. Best \(r\): none produced improvements.  
2. Conflict vs random: no size difference; conflict fewer attempts.  
3. Larger exact neighborhoods: did not find missed improvements on these incumbents.  
4. Exact vs more R-EVO: exact did not add value; more R-EVO can be better (seed 123 / 9bd55ea0).  
5. Induced \(|H|\): usually tiny (\(\sim r\ldots r+3\)) after strong cliques.  
6. Proven impossible: essentially **all** completed searches.  
7. Cache: helpful; many duplicate fixed-sets.  
8. Equal-sized alternatives: yes, modestly (`diverse` elite ≈ 2–3).  
9. Diversity stealing size: not on seed 42 primary; risk exists via reduced R-EVO budget.  
10. Reward rank: unchanged vs R-EVO.

---

## Artifacts

- Solvers: `clique/one_repair.py`, `clique/neighborhood_*.py`, `clique/optimal_neighborhood.py`  
- Benchmarks: `benchmarks/run_phase5a.py`, `analyze_phase5a.py`, `profile_phase5a.py`  
- Results: `results/phase5a_*.jsonl`, `phase5a_round_comparison.csv`, `phase5a_multiseed_summary.json`, `phase5a_neighborhood_diagnostics.json`, `phase5a_ablation.csv`, `phase5a_allocation_ablation.csv`, `phase5a_profiling.json`  
- Tests: `tests/test_optimal_neighborhood.py`, `test_neighborhood_exact.py`, `test_conflict_repair.py`, `test_neighborhood_deadline.py`
