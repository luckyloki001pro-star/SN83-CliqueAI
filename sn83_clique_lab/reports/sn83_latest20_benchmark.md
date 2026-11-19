# SN83 Latest-20 Historical Benchmark Report

Generated UTC: `2026-11-18T15:36:48.497863+00:00`

## A. Historical Data Provenance

- Source project: `toptensor-ai/CliqueAI`
- Access status: **ok**
- Manifest retrieval timestamp: `2026-11-18T15:18:09.645744+00:00`
- Real complete challenges available: **20**
- Requested: 20
- Selected UUIDs:
  - `fc92cd37-8229-42c8-9397-eb996f686e6a`
  - `53839380-d224-4048-8ecd-8a776a37ada9`
  - `2c36dae9-56a6-4d16-85b9-c8e5c26d157e`
  - `f12351e7-28ed-4ec9-b8d6-f77dd8317b63`
  - `1a5fcb5c-480a-4658-bc93-07d1fff4fcce`
  - `188a4272-d29e-47ee-aa22-e87009e4bc89`
  - `fe10c0b3-ca81-4918-af02-cca346b0e75e`
  - `42c827b2-c42b-46c0-bdaf-5988db3425f0`
  - `7a5ba71a-a6ed-4289-8901-4133622240be`
  - `b389bbe3-e958-40e1-9055-698f18da6e23`
  - `1987b6bb-9afb-4323-9951-3ca264dd17b5`
  - `22bc813e-0c98-4367-8dd9-7fa4d8247b19`
  - `9645a4e8-e2a4-4921-8581-e6a3803b4e31`
  - `577e9988-d4d1-4546-ac7a-e779b5c9919c`
  - `1231dc5e-eab9-42e6-9627-4430480598f3`
  - `1db8cfb3-163d-4879-9d28-f9d8b4c1306c`
  - `4c69bfb1-dd54-4127-85f8-2349012ddb8e`
  - `9bd55ea0-5149-448a-891c-834ebd87efdd`
  - `07965b58-2bd0-4337-871d-0e4ce4a60bbb`
  - `225ce3c0-3ed0-4980-9ea6-d0ade1cb3671`
- Timestamp range: `{'min': 1794988833.8089044, 'max': 1794993834.5636976}`

See also `reports/data_access_status.md`.

### Access status excerpt

```
# SN83 Historical Data Access Status

## Retrieval attempt

- UTC time: `2026-11-18T15:17:31+00:00`
- Project: `toptensor-ai/CliqueAI`
- Method: public Forge GraphQL `https://forge.coreweave.com/api/wandb/graphql` → `sampledHistory(specs)` with `minStep`/`maxStep`
- Run: `5CJmEokTjtqe4bsXsNfEzTv9bjW26R4A4iYS7hi1nz5p4s83-0.0.17-83`
- `WANDB_API_KEY` configured: **False** (not required for this public Forge endpoint)
- Access status: **ok**
- Complete records selected: **20** / 20

## Result

**20 real historical challenge records retrieved** (validator steps 102460–102481, two IncompleteRead skips).

Source artifact: `datasets/sn83_history/raw/latest20_raw.json` → imported to `datasets/sn83_history/latest20.jsonl`.

### Notes

1. Official `wandb.Api()` still needs a key; public Forge GraphQL does not for this project.
2. `encoded_matrix` strings from history contain embedded spaces and do not round-trip through `GraphCodec`; **`adjacency_list` is intact** and is the graph used for verification/solvers.
3. Score reproduction vs logged miner metrics: **20/20 OK** (max abs error 0 on omega/optimality/rewards).

### What was NOT done

- No synthetic graphs labeled as historical SN83 challenges.
- No miner process launched.
- No C++/Numba solvers.

