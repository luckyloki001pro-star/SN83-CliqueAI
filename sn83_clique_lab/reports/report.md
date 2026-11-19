# SN83 Clique Lab — Detailed Results Report

Generated UTC: `2026-11-18T16:46:35.707623+00:00`

This is the single consolidated report for Phase 1 (baseline/ULM historical eval) and Phase 2 (anytime local search) on the same **20 real** CliqueAI validator challenges.

---

## 1. Executive Summary

| Method | Mean size | Mean gap | Mean reward | Mean diversity | Mean rank | Mean percentile | Top-1 | Top-3 | Hist-best ties | Validity |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A `baseline (BnB)` | 34.30 | 2.90 | 1.7293 | 1.0000 | 50.95 | 11.0% | 1 | 1 | 1 | 100% |
| D `multistart_greedy` | 35.40 | 1.80 | 1.9071 | 0.8875 | 47.20 | 17.7% | 1 | 2 | 5 | 100% |
| E `swap_local_search` | 36.00 | 1.20 | 2.0539 | 0.8125 | 38.05 | 27.6% | 3 | 4 | 9 | 100% |
| F `triangle_guided` | 36.40 | 0.80 | 2.1356 | 0.7125 | 41.05 | 25.3% | 3 | 3 | 13 | 100% |

**Verdict**

- Correctness is solid: **100% valid** maximal cliques, **0** hard deadline violations.
- Competitive quality improved sharply after switching from BnB anytime behavior to local search.
- Gap vs historical best: **2.90 → 0.80** (`baseline` → `triangle_guided`).
- **Recommended method: `triangle_guided` (F)** for clique size / gap / reward / hist-best ties.
- **`swap_local_search` (E)** is close and best on mean rank percentile / top-3.

---

## 2. Data and Evaluation Setup

| Item | Value |
|---|---|
| Challenges | **20** real SN83 rounds |
| Source | `forge GraphQL sampledHistory (toptensor-ai/CliqueAI run 5CJmEokTjtqe4bsXsNfEzTv9bjW26R4A4iYS7hi1nz5p4s83-0.0.17-83)` |
| History file | `datasets/sn83_history/latest20.jsonl` |
| Scoring | Official `CliqueScoreCalculator` semantics |
| Reward | `optimality × (1 + difficulty) + diversity` |
| Evaluation mode | Each method inserted **alone** into the historical miner pool |
| Seed | 42 |
| Safety margin | 500 ms |
| Hardware | Intel i7-7700 @ 3.60GHz, 8 threads, ~16GB, WSL2, Python 3.12.3 |

Score reproduction on historical miner logs was previously verified **20/20** (max abs error 0).

---

## 3. Baseline Diagnosis (Why BnB Was Weak)

| Metric | Value |
|---|---|
| Soft-deadline stop rate | 100% |
| Search incomplete at deadline | 100% |
| Hard deadline violations | 0% |
| Best found in greedy init | 90% of rounds |
| BnB later improved greedy | 10% of rounds |
| Mean time to best | 325.1 ms |

Interpretation: the old “100% timeout” is **cooperative soft-deadline interruption**, not a missed response deadline. Most time was spent in BnB after a greedy incumbent that rarely improved. Phase 2 therefore redirected the budget into multi-start construction and clique exchanges.

---

## 4. Methods Compared

| ID | Solver | Strategy |
|---|---|---|
| A | `baseline` | Bitset branch-and-bound + greedy coloring |
| D | `multistart_greedy` | Randomized multi-start maximal greedy constructions |
| E | `swap_local_search` | D + 1-for-2 / bounded 2-for-3 exchanges + perturbation |
| F | `triangle_guided` | E + triangle/degree-guided candidate scoring |

ULM / selective ULM were retained in the codebase but are not the competitive focus here (they previously tied baseline on size).

---

## 5. Aggregate Score / Rank / Diversity

### 5.1 Summary metrics

