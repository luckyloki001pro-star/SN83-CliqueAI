# SN83 Phase 5C — Adaptive Dual-Solver Portfolio (R-EVO + NuMVC)

Generated: 2026-11-19 (local)  
Primary seed: **42**  
Controls (unchanged): **`revo_no_model`**, **`numvc_complement`**  
Resumption mode: **restart-based slices** (true pause/resume not claimed)

---

## 1. Executive Summary

**On primary seed 42, yes — a fixed 50/50 R-EVO→NuMVC portfolio beat full-budget R-EVO under one shared deadline** and met the conditional Phase 5C targets:

| Metric (seed 42) | Full R-EVO | `revo_50_numvc_50` | Target |
|---|---:|---:|---|
| mean_gap | 0.30 | **0.25** | ≤ 0.25 |
| mean_reward | 2.355 | **2.416** | > 2.355 |
| hist_best_ties | 16/20 | **17/20** | ≥ 17/20 |
| mean_percentile | 46.2% | **51.2%** | — |
| wins / ties / losses vs R-EVO | — | **1 / 19 / 0** | no regressions |
| validity | 100% | **100%** | 100% |
| deadline violations | 0% | **0%** | 0% |

The seed-42 win is **`577e9988`**: NuMVC half-budget found the verified **57**-clique (R-EVO 56; Jaccard ≈ **0.037**). The other 19 sizes matched full R-EVO, including **`1231dc5e` = 34**.

Multi-seed (42 / 123 / 2026): mean size delta vs paired R-EVO is **+0.05 on every seed**, but **official reward is not monotone** (seed 123: reward −0.027 with 2 size regressions). The hist-57 capture did not repeat on 123/2026.

Short NuMVC probes and 90/10–80/20 splits **did not** capture the 57 on seed 42. Stagnation adaptive scheduling hurt reward/ties.

### Verdict

```
adopt_fixed_dual_portfolio
```

Recommended policy among tested schedules: **`revo_50_numvc_50`** (R-EVO first, then NuMVC; usable-wall fractions; 500 ms safety). Treat multi-seed reward variance as a production risk; keep `revo_no_model` as fallback. Do **not** adopt stagnation/early-probe adaptive policies on current evidence.

---

## 2. Review of Earlier Findings

### Phase 4B — R-EVO reliability

`revo_no_model` on latest20 / seed 42: mean size 36.90, gap 0.30, reward 2.355, ties 16/20. Learned-probability R-EVO did not help.

### Phase 5A — Optimal neighborhood

~1.57M exact neighborhoods → **0** verified improvements. Hard graphs need alternate basins, not deeper local repair of the incumbent.

### Phase 5B — NuMVC complementarity

Solo NuMVC weaker on average (gap 0.50) but found a **structurally distinct 57** on `577e9988` (overlap 4 verts with R-EVO 56). Naive 50/50 kept the 57 but lost a vertex on `1231dc5e` → `research_further`.

Phase 5C asks whether fair shared-time scheduling can keep R-EVO’s reliability **and** NuMVC’s rare win.

---

## 3. Discovery Curves

Pilot: **10 seeds** from `master_seed=20261119`, official per-graph time limits, −500 ms margin. Continuous anytime curves (not one run per checkpoint).

Hard-graph mean best size vs elapsed time:

### `577e9988` (n=897, limit 30 s)

| t | R-EVO mean | NuMVC mean |
|---|---:|---:|
| 0.25 s | 52.90 | 52.00 |
| 1 s | 53.80 | 52.70 |
| 5 s | 54.90 | 53.70 |
| 10 s | 55.10 | 55.40 |
| 15 s | 55.30 | 55.90 |
| 30 s | 55.60 | **56.30** |

- R-EVO finals: {55:4, 56:6}; **never** hit 57 in pilot.
- NuMVC finals: {56:7, 57:3}; P(ttb > 5 s) = **1.0**.
- Expanded NuMVC on this graph: **5/30 seeds (16.7%)** reached 57.
- Times-to-57 (30-seed panel): ≈ **12.2–21.3 s** (discovery events ≈ 10.0–16.4 s).

**Implication:** useful NuMVC time on this graph is on the order of **≥10 s**, not sub-second probes.

