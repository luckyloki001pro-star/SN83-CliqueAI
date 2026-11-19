# SN83 Local Solver — Detailed State Report

Generated UTC: `2026-11-18T16:00:00+00:00`  
Scope: pure-Python lab solvers (`baseline`, `ulm`, `selective_ulm`) evaluated against the latest **20 real** CliqueAI validator challenges.

---

## 1. Executive verdict

| Question | Answer |
|---|---|
| Is the clique method *broken* (invalid answers)? | **No.** 20/20 answers are valid maximal cliques. |
| Is it *competitive* on live-like rounds? | **Mostly no.** Trails historical best size on 19/20 rounds. |
| Do ULM variants help on this set? | **No measurable gain.** A/B/C identical size, reward, and rank. |
| Root issue | **Speed / search quality under timeout**, not correctness. |

**Recommendation:** keep shipping **baseline (Method A)** for miner work; treat ULM as research-only until it finds larger cliques *within* the deadline.

---

## 2. Data provenance (exact, not synthetic)

| Field | Value |
|---|---|
| Source | Public Forge GraphQL `https://forge.coreweave.com/api/wandb/graphql` |
| Project | `toptensor-ai/CliqueAI` |
| Validator run | `5CJmEokTjtqe4bsXsNfEzTv9bjW26R4A4iYS7hi1nz5p4s83-0.0.17-83` |
| Steps used | 102460–102481 (2 IncompleteRead skips filled by next steps) |
| Records | **20 / 20** complete |
| Graph used | `adjacency_list` (intact) |
| `encoded_matrix` | Present but does **not** round-trip `GraphCodec` (spaces / decode header failure); scoring/solvers did not depend on it |
| Artifacts | `datasets/sn83_history/latest20.jsonl`, `raw/latest20_raw.json` |

Each record includes historical miner responses and scores: `miner_ans`, `miner_uids`, `miner_omega`, `miner_optimality`, `miner_diversity`, `miner_rewards`, etc.

---

## 3. Scoring fidelity

Official `CliqueScoreCalculator` semantics were reproduced locally.

| Check | Result |
|---|---|
| Score reproduction vs logged miner metrics | **20/20 OK** (max abs error **0** on omega / optimality / diversity / rewards) |
| Validity of local answers | **20/20 valid** |
| Reward formula | `reward = optimality × (1 + difficulty) + diversity` |

So rankings below are from the **same** scoring rule the validator uses, after counterfactual insertion of the local answer into that round’s miner pool.

---

## 4. Local solver behavior

### 4.1 Methods compared

| ID | Solver | Role |
|---|---|---|
| A | `baseline` | Bitset BnB + greedy coloring |
| B | `ulm` | A + full unit-weight ULM |
| C | `selective_ulm` | A + selective ULM |

### 4.2 Outcome on latest-20

| Metric | baseline | ulm | selective_ulm |
|---|---:|---:|---:|
| Mean clique size | 34.3 | 34.3 | 34.3 |
| Mean runtime (ms) | 15603 | 15604 | 15603 |
| Validity rate | 1.0 | 1.0 | 1.0 |
| Timeout rate | **1.0** | **1.0** | **1.0** |
| Mean reward | 1.729 | 1.729 | 1.729 |
| Mean reward rank | 50.95 | 50.95 | 50.95 |
| Mean rank percentile | 13.1% | 13.1% | 13.1% |

**A = B = C on every round** (size, reward, rank). ULM did not change the incumbent found before the deadline.

### 4.3 Challenge mix

| Property | Range / values |
|---|---|
| Vertices `n` | 292 – 897 |
| Difficulty | 0.7 (11), 0.8 (4), 0.9 (1), 1.0 (4) |
| Time limit (s) | 6 / 7.5 / 10 / 15 / 30 |
| Historical miners / round | 14 – 91 |

---

## 5. Gap vs historical best clique size

Local size is compared to the best **valid** historical miner clique in that round.

| Gap (hist_best − ours) | Count |
|---:|---:|
| 0 (tie best) | 1 |
| 1 | 4 |
| 2 | 3 |
| 3 | 4 |
| 4 | 6 |
| 5 | 1 |
| 7 | 1 |
| **Mean gap** | **2.9** |
| **Median gap** | **3.0** |
| Exceeded hist best | **0 / 20** |

### By difficulty

| Difficulty | Rounds | Mean `n` | Mean gap | Mean percentile |
|---:|---:|---:|---:|---:|
| 0.7 | 11 | 296 | 1.73 | 19.2% |
| 0.8 | 4 | 496 | 3.75 | 2.3% |
| 0.9 | 1 | 700 | 4.00 | 2.6% |
| 1.0 | 4 | 896 | 5.00 | 10.0% |

Gap **widens on harder / larger** graphs. Soft rounds (diff 0.7, n≈300) are closer; hard rounds (diff 1.0, n≈900) trail more.

---

## 6. Round-by-round ranking (counterfactual)

Pool = historical miners + our answer. **Rank 1 = best reward.**  
(Solvers A/B/C identical — one column.)