| Method | Mean size | Mean gap | Mean reward | Mean diversity | Mean optimality* | Mean rank | Mean % |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 34.30 | 2.90 | 1.7293 | 1.0000 | 0.4103 | 50.95 | 11.0% |
| D | 35.40 | 1.80 | 1.9071 | 0.8875 | 0.5790 | 47.20 | 17.7% |
| E | 36.00 | 1.20 | 2.0539 | 0.8125 | 0.7069 | 38.05 | 27.6% |
| F | 36.40 | 0.80 | 2.1356 | 0.7125 | 0.8116 | 41.05 | 25.3% |

\*Optimality is normalized omega in the counterfactual pool.

### 5.2 What diversity means here

- Diversity = normalized uniqueness among **valid** answers in the pool.
- If your clique is unique → diversity tends to **1.0**.
- If many miners (including you) share the same best clique → diversity falls to `1/count` (then normalized).
- That is why F/E can have **lower mean diversity** than baseline even while winning on size: they more often match the popular historical-best clique.

### 5.3 Ranking convention

- Reward rank **1 = best**.
- Pool = historical miners + this method only.
- Percentile = `100 × (pool − rank) / (pool − 1)` (100% = best).

---

## 6. Round-by-Round Detailed Results

For each challenge: graph size, historical best, then each method’s size / reward / diversity / rank.

### Round 1: `fc92cd37-8229-42c8-9397-eb996f686e6a`

- n = **297**, difficulty = **0.7**, time limit = **15.0s**, historical miners = **64**, hist best size = **25**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 23 | 2 | 1.5830 | 1.0000 | 0.3429 | 65 | 65 | 0.0% | True |
| D `multistart_greedy` | 25 | 0 | 2.0333 | 0.3333 | 1.0000 | 54 | 65 | 17.2% | True |
| E `swap_local_search` | 25 | 0 | 2.0333 | 0.3333 | 1.0000 | 54 | 65 | 17.2% | True |
| F `triangle_guided` | 25 | 0 | 2.0333 | 0.3333 | 1.0000 | 54 | 65 | 17.2% | True |

### Round 2: `53839380-d224-4048-8ecd-8a776a37ada9`

- n = **292**, difficulty = **0.7**, time limit = **15.0s**, historical miners = **90**, hist best size = **50**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 50 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 91 | 100.0% | True |
| D `multistart_greedy` | 49 | 1 | 1.6267 | 1.0000 | 0.3686 | 90 | 91 | 1.1% | True |
| E `swap_local_search` | 50 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 91 | 100.0% | True |
| F `triangle_guided` | 50 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 91 | 100.0% | True |

### Round 3: `2c36dae9-56a6-4d16-85b9-c8e5c26d157e`

- n = **297**, difficulty = **0.7**, time limit = **15.0s**, historical miners = **82**, hist best size = **32**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 31 | 1 | 1.6208 | 1.0000 | 0.3652 | 82 | 83 | 1.2% | True |
| D `multistart_greedy` | 31 | 1 | 1.6208 | 1.0000 | 0.3652 | 82 | 83 | 1.2% | True |
| E `swap_local_search` | 32 | 0 | 2.2000 | 0.5000 | 1.0000 | 18 | 83 | 79.3% | True |
| F `triangle_guided` | 32 | 0 | 2.2000 | 0.5000 | 1.0000 | 18 | 83 | 79.3% | True |

### Round 4: `f12351e7-28ed-4ec9-b8d6-f77dd8317b63`

- n = **298**, difficulty = **0.7**, time limit = **30.0s**, historical miners = **84**, hist best size = **66**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 63 | 3 | 1.6112 | 1.0000 | 0.3595 | 84 | 85 | 1.2% | True |
| D `multistart_greedy` | 65 | 1 | 1.6307 | 1.0000 | 0.3710 | 84 | 85 | 1.2% | True |
| E `swap_local_search` | 66 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 85 | 100.0% | True |
| F `triangle_guided` | 66 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 85 | 100.0% | True |

### Round 5: `1a5fcb5c-480a-4658-bc93-07d1fff4fcce`