### `1db8cfb3` (30 s)

R-EVO mean 42.30 (max 43); NuMVC mean 42.50 (max 43). Both improve late; neither matched hist 44 in the pilot.

### `4c69bfb1` (30 s)

Both mean 46.90; each hit hist 48 once / 10 seeds. Similar curves after ~5 s.

### `9bd55ea0` (15 s)

R-EVO mean 43.10 (max 44); NuMVC mean 42.80 (max 44). R-EVO often finishes improving earlier (P(ttb>5s)=0.30) than NuMVC (1.00).

**Scheduling takeaway from curves:** R-EVO is the safer early/mid performer; NuMVC’s unique value on `577e9988` arrives **late**. Allocations that starve NuMVC below ~10 s on 30 s challenges cannot expect the 57.

---

## 4. Complementarity

| Question | Evidence |
|---|---|
| How often full-budget NuMVC finds 57 on `577e9988`? | **5/30 = 16.7%** (not “reliable”; seed-sensitive) |
| When? | Typically **10–21 s** into search |
| Do short probes find 57? | **No** (0.25–1.0 s early; late 20% ≈ 5.9 s also missed on seed 42) |
| Cross-basin structure? | Hybrid/NuMVC 57 vs R-EVO 56: Jaccard ≈ **0.037** |
| Does NuMVC beat R-EVO elsewhere on seed 42? | Solo: wins on `577e9988` and `9bd55ea0` (+1), losses on several others → net worse |
| Shared-time capture without R-EVO loss? | **`revo_50_numvc_50`**: yes on seed 42 |

NuMVC is a **low-probability, high-value alternate basin**, not a general replacement.

---

## 5. Solver Instrumentation

### Callback interface

Optional `on_incumbent(solver_name, clique_mask, clique_size, elapsed_ms, seed)` on `RevoConfig` / `NuMVCConfig`, fired only on verified output-eligible improvements. Events buffered in memory; JSONL written after the timed run.

### Overhead

On `225ce3c0`, 2.0 s R-EVO, 3×3 replicates: mean wall delta with callbacks ≈ **−0.2 ms** (noise). Callbacks do not materially change throughput. Artifacts: `results/phase5c_callback_overhead.json`, `results/phase5c_discovery_events.jsonl`.

### Timing

`time.perf_counter_ns()`-based elapsed from algorithm init, including NuMVC complement construction inside NuMVC’s budget.

### Reference integrity

`revo_no_model` / `numvc_complement` remain callable unchanged. Portfolio uses wrappers/slices. A temporary NuMVC seed offset (`+1000`) in an early portfolio draft broke seed-42 reproducibility of the 57; **removed** so portfolio NuMVC uses `seed + seed_offset` consistently with solo NuMVC.

---

## 6. Fixed Schedules

All under **one** usable wall budget = `time_limit − 500 ms`. Splits are fractions of that usable wall (setup included). Primary order: **R-EVO first, then NuMVC**.

| Schedule | mean_size | mean_gap | mean_reward | ties | W/T/L vs R-EVO |
|---|---:|---:|---:|---:|---|
| full_revo | 36.90 | 0.30 | 2.355 | 16 | 0/20/0 |
| full_numvc | 36.80 | 0.40 | 2.331 | 15 | 2/15/3 |
| revo_90_numvc_10 | 36.90 | 0.30 | 2.355 | 16 | 0/20/0 |
| revo_80_numvc_20 | 36.90 | 0.30 | 2.355 | 16 | 0/20/0 |
| **revo_50_numvc_50** | **36.95** | **0.25** | **2.416** | **17** | **1/19/0** |

90/10 and 80/20 preserved R-EVO sizes but never received enough NuMVC time for the 57 on seed 42. Full NuMVC recovers 57 but regresses elsewhere.

Order ablation is supported in code (`revo_first=False` / `*_numvc_first` variants). Primary leaderboard used R-EVO-first (fast valid fallback before NuMVC init).

**INFEASIBLE TWO-FULL-RUN ORACLE** was not used as a deployable comparison.

---

## 7. Adaptive Scheduler

Implemented in `clique/adaptive_dual_portfolio.py` (restart-based):

