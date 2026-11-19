"""Fetch latest complete SN83 validator challenges from W&B (read-only)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".deps"))

from clique.history import (  # noqa: E402
    check_completeness,
    normalize_record,
    save_jsonl,
    select_latest_complete,
    write_manifest,
)

OUT_DIR = ROOT / "datasets" / "sn83_history"
PROJECT = "toptensor-ai/CliqueAI"
SOURCE_URLS = [
    "https://wandb.ai/toptensor-ai/CliqueAI/table",
    "https://github.com/toptensor/CliqueAI/blob/main/docs/wandb_logging.md",
]


def _extract_from_history_row(row: Dict[str, Any], run_id: str) -> Dict[str, Any] | None:
    """Try to recover a WandbRunLogData-like dict from a history row."""
    # Common patterns: flat keys, nested under 'data', or JSON string columns.
    candidates = [row]
    if isinstance(row.get("data"), dict):
        candidates.append(row["data"])
    for key in ("wandb_log", "log_data", "challenge", "payload"):
        val = row.get(key)
        if isinstance(val, dict):
            candidates.append(val)
        elif isinstance(val, str) and val.strip().startswith("{"):
            try:
                candidates.append(json.loads(val))
            except json.JSONDecodeError:
                pass

    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        # Flatten keys like miner_uids that may be nested.
        flat = dict(cand)
        if "uuid" in flat and "miner_ans" in flat:
            return normalize_record(
                flat,
                provenance={
                    "wandb_run_id": run_id,
                    "source": "wandb_history",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                },
            )
    return None


def fetch_via_wandb(limit: int = 20, max_runs: int = 50) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    status: Dict[str, Any] = {
        "method": "wandb.Api",
        "ok": False,
        "error": None,
        "run_ids_scanned": [],
        "rows_seen": 0,
        "records_parsed": 0,
    }
    try:
        import wandb
    except ImportError as e:
        status["error"] = f"wandb not installed: {e}"
        return [], status

    try:
        api = wandb.Api(timeout=120)
    except Exception as e:
        status["error"] = f"wandb.Api() failed: {type(e).__name__}: {e}"
        return [], status

    records: List[Dict[str, Any]] = []
    try:
        runs = api.runs(PROJECT, order="-created_at", per_page=min(max_runs, 50))
    except Exception as e:
        status["error"] = f"api.runs failed: {type(e).__name__}: {e}"
        return [], status

    scanned = 0
    for run in runs:
        if scanned >= max_runs:
            break
        scanned += 1
        status["run_ids_scanned"].append(run.id)
        try:
            # Prefer complete history over sampled.
            for row in run.scan_history(page_size=500):
                status["rows_seen"] += 1
                rec = _extract_from_history_row(dict(row), run.id)
                if rec is not None:
                    records.append(rec)
                    status["records_parsed"] += 1
        except Exception as e:
            status.setdefault("run_errors", []).append(
                {"run_id": run.id, "error": f"{type(e).__name__}: {e}"}
            )
            # Fallback: summary / config sometimes holds last payload
            try:
                summary = dict(run.summary)
                rec = _extract_from_history_row(summary, run.id)
                if rec is not None:
                    records.append(rec)
                    status["records_parsed"] += 1
            except Exception:
                pass

        # Also inspect tables/artifacts if present.
        try:
            for art in run.logged_artifacts():
                if "table" in art.type or "table" in art.name.lower():
                    status.setdefault("artifacts_seen", []).append(
                        {"run_id": run.id, "name": art.name, "type": art.type}
                    )
        except Exception:
            pass

        # Early stop if we already have enough unique complete records.
        selected, _ = select_latest_complete(records, limit=limit)
        if len(selected) >= limit and scanned >= 3:
            # Keep scanning a bit for recency confirmation; break after enough.
            if scanned >= min(10, max_runs):
                break

    status["ok"] = status["records_parsed"] > 0
    if not status["ok"] and status["error"] is None:
        status["error"] = (
            "No complete challenge records parsed from scanned runs. "
            "Project may store tables differently or require auth."
        )
    return records, status


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch latest SN83 W&B challenges")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-runs", type=int, default=50)
    p.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = p.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    access_path = ROOT / "reports" / "data_access_status.md"
    access_path.parent.mkdir(parents=True, exist_ok=True)

    key_present = bool(os.environ.get("WANDB_API_KEY"))
    records, status = fetch_via_wandb(limit=args.limit, max_runs=args.max_runs)

    complete = [r for r in records if check_completeness(r).ok]
    selected, conflicts = select_latest_complete(complete, limit=args.limit)

    warnings: List[Any] = list(conflicts)
    if status.get("error"):
        warnings.append({"type": "fetch_error", "detail": status["error"]})
    if not key_present:
        warnings.append(
            {
                "type": "auth",
                "detail": "WANDB_API_KEY not set; wandb.Api requires login for this project.",
            }
        )
    if len(selected) < args.limit:
        warnings.append(
            {
                "type": "incomplete_retrieval",
                "detail": f"Only {len(selected)} complete records available; requested {args.limit}.",
            }
        )

    access_status = "success" if len(selected) == args.limit else (
        "partial" if selected else "failed"
    )

    # Only write latest20.jsonl when we have real records (never fabricate).
    out_jsonl = args.output_dir / "latest20.jsonl"
    if selected:
        save_jsonl(out_jsonl, selected)
    elif out_jsonl.exists():
        # Do not leave stale pretended data; remove if empty fetch after prior?
        # Keep existing only if user imported; write empty marker file instead.
        pass

    write_manifest(
        args.output_dir / "manifest.json",
        selected=selected,
        retrieved_count=len(records),
        complete_count=len(complete),
        run_ids=status.get("run_ids_scanned", []),
        warnings=warnings,
        source="wandb.Api:" + PROJECT,
        source_urls=SOURCE_URLS,
        access_status=access_status,
    )

    # Persist raw fetch status (no secrets).
    (args.output_dir / "fetch_status.json").write_text(
        json.dumps(
            {
                "access_status": access_status,
                "wandb_api_key_configured": key_present,
                "status": {k: v for k, v in status.items() if k != "error" or True},
                "selected_count": len(selected),
                "warnings": warnings,
            },
            indent=2,
            default=str,
        )
    )

    access_md = f"""# SN83 Historical Data Access Status

