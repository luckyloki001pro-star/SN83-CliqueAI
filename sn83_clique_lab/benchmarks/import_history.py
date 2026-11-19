"""Import authorized manual W&B exports into datasets/sn83_history."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clique.history import (
    check_completeness,
    normalize_record,
    save_jsonl,
    select_latest_complete,
    write_manifest,
)

OUT_DIR = ROOT / "datasets" / "sn83_history"
SOURCE_URLS = [
    "https://wandb.ai/toptensor-ai/CliqueAI/table",
    "manual_export",
]


def _parse_maybe_json(val: Any) -> Any:
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return val
    return val


def load_export(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "rows", "records", "history", "table"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        raise ValueError("Unrecognized JSON structure")
    if path.suffix.lower() == ".csv":
        rows = []
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                parsed = {k: _parse_maybe_json(v) for k, v in row.items()}
                rows.append(parsed)
        return rows
    raise ValueError(f"Unsupported export format: {path.suffix}")


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Import W&B-exported SN83 history")
    p.add_argument("--file", required=True, type=Path)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = p.parse_args(argv)

    raw_rows = load_export(args.file)
    records = []
    for row in raw_rows:
        rec = normalize_record(
            row,
            provenance={
                "source": "manual_export",
                "export_file": str(args.file),
                "imported_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        records.append(rec)

    complete = [r for r in records if check_completeness(r).ok]
    selected, conflicts = select_latest_complete(complete, limit=args.limit)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = args.output_dir / "latest20.jsonl"
    if not selected:
        print(
            json.dumps(
                {
                    "error": "no complete records in export",
                    "parsed": len(records),
                    "complete": len(complete),
                },
                indent=2,
            )
        )
        return 1

    save_jsonl(out_jsonl, selected)
    write_manifest(
        args.output_dir / "manifest.json",
        selected=selected,
        retrieved_count=len(records),
        complete_count=len(complete),
        run_ids=[],
        warnings=conflicts
        + (
            [{"type": "partial", "detail": f"only {len(selected)} of {args.limit}"}]
            if len(selected) < args.limit
            else []
        ),
        source=f"import:{args.file}",
        source_urls=SOURCE_URLS,
        access_status="imported" if len(selected) == args.limit else "imported_partial",
    )
    print(json.dumps({"imported": len(selected), "path": str(out_jsonl)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