| Policy | Rule (summary) | Seed-42 outcome |
|---|---|---|
| D1 stagnation_trigger | R-EVO chunks; NuMVC probe if no growth | mean gap 0.25 but **reward 2.301**, ties **15**, loss on `1231dc5e` (−1), incidental +2 on `9bd55ea0` from chunked R-EVO |
| D2 early_probe_0.5s / 1.0s | NuMVC ≤0.25·usable then R-EVO | gap 0.35; miss 57; regress `1231dc5e` |
| D3 late_probe (20%) | R-EVO 80% then NuMVC 20% | ties full R-EVO; **no** 57 |

Default “adaptive” alias = early probe — **weaker** than fixed 50/50 on this retrospective set.

---

## 8. Resume and Restart

**True cooperative pause/resume is not implemented.**

`DualPortfolioEngine` runs **restart-based** slices: each slice calls `solve_revo` / `solve_numvc` fresh with a slice deadline. Solver internal state (tabu, NuMVC weights, etc.) is **not** preserved across switches. `resumption_mode = "restart_based"` is recorded in extras. Tests cover incumbent persistence across interruptions, not bit-identical multi-slice trajectories vs continuous runs.

---

## 9. Historical Round-by-Round Results (seed 42)

| UUID8 | N | limit | hist | R-EVO | NuMVC | 50/50 | stag | late | early0.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fc92cd37 | — | — | 25 | 25 | 25 | 25 | 25 | 25 | 25 |
| 53839380 | — | — | 50 | 50 | 50 | 50 | 50 | 50 | 50 |
| 2c36dae9 | — | — | 32 | 32 | 32 | 32 | 32 | 32 | 32 |
| f12351e7 | — | — | 66 | 66 | 66 | 66 | 66 | 66 | 66 |
| 1a5fcb5c | — | — | 28 | 28 | 28 | 28 | 28 | 28 | 28 |
| 188a4272 | — | — | 23 | 23 | 23 | 23 | 23 | 23 | 23 |
| fe10c0b3 | — | — | 23 | 23 | 23 | 23 | 23 | 23 | 23 |
| 42c827b2 | — | — | 22 | 22 | 22 | 22 | 22 | 22 | 22 |
| 7a5ba71a | — | — | 69 | 69 | 69 | 69 | 69 | 69 | 69 |
| b389bbe3 | — | — | 30 | 30 | 30 | 30 | 30 | 30 | 30 |
| 1987b6bb | — | — | 25 | 25 | 24 | 25 | 25 | 25 | 25 |
| 22bc813e | — | — | 37 | 37 | 37 | 37 | 37 | 37 | 37 |
| 9645a4e8 | — | — | 29 | 29 | 29 | 29 | 29 | 29 | 29 |
| **577e9988** | 897 | 30 | **57** | 56 | **57** | **57** | 56 | 56 | 56 |
| **1231dc5e** | 896 | 10 | 34 | **34** | 32 | **34** | 33 | 34 | 33 |
| 1db8cfb3 | 897 | 30 | 44 | 43 | 42 | 43 | 43 | 43 | 43 |
| 4c69bfb1 | 700 | 30 | 48 | 47 | 47 | 47 | 47 | 47 | 47 |
| 9bd55ea0 | 895 | 15 | 45 | 42 | 43 | 42 | **44** | 42 | 42 |
| 07965b58 | — | — | 27 | 27 | 27 | 27 | 27 | 27 | 27 |
| 225ce3c0 | — | — | 30 | 30 | 30 | 30 | 30 | 30 | 30 |

CSV: `results/phase5c_round_comparison.csv`.

---

## 10. Hard Graph Analysis

### `577e9988`

- Full R-EVO: 56. Full NuMVC (seed 42): **57** at ≈9.8–11.1 s discovery.
- `revo_50_numvc_50`: R-EVO half → 56; NuMVC half → **57**; incumbent source `numvc_complement`; discovery ≈24.5 s wall (after R-EVO slice).
- Short/late probes: NuMVC best 52–54; miss 57.
- 30-seed NuMVC: success_count=**5**, trials=**30** — real, not reliably repeatable every seed.

### `1db8cfb3`