- n = **299**, difficulty = **0.7**, time limit = **15.0s**, historical miners = **82**, hist best size = **28**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 27 | 1 | 1.6179 | 1.0000 | 0.3635 | 82 | 83 | 1.2% | True |
| D `multistart_greedy` | 28 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 83 | 100.0% | True |
| E `swap_local_search` | 28 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 83 | 100.0% | True |
| F `triangle_guided` | 28 | 0 | 2.2000 | 0.5000 | 1.0000 | 79 | 83 | 4.9% | True |

### Round 6: `188a4272-d29e-47ee-aa22-e87009e4bc89`

- n = **292**, difficulty = **0.7**, time limit = **10.0s**, historical miners = **82**, hist best size = **23**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 21 | 2 | 1.5761 | 1.0000 | 0.3389 | 83 | 83 | 0.0% | True |
| D `multistart_greedy` | 22 | 1 | 2.6577 | 1.0000 | 0.9751 | 3 | 83 | 97.6% | True |
| E `swap_local_search` | 22 | 1 | 2.6577 | 1.0000 | 0.9751 | 3 | 83 | 97.6% | True |
| F `triangle_guided` | 22 | 1 | 2.1577 | 0.5000 | 0.9751 | 78 | 83 | 6.1% | True |

### Round 7: `fe10c0b3-ca81-4918-af02-cca346b0e75e`

- n = **299**, difficulty = **0.7**, time limit = **15.0s**, historical miners = **75**, hist best size = **23**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 22 | 1 | 1.6059 | 1.0000 | 0.3564 | 76 | 76 | 0.0% | True |
| D `multistart_greedy` | 23 | 0 | 2.4500 | 0.7500 | 1.0000 | 64 | 76 | 16.0% | True |
| E `swap_local_search` | 23 | 0 | 2.4500 | 0.7500 | 1.0000 | 64 | 76 | 16.0% | True |
| F `triangle_guided` | 23 | 0 | 2.4500 | 0.7500 | 1.0000 | 64 | 76 | 16.0% | True |

### Round 8: `42c827b2-c42b-46c0-bdaf-5988db3425f0`

- n = **294**, difficulty = **0.7**, time limit = **10.0s**, historical miners = **91**, hist best size = **22**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 21 | 1 | 2.5877 | 1.0000 | 0.9340 | 5 | 92 | 95.6% | True |
| D `multistart_greedy` | 22 | 0 | 2.0333 | 0.3333 | 1.0000 | 89 | 92 | 3.3% | True |
| E `swap_local_search` | 22 | 0 | 2.0333 | 0.3333 | 1.0000 | 89 | 92 | 3.3% | True |
| F `triangle_guided` | 22 | 0 | 2.2000 | 0.5000 | 1.0000 | 88 | 92 | 4.4% | True |

### Round 9: `7a5ba71a-a6ed-4289-8901-4133622240be`

- n = **292**, difficulty = **0.7**, time limit = **30.0s**, historical miners = **66**, hist best size = **69**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 66 | 3 | 1.6070 | 1.0000 | 0.3571 | 67 | 67 | 0.0% | True |
| D `multistart_greedy` | 66 | 3 | 1.6070 | 1.0000 | 0.3571 | 67 | 67 | 0.0% | True |
| E `swap_local_search` | 68 | 1 | 1.6352 | 1.0000 | 0.3737 | 66 | 67 | 1.5% | True |
| F `triangle_guided` | 69 | 0 | 2.7000 | 1.0000 | 1.0000 | 1 | 67 | 100.0% | True |

### Round 10: `b389bbe3-e958-40e1-9055-698f18da6e23`

- n = **297**, difficulty = **0.7**, time limit = **10.0s**, historical miners = **60**, hist best size = **30**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 28 | 2 | 1.5926 | 1.0000 | 0.3486 | 61 | 61 | 0.0% | True |
| D `multistart_greedy` | 30 | 0 | 2.0333 | 0.3333 | 1.0000 | 59 | 61 | 3.3% | True |
| E `swap_local_search` | 29 | 1 | 1.9348 | 0.5000 | 0.8440 | 60 | 61 | 1.7% | True |
| F `triangle_guided` | 30 | 0 | 2.2000 | 0.5000 | 1.0000 | 56 | 61 | 8.3% | True |

