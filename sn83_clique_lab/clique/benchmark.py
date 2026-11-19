"""python -m clique.benchmark --mode quick|full"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SN83 clique lab benchmarks")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--output", default="reports")
    args = parser.parse_args(argv)

    from benchmarks.run import run_benchmark

    rows = run_benchmark(mode=args.mode, output_dir=Path(args.output))
    print(json.dumps({"mode": args.mode, "runs": len(rows), "output": args.output}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