All practical schedules tied R-EVO at 43; hist 44 remains open. NuMVC solo 42 on seed 42.

### `4c69bfb1`

Tied at 47 across portfolios; hist 48 rare in discovery pilot (1/10 each solver).

### `9bd55ea0`

Full NuMVC 43 > R-EVO 42 on seed 42, but 50/50 kept R-EVO’s 42 (NuMVC half insufficient / unlucky). Stagnation’s 44 came from **chunked R-EVO restarts**, not NuMVC — and that policy is unsafe elsewhere.

### `1231dc5e` (regression sentinel)

50/50 and late_probe preserved **34**. Early probe and stagnation dropped to **33**. This is why adaptive ≠ automatic upgrade.

---

## 11. Reward and Rank

Official `CliqueScoreCalculator` counterfactual scoring (append one candidate to historical miner pool; never multi-strategy same pool):

| Solver | mean_reward | mean_percentile | hist ties |
|---|---:|---:|---:|
| full_revo | 2.355 | 46.2% | 16 |
| **revo_50_numvc_50** | **2.416** | **51.2%** | **17** |
| late_probe | 2.355 | 46.2% | 16 |
| stagnation_trigger | 2.301 | 41.9% | 15 |
| full_numvc | 2.331 | 42.2% | 15 |
| early_probe_0.5s | 2.282 | 41.5% | 15 |

Size and reward agree on the leader: fixed 50/50. Stagnation’s better hard-graph mean gap does **not** translate to reward.

---

## 12. Multi-Seed Robustness

Artifacts: `results/phase5c_*_responses_multiseed.jsonl`, `results/phase5c_multiseed_robustness.json`.  
Seeds: **42, 123, 2026** × 20 graphs for `full_revo` and `revo_50_numvc_50` (60 pairs each).

| Seed | mean_size hyb / revo | mean_gap hyb | Δsize | W/T/L | mean_reward hyb / revo | Δreward |
|---:|---:|---:|---:|---|---:|---:|
| 42 | 36.95 / 36.90 | 0.25 | +0.05 | 1/19/0 | 2.416 / 2.355 | **+0.061** |
| 123 | 36.85 / 36.80 | 0.35 | +0.05 | 3/15/2 | 2.234 / 2.261 | **−0.027** |
| 2026 | 36.85 / 36.80 | 0.35 | +0.05 | 1/19/0 | 2.249 / 2.195 | **+0.053** |

Across 60 graph×seed pairs: P(improve)=**8.3%**, P(regress)=**3.3%**, mean Δsize=**+0.05**.

Improvements (NuMVC source unless noted): `577e9988@42` (+1→57), `577e9988@123` (+1→56), `4c69bfb1@123`, `4c69bfb1@2026`, `188a4272@123`.  
Regressions (seed 123 only): `9bd55ea0` (−1), `22bc813e` (−1).

Hard-graph snapshot:

| Graph | 42 revo/hyb | 123 revo/hyb | 2026 revo/hyb |
|---|---|---|---|
| 577e9988 | 56 / **57** | 55 / **56** | 56 / 56 |
| 1231dc5e | 34 / 34 | 33 / 33 | 33 / 33 |
| 4c69bfb1 | 47 / 47 | 46 / **47** | 46 / **47** |
| 9bd55ea0 | 42 / 42 | **44** / 43 | 43 / 43 |

Discovery panel: NuMVC full-budget 57 on `577e9988` in **5/30** seeds (~16.7%); times ≈10–21 s. Seed-42’s hist-57 under 50/50 is real but not every-seed.

Fresh unseen validator batch: **not available** here — latest20 is retrospective, not untouched holdout.

---

## 13. Profiling

Separate from timed benches (`benchmarks/profile_phase5c.py` → `results/phase5c_profiling.json`).

On `577e9988` early-probe profile (~2.8 s wall): dominant costs are R-EVO `step` / `is_clique` / `has_edge`, then NuMVC slice, then **complement construction (~132 ms)**. Scheduler wrapper overhead is negligible vs search. Restart-based switching re-pays init (including complement) per NuMVC slice — acceptable for one switch in fixed 50/50; harmful if switching excessively (D1 multi-probe).

---

## 14. Ablations

