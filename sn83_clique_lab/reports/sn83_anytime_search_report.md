# SN83 Anytime Local Search Report (Phase 2)

Generated UTC: `2026-11-18T16:40:00+00:00`  
Branch: `experiment/sn83-anytime-local-search`  
Dataset: `datasets/sn83_history/latest20.jsonl` (20 real validator challenges; unchanged)

---

## 1. Executive Summary

**Yes — pure-Python anytime local search finds larger cliques than the existing BnB baseline under the same SN83 deadlines.**

| Solver | Mean size | Mean gap vs hist best | Mean reward | Mean rank % | Top-1 | Top-3 | Hist-best ties | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A `baseline` | 34.3 | 2.9 | 1.729 | 11.0% | 1 | 1 | 1 | 100% |
| D `multistart_greedy` | 35.4 | 1.8 | 1.907 | 17.7% | 1 | 2 | 5 | 100% |
| E `swap_local_search` | 36.0 | 1.2 | 2.054 | **27.6%** | **3** | **4** | 9 | 100% |
| F `triangle_guided` | **36.4** | **0.8** | **2.136** | 25.3% | 3 | 3 | **13** | 100% |

- Research target **mean gap &lt; 1.0**: **achieved by F (0.8)**.
- No response-deadline violations (0/20 for all methods).
- Validity / maximality: **100%**.
- **Recommended miner candidate: `triangle_guided` (F)** for clique quality; `swap_local_search` (E) is close and slightly better on mean rank percentile.

Final research answer: **multi-start + exchange (+ triangle guidance) improves historical size/reward/rank versus BnB**, typically by **+1 to +3 vertices**, without C++/Numba.

---

## 2. Baseline Diagnosis

Instrumented `baseline` on all 20 historical rounds (`results/baseline_diagnosis.json`).

### Key findings

| Metric | Value |
|---|---|
| Timeout / soft-deadline stop rate | 100% |
| `search_incomplete_at_deadline` | 100% |
| `response_deadline_violation` | **0%** |
| Best incumbent from greedy init | **90%** of rounds |
| BnB later improved greedy | **10%** of rounds |
| Mean time to best | ~325 ms (often &lt; 20 ms) |
| Checkpoint sizes 0.1s→deadline | flat (best found immediately) |

### Timeout interpretation

The previous “100% timeout” means:

- **Normal cooperative exact-search interruption** after the soft deadline (`time_limit − 500 ms`).
- **Not** a missed hard response deadline.
- **Not** worker kill / overrun (`response_deadline_violation = false`).
- Most wall-clock is spent in BnB **trying to prove / expand** after a greedy incumbent that almost never improves.

### ULM note (prior phase)

ULM **was invoked** historically (`ulm_time_ms` and `ulm_prunes` nonzero) but did not change final clique sizes versus baseline. This phase did not further optimize ULM.

### Implication

Spend the deadline on **many constructions + local exchanges**, not on fruitless optimality search.

---

## 3. New Algorithm Implementations

| ID | Name | Idea |
|---|---|---|
| D | `multistart_greedy` | Many seeded randomized greedy maximal constructions; elite pool; RCL / residual / softmax policies |
| E | `swap_local_search` | D + **1-for-2** clique exchanges, bounded **2-for-3**, perturbations |
| F | `triangle_guided` | E + triangle / degree-structure candidate scoring (`α=0.65`, `β=0.35`) |

Shared requirements:

- Python integer bitsets (`adjacency[v]` masks).
- Anytime incumbent + improvement history + checkpoints.
- Soft deadline with `SAFETY_MARGIN_MS = 500`.
- No historical answers used as search hints.

Code: `clique/anytime_search.py`, wired through `clique/solver.py`.

---

## 4. Correctness Tests

```text
tests/test_anytime_search.py  ......  6 passed
tests/test_cliques.py / deadlines     still passing in combined run
```

Covered:

- Greedy maximality + seed determinism
- 1-for-2 validity
- 2-for-3 triangle requirement
- All variants vs exact oracle on small graphs
- Deadline returns valid incumbent
- Elite/seed stability

Known limitation: on huge dense graphs, F uses a **degree-based triangle proxy** (full common-neighbor sampling is too expensive in pure Python for n≈900).

---

## 5. Benchmark Environment

| Item | Value |
|---|---|
| CPU | Intel Core i7-7700 @ 3.60GHz (4c/8t) |
| Memory | ~16 GB |
| OS | Linux WSL2 |
| Python | 3.12.3 |
| Seed (primary) | 42 |
| Safety margin | 500 ms |
| Historical source | Forge GraphQL run `…-0.0.17-83` (previously verified 20/20 score reproduction) |

Prior Phase-1 outputs under `results/baseline_responses.jsonl` etc. were **preserved**; new artifacts use `anytime_*` prefixes.

---

## 6. Round-by-Round Comparison

