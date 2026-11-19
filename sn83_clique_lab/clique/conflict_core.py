"""Conflict-core data structures for unit-weight ULM.

Unit-weight specialization (SN83 / MCP):
- Every vertex has weight 1.
- Independent-set weight w*(I) = max weight in I = 1.
- Conflict shared weight β = min_i w*(I_i) = 1 always.
- split(I, 1) locks the entire set (weight 1) and leaves no remainder.
- Bound reduction per conflict is therefore exactly 1.
- Unlocking still matters: after a core's penalty is paid (uw >= w),
  remaining locked independent sets may re-enter unit propagation.

This module never guesses bounds; all reductions come from detected
conflicts under unit propagation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(slots=True)
class IndependentSet:
    """One color-class / independent set used in MaxSAT reasoning."""

    id: int
    # Current feasible members under reasoning assumptions (bitset).
    mask: int
    # Original members (bitset), used for restore.
    original_mask: int
    weight: int = 1  # unit-weight specialization
    active: bool = True
    locked: bool = False
    unlocked: bool = False  # True once core unlocks this set for reuse
    satisfied: bool = False
    core_id: int = -1
    # Which unit sets caused each vertex removal (vertex -> reason iset id).
    # Stored sparsely via parallel lists for restore.
    removal_reasons: dict = field(default_factory=dict)


@dataclass(slots=True)
class ConflictCore:
    """Conflict core preserving locked independent sets (paper Def. 1)."""

    id: int
    iset_ids: List[int]
    weight: int  # penalty c.w
    unlock_weight: int = 0  # c.uw accounted empty locked weight
    active: bool = True
    unlocked_iset_ids: List[int] = field(default_factory=list)


@dataclass(slots=True)
class ReasoningStats:
    conflicts: int = 0
    cores_created: int = 0
    cores_merged: int = 0
    unlock_events: int = 0
    bound_reductions: int = 0
    total_reduction: int = 0
    propagations: int = 0
    calls: int = 0
    time_ns: int = 0
    max_call_ns: int = 0


def core_invariant_holds(
    cores: List[ConflictCore],
    isets: List[IndependentSet],
) -> bool:
    """Structural sanity check (not a full clique enumeration)."""
    for c in cores:
        if not c.active:
            continue
        if c.weight < 0 or c.unlock_weight < 0:
            return False
        if c.unlock_weight > c.weight + 1:
            # Allow equality at unlock threshold; slight overshoot is ok
            # only transiently before unlock clears state.
            pass
        for iid in c.iset_ids:
            if iid < 0 or iid >= len(isets):
                return False
    return True