| Ablation | Result |
|---|---|
| A Allocation | Only **50/50** beat R-EVO; 90/10–80/20 tied; 0/100 worse |
| B Order | Primary = R-EVO first (fallback safety); NuMVC-first supported in API |
| C Early probe | 0.25–1.0 s insufficient for 57; slight R-EVO starvation risk |
| D Stagnation | Disabled better for reward; 0.5–2 s triggers not adopted |
| E Resume vs restart | Restart only; resume not validated |
| F NuMVC preprocess | Counted inside NuMVC budget; no UUID cache |
| G Diversity pool | Elite pool retained equal-size distinct cliques; primary metric = size |
| H Adaptive vs fixed | **Fixed 50/50 > adaptive policies** on seed-42 reward/gap/ties |

---

## 15. Risks and Limitations

1. **Seed dependence** of the NuMVC 57 (~17% full-budget).
2. **Retrospective tuning** on heavily studied latest20 — not independent validation.
3. **Restart overhead** if more switches are added.
4. **Short challenges** (e.g. 10 s): 50% NuMVC may be tight; seed-42 survived `1231dc5e`, but risk remains.
5. **Historical collision / diversity** not optimized; reward gain here is primarily from +1 size on `577e9988`.
6. Missing exhaustive 70/30 and 60/40 full-20 seed-42 tables in artifacts (API supports them; Stage A focused on 90/10, 80/20, 50/50).
7. No fresh online challenges in this environment.

---

## 16. Recommendation

```
adopt_fixed_dual_portfolio
```

**Concrete policy:** `revo_50_numvc_50` — R-EVO for 50% of usable wall, then NuMVC for the remainder; shared verified incumbent; independent search states; 500 ms response safety margin.

**Why this over pure R-EVO?** It is the only tested single-deadline schedule that captured NuMVC’s complementary basin on seed 42 (gap 0.25, reward 2.416, ties 17/20, zero regressions) while keeping mean Δsize ≥ 0 on seeds 123 and 2026.

**Why not adaptive?** Early/late/stagnation probes either missed the 57 or introduced regressions that lowered official reward on seed 42.

**Caveats (required):** Multi-seed reward is **not** stable (seed 123 reward below R-EVO despite better mean size). The hist-57 event is uncommon (~17% full-budget NuMVC). Deploy with monitoring; fall back to `revo_no_model` if production seeds show frequent size regressions. Graph-aware gating (large usable budget only) remains unvalidated research.

**Not chosen:** `retain_revo_no_model` (forgoes measured complementary wins), `adopt_adaptive_dual_portfolio` (weaker empirically), `retain_numvc_as_optional_probe` (understates that fixed 50/50 already works as a full shared-time policy when seeds align), `research_further` (enough evidence to prefer fixed 50/50 among current options, with eyes open on seed risk).

---

## Artifacts

| Path | Role |
|---|---|
| `clique/portfolio_incumbent.py` | Shared verified incumbent |
| `clique/portfolio_engine.py` | Dual engine, restart slices |
| `clique/portfolio_scheduler.py` | Fixed C0–C6 |
| `clique/adaptive_dual_portfolio.py` | D1–D3 + wiring |
| `benchmarks/run_phase5c_discovery_curves.py` | Anytime curves |
| `benchmarks/run_phase5c_schedules.py` | Schedule benches |
| `benchmarks/analyze_phase5c.py` | Official scoring summary |
| `benchmarks/profile_phase5c.py` | Profiler |
| `tests/test_portfolio_*.py` | Correctness (11 passed) |
| `results/phase5c_*` | Curves, responses, summaries |

### Repro commands

```bash
cd /home/CliqueAI/sn83_clique_lab
export PYTHONPATH="/home/CliqueAI/sn83_clique_lab:/home/CliqueAI/sn83_clique_lab/.deps"

python3 -m pytest tests/test_portfolio_*.py -q
python3 benchmarks/run_phase5c_discovery_curves.py
python3 benchmarks/run_phase5c_schedules.py --solvers full_revo full_numvc revo_90_numvc_10 revo_80_numvc_20 revo_50_numvc_50 early_probe_0.5s late_probe stagnation_trigger --seed 42
python3 benchmarks/analyze_phase5c.py
```