| Round | n | t_lim | Hist best | A base | D greedy | E swap | F triangle |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `fc92cd37` | 297 | 15 | 25 | 23 | 25 | 25 | 25 |
| `53839380` | 292 | 15 | 50 | 50 | 49 | 50 | 50 |
| `2c36dae9` | 297 | 15 | 32 | 31 | 31 | 32 | 32 |
| `f12351e7` | 298 | 30 | 66 | 63 | 65 | 66 | 66 |
| `1a5fcb5c` | 299 | 15 | 28 | 27 | 28 | 28 | 28 |
| `188a4272` | 292 | 10 | 23 | 21 | 22 | 22 | 22 |
| `fe10c0b3` | 299 | 15 | 23 | 22 | 23 | 23 | 23 |
| `42c827b2` | 294 | 10 | 22 | 21 | 22 | 22 | 22 |
| `7a5ba71a` | 292 | 30 | 69 | 66 | 66 | 68 | 69 |
| `b389bbe3` | 297 | 10 | 30 | 28 | 30 | 29 | 30 |
| `1987b6bb` | 497 | 7.5 | 25 | 22 | 23 | 25 | 25 |
| `22bc813e` | 497 | 6 | 37 | 33 | 35 | 36 | 36 |
| `9645a4e8` | 493 | 15 | 29 | 25 | 28 | 28 | 29 |
| `577e9988` | 897 | 30 | 57 | 50 | 53 | 53 | 54 |
| `1231dc5e` | 896 | 10 | 34 | 30 | 30 | 32 | 33 |
| `1db8cfb3` | 897 | 30 | 44 | 39 | 40 | 41 | 41 |
| `4c69bfb1` | 700 | 30 | 48 | 44 | 43 | 44 | 45 |
| `9bd55ea0` | 895 | 15 | 45 | 41 | 40 | 40 | 41 |
| `07965b58` | 495 | 7.5 | 27 | 23 | 26 | 27 | 27 |
| `225ce3c0` | 299 | 6 | 30 | 27 | 29 | 29 | 30 |

F ties historical best on **13/20** rounds; never exceeds it on this set.

---

## 7. Score and Rank Results

Independent counterfactual pools (each solver inserted alone into the historical miner list; official `CliqueScoreCalculator`).

See §1 table. Additional notes:

- Mean gap path: **2.9 → 1.8 → 1.2 → 0.8** (A→D→E→F).
- Mean reward path: **1.729 → 1.907 → 2.054 → 2.136**.
- E edges F on mean percentile / top-3; F edges E on size, gap, ties, and mean reward.
- All methods: validity 100%, hard-deadline violation 0%.

Artifacts:

- `results/anytime_round_comparison.json`
- `results/anytime_rank_summary.json`

---

## 8. Anytime Improvement Curves

Mean clique size vs elapsed time (D/E/F; from `results/anytime_checkpoint_curves.json`):

| Time | D | E | F |
|---|---:|---:|---:|
| 0.1 s | 33.30 | 33.40 | 33.25 |
| 0.5 s | 33.95 | 34.40 | 34.80 |
| 1 s | 34.20 | 34.85 | 35.15 |
| 2 s | 34.45 | 35.25 | 35.35 |
| 3 s | 34.65 | 35.35 | 35.60 |
| 5 s | 35.00 | 35.60 | 35.80 |
| deadline | 35.40 | 36.00 | 36.40 |

Baseline diagnosis: size is essentially **constant after ~0.1 s** (greedy incumbent), then BnB burns the rest of the budget.

Discovery speed: **F pulls ahead by ~0.5 s** and keeps a lead to the deadline.

---

## 9. Ablation Study

Development graphs only (`results/anytime_parameter_ablation.csv`; not the final-20 set):

- On short ER-like graphs (n=80–120, 2 s), D/E/F configs often tied — little room / weak structure.
- On real SN83 dense graphs, exchanges matter: E/F gain from **1-for-2** heavily (`mean_swap_1for2_success ≈ 2500` for F) and non-trivial **2-for-3** (`≈ 139` successes).
- Triangle prep cost on SN83-scale dense graphs was kept tiny via degree proxy (`triangle_prep ≈ 0.1 ms`).

---

## 10. Performance Bottlenecks

From `results/anytime_profiling.json` (F averages):

| Component | Approx. share |
|---|---|
| Local search (1-for-2 / 2-for-3) | ~5.5 s mean |
| Greedy constructions | ~4.5 s mean |
| Triangle prep | ~0.1 ms (proxy) |
| Soft-deadline stop | always |

Hot loops: bitset residual scoring, 1-for-2 neighbor-pair scan, bounded 2-for-3 triangle scan.  
Pure Python remains the ceiling; no compiled extensions used.

---

## 11. Final Recommendation

**Ship / continue with `triangle_guided` (Method F)** as the primary pure-Python SN83 candidate:

- Best mean size and **gap 0.8 &lt; 1.0 target**
- Best mean reward
- Most historical-best ties (13/20)
- Still zero deadline violations

Keep `swap_local_search` as a strong alternative when optimizing specifically for rank percentile / top-3.

Do **not** spend more effort on ULM for short deadlines until anytime search saturates further.

Baseline BnB remains useful as a correctness/reference solver, not as the competitive anytime engine.

---

## 12. Next Steps

1. Multi-seed robustness on the same 20 (`seeds 42 123 2026`) without retuning on them.
2. Stronger diversification when F still trails hist-best on hard n≈900 rounds (e.g. `577e9988`, `9bd55ea0`).
3. Optional later: compiled bitset kernel **only after** documenting pure-Python saturation (out of scope here).
4. Integrate F behind the existing miner-facing `solve_clique(...)` API for offline packaging (still no live miner launch in this phase).

---

## Reproduction

```bash
cd sn83_clique_lab
export PYTHONPATH=.:.deps
python -m pytest tests/test_anytime_search.py -q
python benchmarks/diagnose_baseline.py
python benchmarks/run_anytime_historical.py --solvers multistart_greedy swap_local_search triangle_guided
python benchmarks/score_anytime.py
python benchmarks/run_anytime_ablation.py
```

### Research question (answered)

**Can pure-Python randomized multi-start / clique-exchange / triangle-guided search find cliques 1–3 vertices larger than BnB within SN83 deadlines and improve reward/rank on the same 20 real graphs?**

**Yes.** Measured mean gains vs baseline: **+1.1 / +1.7 / +2.1** vertices (D/E/F), gap reduced **2.9 → 0.8** (F), reward **1.729 → 2.136** (F).