```

## B. Historical Miner Performance

| UUID | n | density | difficulty | t_limit | miners | hist best size | score repro |
|---|---:|---:|---:|---:|---:|---:|---|
| `fc92cd37…` | 297 | 0.772 | 0.7 | 15.0 | 64 | 25 | ok |
| `53839380…` | 292 | 0.906 | 0.7 | 15.0 | 90 | 50 | ok |
| `2c36dae9…` | 297 | 0.827 | 0.7 | 15.0 | 82 | 32 | ok |
| `f12351e7…` | 298 | 0.940 | 0.7 | 30.0 | 84 | 66 | ok |
| `1a5fcb5c…` | 299 | 0.801 | 0.7 | 15.0 | 82 | 28 | ok |
| `188a4272…` | 292 | 0.741 | 0.7 | 10.0 | 82 | 23 | ok |
| `fe10c0b3…` | 299 | 0.748 | 0.7 | 15.0 | 75 | 23 | ok |
| `42c827b2…` | 294 | 0.733 | 0.7 | 10.0 | 91 | 22 | ok |
| `7a5ba71a…` | 292 | 0.945 | 0.7 | 30.0 | 66 | 69 | ok |
| `b389bbe3…` | 297 | 0.815 | 0.7 | 10.0 | 60 | 30 | ok |
| `1987b6bb…` | 497 | 0.726 | 0.8 | 7.5 | 54 | 25 | ok |
| `22bc813e…` | 497 | 0.831 | 0.8 | 6.0 | 59 | 37 | ok |
| `9645a4e8…` | 493 | 0.774 | 0.8 | 15.0 | 41 | 29 | ok |
| `577e9988…` | 897 | 0.881 | 1.0 | 30.0 | 14 | 57 | ok |
| `1231dc5e…` | 896 | 0.786 | 1.0 | 10.0 | 14 | 34 | ok |
| `1db8cfb3…` | 897 | 0.835 | 1.0 | 30.0 | 21 | 44 | ok |
| `4c69bfb1…` | 700 | 0.862 | 0.9 | 30.0 | 38 | 48 | ok |
| `9bd55ea0…` | 895 | 0.838 | 1.0 | 15.0 | 23 | 45 | ok |
| `07965b58…` | 495 | 0.742 | 0.8 | 7.5 | 67 | 27 | ok |
| `225ce3c0…` | 299 | 0.815 | 0.7 | 6.0 | 76 | 30 | ok |

Score reproduction: 20/20 rounds within tolerance 1e-6.

## C. My Solver Performance

| Solver | Mean size | Mean runtime ms | Validity rate | Timeout rate |
|---|---:|---:|---:|---:|
| baseline | 34.300 | 15603.1 | 1.000 | 1.000 |
| ulm | 34.300 | 15604.3 | 1.000 | 1.000 |
| selective_ulm | 34.300 | 15602.7 | 1.000 | 1.000 |

## D. Recalculated Rewards

Counterfactual rewards are computed by appending the local solver answer to the historical response list and rescoring the **entire** pool with `CliqueScoreCalculator`. These are not comparable to unchanged logged rewards.

| UUID | baseline reward | ulm reward | selective_ulm reward |
|---|---:|---:|---:|
| `fc92cd37…` | 1.5829779804950208 | 1.5829779804950208 | 1.5829779804950208 |
| `53839380…` | 2.7 | 2.7 | 2.7 |
| `2c36dae9…` | 1.6207939068535437 | 1.6207939068535437 | 1.6207939068535437 |
| `f12351e7…` | 1.61119395191067 | 1.61119395191067 | 1.61119395191067 |
| `1a5fcb5c…` | 1.6179053789703786 | 1.6179053789703786 | 1.6179053789703786 |
| `188a4272…` | 1.5761344620477424 | 1.5761344620477424 | 1.5761344620477424 |
| `fe10c0b3…` | 1.6058818290285675 | 1.6058818290285675 | 1.6058818290285675 |
| `42c827b2…` | 2.587729915081223 | 2.587729915081223 | 2.587729915081223 |
| `7a5ba71a…` | 1.607002423583543 | 1.607002423583543 | 1.607002423583543 |
| `b389bbe3…` | 1.5925998377974468 | 1.5925998377974468 | 1.5925998377974468 |
| `1987b6bb…` | 1.6021464099103397 | 1.6021464099103397 | 1.6021464099103397 |
| `22bc813e…` | 1.597656809086164 | 1.597656809086164 | 1.597656809086164 |
| `9645a4e8…` | 1.5800770801398443 | 1.5800770801398443 | 1.5800770801398443 |
| `577e9988…` | 1.6901455100867675 | 1.6901455100867675 | 1.6901455100867675 |
| `1231dc5e…` | 1.8077364203591197 | 1.8077364203591197 | 1.8077364203591197 |
| `1db8cfb3…` | 1.717133082746381 | 1.717133082746381 | 1.717133082746381 |
| `4c69bfb1…` | 1.6563355072746888 | 1.6563355072746888 | 1.6563355072746888 |
| `9bd55ea0…` | 1.6985964084204723 | 1.6985964084204723 | 1.6985964084204723 |
| `07965b58…` | 1.566168834287141 | 1.566168834287141 | 1.566168834287141 |
| `225ce3c0…` | 1.567762066165567 | 1.567762066165567 | 1.567762066165567 |

## E. Round-by-Round Ranking

| UUID | hist best | base size/rank | ulm size/rank | sel size/rank |
|---|---:|---|---|---|
| `fc92cd37…` | 25 | 23/65 | 23/65 | 23/65 |
| `53839380…` | 50 | 50/1 | 50/1 | 50/1 |
| `2c36dae9…` | 32 | 31/82 | 31/82 | 31/82 |
| `f12351e7…` | 66 | 63/84 | 63/84 | 63/84 |
| `1a5fcb5c…` | 28 | 27/82 | 27/82 | 27/82 |
| `188a4272…` | 23 | 21/83 | 21/83 | 21/83 |
| `fe10c0b3…` | 23 | 22/76 | 22/76 | 22/76 |
| `42c827b2…` | 22 | 21/5 | 21/5 | 21/5 |
| `7a5ba71a…` | 69 | 66/67 | 66/67 | 66/67 |
| `b389bbe3…` | 30 | 28/61 | 28/61 | 28/61 |
| `1987b6bb…` | 25 | 22/54 | 22/54 | 22/54 |
| `22bc813e…` | 37 | 33/60 | 33/60 | 33/60 |
| `9645a4e8…` | 29 | 25/42 | 25/42 | 25/42 |
| `577e9988…` | 57 | 50/15 | 50/15 | 50/15 |
| `1231dc5e…` | 34 | 30/13 | 30/13 | 30/13 |
| `1db8cfb3…` | 44 | 39/21 | 39/21 | 39/21 |
| `4c69bfb1…` | 48 | 44/39 | 44/39 | 44/39 |
| `9bd55ea0…` | 45 | 41/24 | 41/24 | 41/24 |
| `07965b58…` | 27 | 23/68 | 23/68 | 23/68 |
| `225ce3c0…` | 30 | 27/77 | 27/77 | 27/77 |

## F. Summary Ranking Prediction

- Best measured solver: **baseline**
- Mean counterfactual rank percentile: **13.15** (bootstrap 95% CI 2.89–26.95)
- Top-1 / Top-3 rates: 1/20 , 1/20
- Historical-best match / exceed rates: 0.050 / 0.000
- Exact on-chain rank: **unavailable**
- Future on-chain rank: **uncertain**

On-chain weights use debiased EMA (α≈0.01), selection filtering, min-max normalization, sigmoid, and power scaling; 20 rounds cannot recover UID rank.

## G. Recommendation

Recommend **baseline** based on counterfactual mean rank percentile / reward on the retrieved historical set.

## H. Limitations

- Retrieved via public Forge GraphQL (no `WANDB_API_KEY`); two steps skipped on IncompleteRead.
- `encoded_matrix` from history does not round-trip `GraphCodec`; graphs used `adjacency_list` (score-verified).
- All three local solvers hit the challenge time limit every round (timeout_rate=1.0) and tied on size/reward.
- Mean gap vs historical best clique size: **2.9**; matched hist-best in 1/20 rounds; never exceeded.
- No fabricated historical challenges were inserted.
- Docs/`wandb_logging.md` omega naming disagrees with `validator.py` logging; verification detects swaps.
- Miner selection bias: only sampled miners appear in each round.
- EMA / weight-setting prevent equating round ranks with live incentive rank.

## Reproduction

```bash
cd sn83_clique_lab
export PYTHONPATH=.:.deps
python -m benchmarks.fetch_sn83_history --limit 20
python -m benchmarks.import_history --file exported_wandb_data.jsonl
python -m benchmarks.verify_history
python -m benchmarks.run_historical --solver all
python -m benchmarks.recalculate_scores
python -m benchmarks.predict_rank
python -m benchmarks.generate_report
```
