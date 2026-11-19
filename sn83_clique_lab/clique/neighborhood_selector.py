"""Neighborhood scheduling: random / conflict-guided / adaptive r selection."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from .bitset import bits_to_list, list_to_mask
from .graph import BitsetGraph
from .optimal_neighborhood import conflict_mask, conflict_union


@dataclass
class RemovalArmStats:
    attempts: int = 0
    successful_improvements: int = 0
    sum_candidate_count: float = 0.0
    sum_search_nodes: float = 0.0
    sum_search_ms: float = 0.0
    timeouts: int = 0
    proven_impossible: int = 0

    @property
    def mean_candidate_count(self) -> float:
        return self.sum_candidate_count / self.attempts if self.attempts else 0.0

    @property
    def timeout_rate(self) -> float:
        return self.timeouts / self.attempts if self.attempts else 0.0

    @property
    def improvement_rate(self) -> float:
        return self.successful_improvements / self.attempts if self.attempts else 0.0

    @property
    def improvement_per_second(self) -> float:
        sec = self.sum_search_ms / 1000.0
        return self.successful_improvements / sec if sec > 1e-9 else 0.0


@dataclass
class AdaptiveRController:
    """Lightweight multi-armed bandit over removal sizes."""

    sizes: List[int] = field(default_factory=lambda: [3, 4, 6, 8, 10])
    arms: Dict[int, RemovalArmStats] = field(default_factory=dict)
    explore_fraction: float = 0.25

    def __post_init__(self) -> None:
        for r in self.sizes:
            self.arms.setdefault(r, RemovalArmStats())

    def choose(self, rng: random.Random, clique_size: int) -> int:
        eligible = [r for r in self.sizes if 1 <= r < clique_size]
        if not eligible:
            return max(1, min(3, max(1, clique_size - 1)))
        if rng.random() < self.explore_fraction:
            # Prefer underexplored
            return min(eligible, key=lambda r: (self.arms[r].attempts, r))
        # Exploit: best improvement_per_second, then improvement_rate, then least timeouts
        def score(r: int) -> Tuple[float, float, float]:
            a = self.arms[r]
            return (a.improvement_per_second, a.improvement_rate, -a.timeout_rate)

        return max(eligible, key=score)

    def record(
        self,
        r: int,
        *,
        improved: bool,
        candidate_count: int,
        search_nodes: int,
        search_ms: float,
        timed_out: bool,
        proven: bool,
    ) -> None:
        arm = self.arms.setdefault(r, RemovalArmStats())
        arm.attempts += 1
        if improved:
            arm.successful_improvements += 1
        arm.sum_candidate_count += candidate_count
        arm.sum_search_nodes += search_nodes
        arm.sum_search_ms += search_ms
        if timed_out:
            arm.timeouts += 1
        if proven:
            arm.proven_impossible += 1

    def to_dict(self) -> Dict[str, dict]:
        return {
            str(r): {
                "attempts": a.attempts,
                "successful_improvements": a.successful_improvements,
                "mean_candidate_count": a.mean_candidate_count,
                "mean_search_nodes": a.sum_search_nodes / a.attempts if a.attempts else 0.0,
                "mean_search_ms": a.sum_search_ms / a.attempts if a.attempts else 0.0,
                "timeout_rate": a.timeout_rate,
                "improvement_per_second": a.improvement_per_second,
                "proven_impossible": a.proven_impossible,
            }
            for r, a in sorted(self.arms.items())
        }


@dataclass(frozen=True)
class ProposedNeighborhood:
    remove: Tuple[int, ...]
    r: int
    source: str  # random | conflict | adaptive
    signature: int  # fixed_mask for cache (or removed_mask)


def random_removals(
    clique: Sequence[int],
    r: int,
    rng: random.Random,
    n_proposals: int = 1,
) -> List[ProposedNeighborhood]:
    c = list(clique)
    if r <= 0 or r >= len(c):
        return []
    out: List[ProposedNeighborhood] = []
    seen = set()
    for _ in range(n_proposals * 3):
        if len(out) >= n_proposals:
            break
        rem = tuple(sorted(rng.sample(c, r)))
        if rem in seen:
            continue
        seen.add(rem)
        r_mask = list_to_mask(rem)
        c_mask = list_to_mask(c)
        f_mask = c_mask & ~r_mask
        out.append(ProposedNeighborhood(rem, r, "random", f_mask))
    return out


def conflict_guided_removals(
    graph: BitsetGraph,
    clique: Sequence[int],
    rng: random.Random,
    *,
    max_seed_size: int = 3,
    max_proposals: int = 8,
) -> List[ProposedNeighborhood]:
    """Derive R from unions of conflict masks of small mutually-adjacent outside sets."""
    c = list(clique)
    c_mask = list_to_mask(c)
    outside = bits_to_list(graph.all_vertices_mask() & ~c_mask)
    if not outside:
        return []

    # Rank outside by small conflict count
    scored: List[Tuple[int, int, int]] = []
    for v in outside:
        cm = conflict_mask(graph, c_mask, v)
        cc = cm.bit_count()
        if cc == 0:
            continue  # already adjacent to all — should extend maximality elsewhere
        scored.append((cc, -graph.degree(v), v))
    scored.sort()
    seeds = [v for _, __, v in scored[: min(64, len(scored))]]
    if not seeds:
        return []

    proposals: List[ProposedNeighborhood] = []
    seen_f: set = set()

    def add_from_A(A: List[int], source: str) -> None:
        if len(proposals) >= max_proposals:
            return
        r_mask = conflict_union(graph, c_mask, A)
        rem = bits_to_list(r_mask)
        if not rem or len(rem) >= len(c):
            return
        f_mask = c_mask & ~r_mask
        if f_mask in seen_f:
            return
        seen_f.add(f_mask)
        proposals.append(
            ProposedNeighborhood(tuple(sorted(rem)), len(rem), source, f_mask)
        )

    # Size-1 seeds
    for v in seeds[:24]:
        add_from_A([v], "conflict1")
        if len(proposals) >= max_proposals:
            return proposals

    # Size-2 mutually adjacent
    if max_seed_size >= 2:
        for i, u in enumerate(seeds[:20]):
            for w in seeds[i + 1 : 20]:
                if not graph.has_edge(u, w):
                    continue
                add_from_A([u, w], "conflict2")
                if len(proposals) >= max_proposals:
                    return proposals

    # Size-3
    if max_seed_size >= 3:
        top = seeds[:12]
        for i, u in enumerate(top):
            for j in range(i + 1, len(top)):
                w = top[j]
                if not graph.has_edge(u, w):
                    continue
                for z in top[j + 1 :]:
                    if graph.has_edge(u, z) and graph.has_edge(w, z):
                        add_from_A([u, w, z], "conflict3")
                        if len(proposals) >= max_proposals:
                            return proposals

    # Shuffle lightly for variety across rounds
    rng.shuffle(proposals)
    return proposals


def iter_scheduled_neighborhoods(
    graph: BitsetGraph,
    clique: Sequence[int],
    rng: random.Random,
    *,
    mode: str,
    r_fixed: Optional[int] = None,
    controller: Optional[AdaptiveRController] = None,
    batch: int = 4,
) -> Iterator[ProposedNeighborhood]:
    """Yield proposed removable sets under a scheduling mode."""
    c = list(clique)
    if len(c) < 2:
        return
    if mode == "conflict":
        for p in conflict_guided_removals(graph, c, rng, max_proposals=batch * 2):
            yield p
        # fill with random of typical r
        r = r_fixed or 6
        r = min(r, len(c) - 1)
        for p in random_removals(c, r, rng, n_proposals=batch):
            yield p
        return

    if mode == "adaptive":
        ctrl = controller or AdaptiveRController()
        for _ in range(batch):
            r = ctrl.choose(rng, len(c))
            for p in random_removals(c, r, rng, n_proposals=1):
                yield p
        # also inject some conflict proposals
        for p in conflict_guided_removals(graph, c, rng, max_proposals=max(2, batch // 2)):
            yield p
        return

    # random / default
    sizes = [r_fixed] if r_fixed else [3, 4, 6, 8, 10]
    for r in sizes:
        if 1 <= r < len(c):
            for p in random_removals(c, r, rng, n_proposals=max(1, batch // len(sizes))):
                yield p