### Round 11: `1987b6bb-9afb-4323-9951-3ca264dd17b5`

- n = **497**, difficulty = **0.8**, time limit = **7.5s**, historical miners = **54**, hist best size = **25**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 22 | 3 | 1.6021 | 1.0000 | 0.3345 | 54 | 55 | 1.9% | True |
| D `multistart_greedy` | 23 | 2 | 1.6315 | 1.0000 | 0.3508 | 54 | 55 | 1.9% | True |
| E `swap_local_search` | 25 | 0 | 2.1333 | 0.3333 | 1.0000 | 52 | 55 | 5.6% | True |
| F `triangle_guided` | 25 | 0 | 2.1333 | 0.3333 | 1.0000 | 52 | 55 | 5.6% | True |

### Round 12: `22bc813e-0c98-4367-8dd9-7fa4d8247b19`

- n = **497**, difficulty = **0.8**, time limit = **6.0s**, historical miners = **59**, hist best size = **37**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 33 | 4 | 1.5977 | 1.0000 | 0.3320 | 60 | 60 | 0.0% | True |
| D `multistart_greedy` | 35 | 2 | 1.6365 | 1.0000 | 0.3536 | 60 | 60 | 0.0% | True |
| E `swap_local_search` | 36 | 1 | 1.6552 | 1.0000 | 0.3640 | 60 | 60 | 0.0% | True |
| F `triangle_guided` | 36 | 1 | 1.6552 | 1.0000 | 0.3640 | 60 | 60 | 0.0% | True |

### Round 13: `9645a4e8-e2a4-4921-8581-e6a3803b4e31`

- n = **493**, difficulty = **0.8**, time limit = **15.0s**, historical miners = **41**, hist best size = **29**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 25 | 4 | 1.5801 | 1.0000 | 0.3223 | 42 | 42 | 0.0% | True |
| D `multistart_greedy` | 28 | 1 | 1.6549 | 1.0000 | 0.3638 | 42 | 42 | 0.0% | True |
| E `swap_local_search` | 28 | 1 | 1.6549 | 1.0000 | 0.3638 | 42 | 42 | 0.0% | True |
| F `triangle_guided` | 29 | 0 | 2.2000 | 0.4000 | 1.0000 | 38 | 42 | 9.8% | True |

### Round 14: `577e9988-d4d1-4546-ac7a-e779b5c9919c`

- n = **897**, difficulty = **1.0**, time limit = **30.0s**, historical miners = **14**, hist best size = **57**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 50 | 7 | 1.6901 | 1.0000 | 0.3451 | 15 | 15 | 0.0% | True |
| D `multistart_greedy` | 53 | 4 | 1.7330 | 1.0000 | 0.3665 | 15 | 15 | 0.0% | True |
| E `swap_local_search` | 53 | 4 | 1.7330 | 1.0000 | 0.3665 | 15 | 15 | 0.0% | True |
| F `triangle_guided` | 54 | 3 | 1.7467 | 1.0000 | 0.3734 | 15 | 15 | 0.0% | True |

### Round 15: `1231dc5e-eab9-42e6-9627-4430480598f3`

- n = **896**, difficulty = **1.0**, time limit = **10.0s**, historical miners = **14**, hist best size = **34**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 30 | 4 | 1.8077 | 1.0000 | 0.4039 | 13 | 15 | 14.3% | True |
| D `multistart_greedy` | 30 | 4 | 1.8077 | 1.0000 | 0.4039 | 13 | 15 | 14.3% | True |
| E `swap_local_search` | 32 | 2 | 1.8548 | 1.0000 | 0.4274 | 13 | 15 | 14.3% | True |
| F `triangle_guided` | 33 | 1 | 1.8771 | 1.0000 | 0.4386 | 13 | 15 | 14.3% | True |

### Round 16: `1db8cfb3-163d-4879-9d28-f9d8b4c1306c`