| # | UUID | n | pool | our size | hist best | reward rank | percentile | reward |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `fc92cd37` | 297 | 65 | 23 | 25 | 65/65 | 1.5% | 1.5830 |
| 2 | `53839380` | 292 | 91 | 50 | 50 | **1/91** | 100.0% | 2.7000 |
| 3 | `2c36dae9` | 297 | 83 | 31 | 32 | 82/83 | 2.4% | 1.6208 |
| 4 | `f12351e7` | 298 | 85 | 63 | 66 | 84/85 | 2.4% | 1.6112 |
| 5 | `1a5fcb5c` | 299 | 83 | 27 | 28 | 82/83 | 2.4% | 1.6179 |
| 6 | `188a4272` | 292 | 83 | 21 | 23 | 83/83 | 1.2% | 1.5761 |
| 7 | `fe10c0b3` | 299 | 76 | 22 | 23 | 76/76 | 1.3% | 1.6059 |
| 8 | `42c827b2` | 294 | 92 | 21 | 22 | **5/92** | 95.7% | 2.5877 |
| 9 | `7a5ba71a` | 292 | 67 | 66 | 69 | 67/67 | 1.5% | 1.6070 |
| 10 | `b389bbe3` | 297 | 61 | 28 | 30 | 61/61 | 1.6% | 1.5926 |
| 11 | `1987b6bb` | 497 | 55 | 22 | 25 | 54/55 | 3.6% | 1.6021 |
| 12 | `22bc813e` | 497 | 60 | 33 | 37 | 60/60 | 1.7% | 1.5977 |
| 13 | `9645a4e8` | 493 | 42 | 25 | 29 | 42/42 | 2.4% | 1.5801 |
| 14 | `577e9988` | 897 | 15 | 50 | 57 | 15/15 | 6.7% | 1.6901 |
| 15 | `1231dc5e` | 896 | 15 | 30 | 34 | 13/15 | 20.0% | 1.8077 |
| 16 | `1db8cfb3` | 897 | 22 | 39 | 44 | 21/22 | 9.1% | 1.7171 |
| 17 | `4c69bfb1` | 700 | 39 | 44 | 48 | 39/39 | 2.6% | 1.6563 |
| 18 | `9bd55ea0` | 895 | 24 | 41 | 45 | 24/24 | 4.2% | 1.6986 |
| 19 | `07965b58` | 495 | 68 | 23 | 27 | 68/68 | 1.5% | 1.5662 |
| 20 | `225ce3c0` | 299 | 77 | 27 | 30 | 77/77 | 1.3% | 1.5678 |

### Rank summary

| Outcome | Count |
|---|---:|
| Reward rank #1 | 1 |
| Top-5 reward | 2 |
| Exact last place | 12 |
| Near-last (rank ≥ #miners) | 17 |

Strong rounds: `#2` (tied hist best) and `#8` (size only −1, but high optimality/diversity → reward rank 5).  
Weak pattern: most rounds are last or near-last because **size** trails, and SN83 optimality is size-competitive.

---

## 7. Diversity state

Diversity = normalized uniqueness among **valid** answers (`1/count` of identical canonical cliques, then ÷ max).

| Item | Result |
|---|---|
| Historical miner diversity | Varies by round (mean often 0.5–1.0); duplicates are common |
| Our diversity after insert | **1.0 on all 20** (our clique never duplicated a historical answer) |
| Implication | Uniqueness bonus is maxed; **reward still loses on optimality/size** |

So diversity is not the problem. Size/optimality is.

---

## 8. Diagnosis: what is wrong vs what is not

### Not wrong

1. Graph ingest from historical `adjacency_list`.
2. Clique validity / maximality checks.
3. Local score reproduction of validator math.
4. ULM soundness on lab unit tests (separate quick bench).

### Wrong for competition

1. **Always times out** → incumbent is whatever was found before the clock; proof/search unfinished.
2. **Mean −2.9 vertices vs best miners** → enough to collapse reward rank on most rounds.
3. **Pure-Python ULM overhead** does not buy a larger incumbent before deadline (same as earlier quick bench: A/B/C size ties).
4. Gap grows with difficulty / `n` → method scales worse than top miners on hard SN83 graphs.

### Interpretation

This is a **performance / anytime-search** deficit relative to deployed miners, not a logic bug in “finding cliques.”

---

## 9. Relation to earlier lab quick-benchmark

From `reports/benchmark_report.md` (synthetic/local graphs):

- A/B/C already tied on clique size under short deadlines.
- ULM reduced nodes but Python overhead ate the gain.
- Recommendation was already **baseline**.

Latest-20 **confirms** that conclusion on real validator traffic.

---

## 10. What would change the state

Priority order for closing the gap:

1. **Faster incumbent discovery** inside the first 1–3s (better greedy / restart / coloring order / branching).
2. **Use full time limit more effectively** (less overhead per node; optional compiled kernel later — currently disallowed in this lab).
3. Only then revisit ULM if it improves bound *and* finds larger cliques before timeout.
4. Re-run this exact latest-20 harness after each change (`verify_history` → `run_historical` → `recalculate_scores` → `predict_rank`).

---

## 11. Key file index

| Path | Contents |
|---|---|
| `reports/sn83_latest20_benchmark.md` | Full historical benchmark report |
| `reports/benchmark_report.md` | Lab ULM quick-bench |
| `reports/data_access_status.md` | Fetch status |
| `results/round_comparison.json` | Per-round counterfactual metrics |
| `results/miner_ranking_prediction.json` | Aggregate rank prediction |
| `results/historical_score_verification.json` | Score reproduction |
| `datasets/sn83_history/latest20.jsonl` | The 20 real challenges |

---

## 12. One-line state

**Correct but too slow / too weak under SN83 deadlines: valid cliques, full score fidelity, ULM tied with baseline, ~3 vertices behind best miners on average → typically bottom-quartile reward rank.**
