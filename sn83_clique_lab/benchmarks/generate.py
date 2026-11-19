"""Dataset generation entrypoint."""

from __future__ import annotations

import argparse

from clique.datasets import generate_synthetic_suite, import_official_samples


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--splits", nargs="+", default=["dev", "tune", "eval"])
    args = p.parse_args()
    print("official", len(import_official_samples()))
    for s in args.splits:
        print(s, len(generate_synthetic_suite(s)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