- n = **897**, difficulty = **1.0**, time limit = **30.0s**, historical miners = **21**, hist best size = **44**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 39 | 5 | 1.7171 | 1.0000 | 0.3586 | 21 | 22 | 4.8% | True |
| D `multistart_greedy` | 40 | 4 | 1.7358 | 1.0000 | 0.3679 | 21 | 22 | 4.8% | True |
| E `swap_local_search` | 41 | 3 | 1.7539 | 1.0000 | 0.3770 | 21 | 22 | 4.8% | True |
| F `triangle_guided` | 41 | 3 | 1.7539 | 1.0000 | 0.3770 | 21 | 22 | 4.8% | True |

### Round 17: `4c69bfb1-dd54-4127-85f8-2349012ddb8e`

- n = **700**, difficulty = **0.9**, time limit = **30.0s**, historical miners = **38**, hist best size = **48**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 44 | 4 | 1.6563 | 1.0000 | 0.3454 | 39 | 39 | 0.0% | True |
| D `multistart_greedy` | 43 | 5 | 1.6403 | 1.0000 | 0.3370 | 39 | 39 | 0.0% | True |
| E `swap_local_search` | 44 | 4 | 1.6563 | 1.0000 | 0.3454 | 39 | 39 | 0.0% | True |
| F `triangle_guided` | 45 | 3 | 1.6720 | 1.0000 | 0.3537 | 39 | 39 | 0.0% | True |

### Round 18: `9bd55ea0-5149-448a-891c-834ebd87efdd`

- n = **895**, difficulty = **1.0**, time limit = **15.0s**, historical miners = **23**, hist best size = **45**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 41 | 4 | 1.6986 | 1.0000 | 0.3493 | 24 | 24 | 0.0% | True |
| D `multistart_greedy` | 40 | 5 | 1.6805 | 1.0000 | 0.3402 | 24 | 24 | 0.0% | True |
| E `swap_local_search` | 40 | 5 | 1.6805 | 1.0000 | 0.3402 | 24 | 24 | 0.0% | True |
| F `triangle_guided` | 41 | 4 | 1.6986 | 1.0000 | 0.3493 | 24 | 24 | 0.0% | True |

### Round 19: `07965b58-2bd0-4337-871d-0e4ce4a60bbb`

- n = **495**, difficulty = **0.8**, time limit = **7.5s**, historical miners = **67**, hist best size = **27**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 23 | 4 | 1.5662 | 1.0000 | 0.3145 | 68 | 68 | 0.0% | True |
| D `multistart_greedy` | 26 | 1 | 2.6175 | 1.0000 | 0.8986 | 6 | 68 | 92.5% | True |
| E `swap_local_search` | 27 | 0 | 2.3000 | 0.5000 | 1.0000 | 61 | 68 | 10.4% | True |
| F `triangle_guided` | 27 | 0 | 2.1333 | 0.3333 | 1.0000 | 62 | 68 | 9.0% | True |

### Round 20: `225ce3c0-3ed0-4980-9ea6-d0ade1cb3671`

- n = **299**, difficulty = **0.7**, time limit = **6.0s**, historical miners = **76**, hist best size = **30**

| Method | Size | Gap | Reward | Diversity | Optimality | Rank | Pool | Percentile | Valid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A `baseline (BnB)` | 27 | 3 | 1.5678 | 1.0000 | 0.3340 | 77 | 77 | 0.0% | True |
| D `multistart_greedy` | 29 | 1 | 1.6124 | 1.0000 | 0.3602 | 77 | 77 | 0.0% | True |
| E `swap_local_search` | 29 | 1 | 1.6124 | 1.0000 | 0.3602 | 77 | 77 | 0.0% | True |
| F `triangle_guided` | 30 | 0 | 2.3000 | 0.6000 | 1.0000 | 57 | 77 | 26.3% | True |

---

## 7. Compact Comparison Table (All Rounds)

