"""Shared verified incumbent for dual-solver portfolios (Phase 5C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .bitset import list_to_mask
from .graph import BitsetGraph
from .greedy import extend_to_maximal
from .validation import is_clique, is_maximal_clique


@dataclass
class IncumbentRecord:
    clique: List[int]
    mask: int
    size: int
    source: str
    discovery_time_ms: float


@dataclass
class SharedIncumbent:
    """Global best maximal clique across independent solvers (output-only sharing)."""

    graph: BitsetGraph
    best: Optional[IncumbentRecord] = None
    updates: int = 0
    elite: List[IncumbentRecord] = field(default_factory=list)
    elite_capacity: int = 16
    _elite_masks: set = field(default_factory=set)

    @property
    def size(self) -> int:
        return self.best.size if self.best else 0

    @property
    def clique(self) -> List[int]:
        return list(self.best.clique) if self.best else []

    def consider(
        self,
        clique: Sequence[int],
        *,
        source: str,
        discovery_time_ms: float,
        require_maximal: bool = True,
    ) -> bool:
        """Accept candidate if larger (or equal for elite). Returns True if global best grew."""
        c = list(clique)
        if not c:
            return False
        if not is_clique(self.graph, c):
            return False
        if require_maximal and not is_maximal_clique(self.graph, c):
            c = sorted(extend_to_maximal(self.graph, c))
            if not is_maximal_clique(self.graph, c):
                return False
        c = sorted(c)
        mask = list_to_mask(c)
        size = len(c)
        grew = False
        if self.best is None or size > self.best.size:
            self.best = IncumbentRecord(c, mask, size, source, discovery_time_ms)
            self.updates += 1
            grew = True
            # reset elite to new best size
            self.elite = [self.best]
            self._elite_masks = {mask}
        elif size == self.best.size and mask not in self._elite_masks:
            rec = IncumbentRecord(c, mask, size, source, discovery_time_ms)
            self.elite.append(rec)
            self._elite_masks.add(mask)
            if len(self.elite) > self.elite_capacity:
                self.elite = self.elite[: self.elite_capacity]
                self._elite_masks = {e.mask for e in self.elite}
        return grew

    def to_dict(self) -> Dict:
        return {
            "size": self.size,
            "source": self.best.source if self.best else None,
            "discovery_time_ms": self.best.discovery_time_ms if self.best else None,
            "updates": self.updates,
            "elite_count": len(self.elite),
        }
