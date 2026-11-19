"""Selective activation policy for ULM (Method C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(slots=True)
class SelectiveULMConfig:
    ULM_MAX_GAP: int = 2
    ULM_MIN_CANDIDATES: int = 16
    ULM_MIN_REMAINING_MS: float = 150.0
    ULM_MAX_TIME_FRACTION: float = 0.15


@dataclass
class SelectiveULMCounters:
    eligible: int = 0
    activated: int = 0
    skipped: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    conflicts_found: int = 0
    bound_reductions: int = 0
    additional_prunes: int = 0
    ulm_time_ns: int = 0

    def bump_skip(self, reason: str) -> None:
        self.skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1


def should_run_ulm(
    *,
    gap: int,
    candidate_count: int,
    remaining_ms: float,
    ulm_time_ns: int,
    total_budget_ns: int,
    cfg: SelectiveULMConfig,
    counters: SelectiveULMCounters,
) -> bool:
    """
    Return True iff selective policy activates ULM.

    Activation never affects soundness: skipped calls fall back to coloring.
    """
    if gap <= 0:
        counters.bump_skip("already_prunable")
        return False

    counters.eligible += 1

    if gap > cfg.ULM_MAX_GAP:
        counters.bump_skip("gap_too_large")
        return False
    if candidate_count < cfg.ULM_MIN_CANDIDATES:
        counters.bump_skip("too_few_candidates")
        return False
    if remaining_ms < cfg.ULM_MIN_REMAINING_MS:
        counters.bump_skip("low_remaining_time")
        return False
    max_ulm_ns = int(total_budget_ns * cfg.ULM_MAX_TIME_FRACTION)
    if ulm_time_ns >= max_ulm_ns:
        counters.bump_skip("ulm_budget_exhausted")
        return False

    counters.activated += 1
    return True