| # | UUID | n | Hist | A size | D size | E size | F size | A rank | D rank | E rank | F rank | A div | D div | E div | F div |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `fc92cd37` | 297 | 25 | 23 | 25 | 25 | 25 | 65 | 54 | 54 | 54 | 1.00 | 0.33 | 0.33 | 0.33 |
| 2 | `53839380` | 292 | 50 | 50 | 49 | 50 | 50 | 1 | 90 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 3 | `2c36dae9` | 297 | 32 | 31 | 31 | 32 | 32 | 82 | 82 | 18 | 18 | 1.00 | 1.00 | 0.50 | 0.50 |
| 4 | `f12351e7` | 298 | 66 | 63 | 65 | 66 | 66 | 84 | 84 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 5 | `1a5fcb5c` | 299 | 28 | 27 | 28 | 28 | 28 | 82 | 1 | 1 | 79 | 1.00 | 1.00 | 1.00 | 0.50 |
| 6 | `188a4272` | 292 | 23 | 21 | 22 | 22 | 22 | 83 | 3 | 3 | 78 | 1.00 | 1.00 | 1.00 | 0.50 |
| 7 | `fe10c0b3` | 299 | 23 | 22 | 23 | 23 | 23 | 76 | 64 | 64 | 64 | 1.00 | 0.75 | 0.75 | 0.75 |
| 8 | `42c827b2` | 294 | 22 | 21 | 22 | 22 | 22 | 5 | 89 | 89 | 88 | 1.00 | 0.33 | 0.33 | 0.50 |
| 9 | `7a5ba71a` | 292 | 69 | 66 | 66 | 68 | 69 | 67 | 67 | 66 | 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 10 | `b389bbe3` | 297 | 30 | 28 | 30 | 29 | 30 | 61 | 59 | 60 | 56 | 1.00 | 0.33 | 0.50 | 0.50 |
| 11 | `1987b6bb` | 497 | 25 | 22 | 23 | 25 | 25 | 54 | 54 | 52 | 52 | 1.00 | 1.00 | 0.33 | 0.33 |
| 12 | `22bc813e` | 497 | 37 | 33 | 35 | 36 | 36 | 60 | 60 | 60 | 60 | 1.00 | 1.00 | 1.00 | 1.00 |
| 13 | `9645a4e8` | 493 | 29 | 25 | 28 | 28 | 29 | 42 | 42 | 42 | 38 | 1.00 | 1.00 | 1.00 | 0.40 |
| 14 | `577e9988` | 897 | 57 | 50 | 53 | 53 | 54 | 15 | 15 | 15 | 15 | 1.00 | 1.00 | 1.00 | 1.00 |
| 15 | `1231dc5e` | 896 | 34 | 30 | 30 | 32 | 33 | 13 | 13 | 13 | 13 | 1.00 | 1.00 | 1.00 | 1.00 |
| 16 | `1db8cfb3` | 897 | 44 | 39 | 40 | 41 | 41 | 21 | 21 | 21 | 21 | 1.00 | 1.00 | 1.00 | 1.00 |
| 17 | `4c69bfb1` | 700 | 48 | 44 | 43 | 44 | 45 | 39 | 39 | 39 | 39 | 1.00 | 1.00 | 1.00 | 1.00 |
| 18 | `9bd55ea0` | 895 | 45 | 41 | 40 | 40 | 41 | 24 | 24 | 24 | 24 | 1.00 | 1.00 | 1.00 | 1.00 |
| 19 | `07965b58` | 495 | 27 | 23 | 26 | 27 | 27 | 68 | 6 | 61 | 62 | 1.00 | 1.00 | 0.50 | 0.33 |
| 20 | `225ce3c0` | 299 | 30 | 27 | 29 | 29 | 30 | 77 | 77 | 77 | 57 | 1.00 | 1.00 | 1.00 | 0.60 |

---

## 8. Anytime Discovery Curves

Mean clique size vs elapsed time:

| Time | D multistart | E swap | F triangle |
|---|---:|---:|---:|
| 0.1s | 33.3 | 33.4 | 33.25 |
| 0.5s | 33.95 | 34.4 | 34.8 |
| 1s | 34.2 | 34.85 | 35.15 |
| 2s | 34.45 | 35.25 | 35.35 |
| 3s | 34.65 | 35.35 | 35.6 |
| 5s | 35.0 | 35.6 | 35.8 |
| deadline | 35.4 | 36.0 | 36.4 |

