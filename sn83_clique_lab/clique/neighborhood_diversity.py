"""Elite pool and equal-size neighborhood enumeration for ONE diversity mode."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .bitset import list_to_mask
from .graph import BitsetGraph
from .neighborhood_exact import ExactStatus, search_target_clique
from .optimal_neighborhood import Neighborhood, assemble_clique, build_neighborhood
from .validation import is_clique


def jaccard(mask_a: int, mask_b: int) -> float:
    inter = (mask_a & mask_b).bit_count()
    union = (mask_a | mask_b).bit_count()
    return inter / union if union else 0.0


@dataclass
class EliteEntry:
    clique: List[int]
    mask: int
    size: int
    discovery_time_ms: float
    discovery_method: str
    seed: int
    neighborhood_signature: int


@dataclass
class ElitePool:
    capacity: int = 64
    entries: List[EliteEntry] = field(default_factory=list)
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
        method: str,
        seed: int,
        neighborhood_signature: int = 0,
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
        entry = EliteEntry(
            clique=sorted(clique),
            mask=mask,
            size=size,
            discovery_time_ms=discovery_time_ms,
            discovery_method=method,
            seed=seed,
            neighborhood_signature=neighborhood_signature,
        )
        self.entries.append(entry)
        self._masks.add(mask)
        if len(self.entries) > self.capacity:
            self._trim_diverse()
        return True

    def _trim_diverse(self) -> None:
        """Keep structurally diverse best-sized cliques (low pairwise Jaccard preferred)."""
        if len(self.entries) <= self.capacity:
            return
        # Greedy: keep first, then farthest (lowest max-jaccard to kept)
        kept: List[EliteEntry] = [self.entries[0]]
        remaining = self.entries[1:]
        while len(kept) < self.capacity and remaining:
            best_i = 0
            best_score = 1e9
            for i, e in enumerate(remaining):
                mx = max(jaccard(e.mask, k.mask) for k in kept)
                if mx < best_score:
                    best_score = mx
                    best_i = i
            kept.append(remaining.pop(best_i))
        self.entries = kept
        self._masks = {e.mask for e in kept}

    def sample(self, rng: random.Random, policy: str = "first_best") -> List[int]:
        if not self.entries:
            return []
        best = self.best_size()
        pool = [e for e in self.entries if e.size == best]
        if not pool:
            return list(self.entries[0].clique)
        if policy == "randomly_selected_best":
            return list(rng.choice(pool).clique)
        if policy == "diverse_best":
            # farthest from first
            base = pool[0].mask
            best_e = min(pool, key=lambda e: jaccard(e.mask, base) if e is not pool[0] else 1.0)
            # if only one, return it
            if len(pool) == 1:
                return list(pool[0].clique)
            others = [e for e in pool if e.mask != base]
            if others:
                best_e = min(others, key=lambda e: jaccard(e.mask, base))
                return list(best_e.clique)
            return list(pool[0].clique)
        if policy == "deterministic_hash_best":
            return list(min(pool, key=lambda e: e.mask).clique)
        # first_best
        return list(pool[0].clique)

    def to_diagnostics(self) -> Dict:
        best = self.best_size()
        pool = [e for e in self.entries if e.size == best]
        pairs = []
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                pairs.append(jaccard(pool[i].mask, pool[j].mask))
        return {
            "elite_count": len(self.entries),
            "best_size": best,
            "best_sized_count": len(pool),
            "mean_pairwise_jaccard": sum(pairs) / len(pairs) if pairs else 0.0,
            "methods": sorted({e.discovery_method for e in self.entries}),
        }


def enumerate_equal_size_replacements(
    graph: BitsetGraph,
    clique: Sequence[int],
    remove: Sequence[int],
    deadline: float,
    elite: ElitePool,
    *,
    seed: int = 0,
    t0: Optional[float] = None,
) -> int:
    """Search for Q of size >= r (equal-size or better) and add to elite.

    Returns number of new elite additions.
    """
    t_ref = t0 if t0 is not None else time.perf_counter()
    nb = build_neighborhood(graph, clique, remove)
    if nb.candidate_count < nb.removed_count:
        return 0
    # Target equal-size: |Q| >= r
    target = nb.removed_count
    if target <= 0:
        return 0
    res = search_target_clique(graph, nb.candidate_mask, target, deadline)
    added = 0
    if res.status == ExactStatus.TARGET_FOUND and res.clique:
        q_mask = list_to_mask(res.clique)
        new_c = assemble_clique(nb.fixed_mask, q_mask)
        if is_clique(graph, new_c):
            if elite.add(
                new_c,
                discovery_time_ms=(time.perf_counter() - t_ref) * 1000.0,
                method="equal_enum",
                seed=seed,
                neighborhood_signature=nb.fixed_mask,
            ):
                added += 1
    return added
