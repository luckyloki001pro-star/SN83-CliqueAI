"""Shared vertex-probability model for R-EVO (Battiti & Brunato inspired).

Labeled as paper-faithful for the core update rule; not a line-by-line port.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple


@dataclass
class ProbabilityModel:
    """probability[v] ≈ learned tendency of v to appear in strong cliques."""

    n: int
    learning_rate: float = 0.5
    delta: int = 3
    initial: float = 0.5
    probability: List[float] = field(default_factory=list)
    update_calls: int = 0
    last_near_best_count: int = 0
    last_entropy: float = 0.0

    def __post_init__(self) -> None:
        if not self.probability:
            self.probability = [float(self.initial)] * self.n
        if len(self.probability) != self.n:
            raise ValueError("probability length must equal n")
        if not (0.0 < self.learning_rate <= 1.0):
            raise ValueError("learning_rate must be in (0, 1]")

    def reset(self) -> None:
        self.probability = [float(self.initial)] * self.n
        self.update_calls = 0
        self.last_near_best_count = 0
        self.last_entropy = binary_entropy_mean(self.probability)

    def clamp(self, floor: float = 0.0, ceil: float = 1.0) -> None:
        for i, p in enumerate(self.probability):
            if p < floor:
                self.probability[i] = floor
            elif p > ceil:
                self.probability[i] = ceil

    def update_from_cliques(
        self,
        cliques: Sequence[Sequence[int]],
        sizes: Sequence[int] | None = None,
        smax: int | None = None,
    ) -> int:
        """Update from near-best cliques (size >= Smax - DELTA).

        Returns number of cliques used in the update.
        """
        if not cliques:
            return 0
        if sizes is None:
            sizes = [len(c) for c in cliques]
        if smax is None:
            smax = max(sizes) if sizes else 0
        selected = [c for c, s in zip(cliques, sizes) if s >= smax - self.delta]
        if not selected:
            return 0
        freq = [0.0] * self.n
        inv = 1.0 / len(selected)
        for c in selected:
            seen = set()
            for v in c:
                if 0 <= v < self.n and v not in seen:
                    freq[v] += inv
                    seen.add(v)
        lr = self.learning_rate
        one_m = 1.0 - lr
        for v in range(self.n):
            self.probability[v] = one_m * self.probability[v] + lr * freq[v]
        self.update_calls += 1
        self.last_near_best_count = len(selected)
        self.last_entropy = binary_entropy_mean(self.probability)
        return len(selected)


def binary_entropy_mean(probs: Sequence[float]) -> float:
    """Mean binary entropy H(p) = -p log p - (1-p) log(1-p); safe at 0/1."""
    if not probs:
        return 0.0
    s = 0.0
    for p in probs:
        if p <= 0.0 or p >= 1.0:
            continue
        s += -p * math.log(p) - (1.0 - p) * math.log(1.0 - p)
    return s / len(probs)


def jaccard_similarity(a: Sequence[int], b: Sequence[int]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 1.0
    return len(sa & sb) / len(union)


def mean_pairwise_jaccard(cliques: Sequence[Sequence[int]]) -> float:
    m = len(cliques)
    if m < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(m):
        for j in range(i + 1, m):
            total += jaccard_similarity(cliques[i], cliques[j])
            count += 1
    return total / count if count else 0.0


def select_near_best(
    cliques: Sequence[Sequence[int]],
    sizes: Sequence[int],
    delta: int,
) -> List[Sequence[int]]:
    if not sizes:
        return []
    smax = max(sizes)
    return [c for c, s in zip(cliques, sizes) if s >= smax - delta]
