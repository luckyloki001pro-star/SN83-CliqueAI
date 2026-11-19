"""Dynamic edge weights with NuMVC forgetting (ρ, γ)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .complement_graph import ComplementGraph


@dataclass
class EdgeWeights:
    """Integer edge weights for complement edges."""

    weights: List[int]
    total_weight: int
    m: int
    gamma: float
    rho: float
    forgetting_events: int = 0
    weight_increments: int = 0
    enable_forgetting: bool = True
    enable_weights: bool = True  # if False, weights stay 1 (still tracked)

    @classmethod
    def create(
        cls,
        comp: ComplementGraph,
        *,
        gamma: float | None = None,
        rho: float = 0.3,
        enable_forgetting: bool = True,
        enable_weights: bool = True,
    ) -> "EdgeWeights":
        m = comp.complement_edge_count
        # Paper default: γ = 0.5 |V|
        g = float(gamma) if gamma is not None else 0.5 * max(1, comp.n)
        return cls(
            weights=[1] * m,
            total_weight=m,
            m=m,
            gamma=g,
            rho=rho,
            enable_forgetting=enable_forgetting,
            enable_weights=enable_weights,
        )

    @property
    def mean_weight(self) -> float:
        return self.total_weight / self.m if self.m else 0.0

    @property
    def max_weight(self) -> int:
        return max(self.weights) if self.weights else 0

    def increment_uncovered(self, uncovered_ids: List[int]) -> None:
        if not self.enable_weights:
            return
        for e in uncovered_ids:
            self.weights[e] += 1
            self.total_weight += 1
            self.weight_increments += 1

    def maybe_forget(self) -> bool:
        """Apply floor(ρ·w) to all edges if mean >= γ. Returns True if forgot."""
        if not self.enable_weights or not self.enable_forgetting or self.m == 0:
            return False
        if self.mean_weight < self.gamma:
            return False
        new_total = 0
        rho = self.rho
        w = self.weights
        for i in range(self.m):
            w[i] = int(rho * w[i])  # floor for nonnegative
            new_total += w[i]
        self.total_weight = new_total
        self.forgetting_events += 1
        return True
