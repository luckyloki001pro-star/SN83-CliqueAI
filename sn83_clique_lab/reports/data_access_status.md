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