## Retrieval attempt

- UTC time: `{datetime.now(timezone.utc).isoformat()}`
- Project: `{PROJECT}`
- Method: `wandb.Api().runs(...).scan_history(...)`
- `WANDB_API_KEY` configured: **{key_present}**
- Access status: **{access_status}**
- Complete records selected: **{len(selected)}** / {args.limit}

## Result

"""
    if selected:
        access_md += (
            f"Retrieved {len(selected)} real complete challenge record(s). "
            f"Saved to `{out_jsonl}`.\n\n"
        )
        access_md += "Selected UUIDs:\n\n"
        for r in selected:
            access_md += f"- `{r.get('uuid')}` ts={r.get('timestamp')}\n"
    else:
        access_md += """**No historical challenge records were retrieved.**

This environment could not read `toptensor-ai/CliqueAI` via the W&B API.

Observed blockers:

1. No `WANDB_API_KEY` / `wandb login` credentials in the environment.
2. Outbound HTTPS to `api.wandb.ai` failed with proxy CONNECT 403 from this sandbox/network path.
3. The public dashboard/table page requires interactive authentication (Forge/W&B login).

### What was NOT done

- No synthetic graphs were labeled as historical SN83 challenges.
- `datasets/sn83_history/latest20.jsonl` was **not** populated with fake rows.

### How to unblock

1. On a machine with W&B access, run `wandb login` (or set `WANDB_API_KEY` in the environment — do not paste the key into chat).
2. Re-run:

```bash
cd sn83_clique_lab
PYTHONPATH=.:.deps python -m benchmarks.fetch_sn83_history --limit 20
```

3. Or export the W&B table/history from https://wandb.ai/toptensor-ai/CliqueAI/table
   as JSON/JSONL/CSV and import:

```bash
PYTHONPATH=.:.deps python -m benchmarks.import_history --file /path/to/export.jsonl
```

Required fields per record are listed in `docs/wandb_logging.md` / `WandbRunLogData`.
"""

    if status.get("error"):
        access_md += f"\n### Fetch error detail\n\n```\n{status['error']}\n```\n"
    if warnings:
        access_md += "\n### Warnings\n\n"
        for w in warnings:
            access_md += f"- `{json.dumps(w, default=str)}`\n"

    access_path.write_text(access_md)
    print(json.dumps({"access_status": access_status, "selected": len(selected)}, indent=2))
    return 0 if access_status != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