Baseline diagnosis showed essentially flat checkpoints after greedy init (best size already present by ~0.1s, then BnB spends the remaining budget).

---

## 9. Method-by-Method Interpretation

### A — baseline

- Mean size 34.3, gap 2.9, mean diversity 1.0 (usually unique but smaller).
- Often last or near-last on reward rank because optimality is size-driven.
- Strong only when greedy already hits hist-best (e.g. round `53839380`).

### D — multistart_greedy

- +1.1 mean size vs baseline; gap 1.8; hist-best ties 5/20.
- Uses the full deadline for many constructions instead of fruitless proof search.
- Still behind E/F when local exchanges can grow the clique.

### E — swap_local_search

- +1.7 mean size vs baseline; gap 1.2; best mean percentile (27.6%) and top-3 (4).
- 1-for-2 exchanges are the main gain mechanism.
- Diversity falls when the improved clique coincides with a popular miner answer.

### F — triangle_guided

- Best mean size (36.4), best gap (**0.8**), best mean reward (2.136), most hist-best ties (**13/20**).
- Meets the Phase-2 gap target (&lt; 1.0).
- Slightly lower mean percentile than E because matching popular best cliques reduces diversity on some rounds, which can hurt reward rank even at equal size.

---

## 10. Notable Rounds

| Round | Why it matters |
|---|---|
| `53839380` | A/E/F all hit size 50 and rank 1; D missed by 1 and collapsed to near-last |
| `f12351e7` | E/F reach hist-best 66 and rank 1; A/D trail |
| `7a5ba71a` | Only F reaches 69 / rank 1 |
| `1a5fcb5c` | D/E unique best → rank 1; F same size but duplicated → low diversity / poor rank |
| `07965b58` | D near-best unique (rank 6); E/F hit hist-best but shared → weaker rank |
| `577e9988` / `9bd55ea0` | Hard large graphs; all methods still trail hist-best |

---

## 11. Profiling Snapshot

| Method | Mean runtime ms | Mean constructions | Mean local-search ms | Mean 1-for-2 successes | Deadline violations |
|---|---:|---:|---:|---:|---:|
| A | 15602.4 | None | None | None | 0% |
| D | 15602.3 | 7161.0 | 0.0 | 0.0 | 0% |
| E | 15601.7 | 2039.6 | 5732.2 | 2628.7 | 0% |
| F | 15601.9 | 1975.7 | 5529.3 | 2519.4 | 0% |

---

## 12. Final Recommendation

1. **Primary:** `triangle_guided` for SN83-style short deadlines (best size/gap/reward/ties).
2. **Secondary:** `swap_local_search` when optimizing rank percentile / top-3.
3. Keep `baseline` as reference/correctness solver, not as the competitive anytime engine.
4. Do not prioritize more ULM work until anytime search is further saturated on hard n≈900 rounds.

---

## 13. Artifacts

| Path | Contents |
|---|---|
| `reports/report.md` | This consolidated report |
| `reports/sn83_anytime_search_report.md` | Phase-2 narrative report |
| `reports/sn83_latest20_benchmark.md` | Phase-1 historical benchmark |
| `reports/solver_state_report.md` | Pre-Phase-2 state diagnosis |
| `results/anytime_round_comparison.json` | Per-round sizes/rewards/ranks |
| `results/anytime_rank_summary.json` | Aggregate summaries |
| `results/anytime_*_responses.jsonl` | Raw solver outputs |
| `results/baseline_diagnosis.json` | BnB anytime diagnosis |
| `datasets/sn83_history/latest20.jsonl` | The 20 real challenges |

---

## 14. One-Line Result

**On 20 real SN83 challenges, triangle-guided pure-Python local search raised mean clique size from 34.3 to 36.4, cut the historical-best gap from 2.9 to 0.8, and improved mean reward from 1.729 to 2.136, with 100% validity and no missed hard deadlines.**

