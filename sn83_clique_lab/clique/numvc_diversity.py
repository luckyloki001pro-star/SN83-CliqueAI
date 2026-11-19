"""Bounded distinct clique pool for NuMVC / MIS solvers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .bitset import list_to_mask


@dataclass
class CliqueEntry:
    clique: List[int]
    mask: int
    size: int
    discovery_time_ms: float
    variant: str
    seed: int


@dataclass
class CliquePool:
    capacity: int = 32
    entries: List[CliqueEntry] = field(default_factory=list)
    _masks: set = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.entries)

    def best_size(self) -> int:
        return max((e.size for e in self.entries), default=0)

    def add(
        self,
        clique: Sequence[int],
        *,
        discovery_time_ms: float,
        variant: str,
        seed: int,
    ) -> bool:
        if not clique:
            return False
        mask = list_to_mask(clique)
        if mask in self._masks:
            return False
        size = len(clique)
        best = self.best_size()
        if size < best:
            return False
        if size > best:
            self.entries.clear()
            self._masks.clear()
        self.entries.append(
            CliqueEntry(
                clique=sorted(clique),
                mask=mask,
                size=size,
                discovery_time_ms=discovery_time_ms,
                variant=variant,
                seed=seed,
            )
        )
        self._masks.add(mask)
        if len(self.entries) > self.capacity:
            self.entries = self.entries[: self.capacity]
            self._masks = {e.mask for e in self.entries}
        return True

    def to_dict(self) -> Dict:
        return {
            "count": len(self.entries),
            "best_size": self.best_size(),
            "sizes": [e.size for e in self.entries],
        }
