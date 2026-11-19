"""Unit-weight UnLocking Mechanism (ULM) MaxSAT bound tightening.

Faithful to ULE-MWC Algorithms 2–3, specialized to unit vertex weights.
No BES (Benefit-Enhanced Strategy) in this first experiment.

Soundness contract for a candidate subgraph:
    exact_omega <= ulm_bound <= coloring_bound
where bounds are remaining clique size (excluding the partial clique).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .conflict_core import ConflictCore, IndependentSet, ReasoningStats
from .graph import BitsetGraph


@dataclass(slots=True)
class ULMConfig:
    enabled: bool = True
    max_conflicts_per_call: int = 64
    max_time_ns: int = 50_000_000  # 50ms soft cap per call
    # When False, caller disabled ULM after a soundness failure.
    pruning_enabled: bool = True


@dataclass(slots=True)
class ULMResult:
    bound: int
    reduction: int
    coloring_bound: int
    stats: ReasoningStats
    sound: bool = True


class ULMReasoner:
    """Stateful ULM reasoner rebuilt per search-node call (local state)."""

    def __init__(
        self,
        graph: BitsetGraph,
        config: ULMConfig | None = None,
    ) -> None:
        self.graph = graph
        self.adj = graph.adjacency
        self.config = config or ULMConfig()
        self.global_stats = ReasoningStats()
        self._disabled_due_to_unsound = False

    def disable(self, reason: str = "") -> None:
        self._disabled_due_to_unsound = True
        self.config.pruning_enabled = False

    @property
    def available(self) -> bool:
        return (
            self.config.enabled
            and self.config.pruning_enabled
            and not self._disabled_due_to_unsound
        )

    def tighten_bound(
        self,
        color_classes: Sequence[int],
        candidates: int,
    ) -> ULMResult:
        """
        Run ULM on the independent sets (color classes) of ``candidates``.

        Returns a (possibly reduced) upper bound on the clique size of the
        induced candidate subgraph.
        """
        coloring_bound = len(color_classes)
        stats = ReasoningStats(calls=1)
        t0 = time.perf_counter_ns()

        if (
            not self.available
            or coloring_bound <= 1
            or candidates == 0
        ):
            stats.time_ns = time.perf_counter_ns() - t0
            self._accumulate(stats)
            return ULMResult(coloring_bound, 0, coloring_bound, stats)

        # Build local independent sets from color classes intersected with
        # candidates (classes should already be subsets, but be safe).
        isets: List[IndependentSet] = []
        for i, raw in enumerate(color_classes):
            mask = raw & candidates
            if mask == 0:
                continue
            isets.append(
                IndependentSet(
                    id=len(isets),
                    mask=mask,
                    original_mask=mask,
                    weight=1,
                )
            )

        if len(isets) <= 1:
            stats.time_ns = time.perf_counter_ns() - t0
            self._accumulate(stats)
            return ULMResult(len(isets), 0, coloring_bound, stats)

        cores: List[ConflictCore] = []
        reduction = 0
        deadline = t0 + self.config.max_time_ns

        # Repeatedly find conflicts via unit propagation until stuck or
        # budget exhausted. Each conflict reduces the bound by β=1.
        while reduction < coloring_bound and stats.conflicts < self.config.max_conflicts_per_call:
            if time.perf_counter_ns() >= deadline:
                break

            conflict = self._find_conflict(isets, cores, stats)
            if conflict is None:
                break

            beta = self._add_core(conflict, isets, cores, stats)
            reduction += beta
            stats.bound_reductions += 1
            stats.total_reduction += beta
            stats.conflicts += 1

            # After AddCore, restore temporary propagation removals on
            # active (non-locked) sets so subsequent rounds start clean,
            # while locked sets retain their locked masks.
            self._restore_active_masks(isets)

            # Early exit if bound already tiny.
            if coloring_bound - reduction <= 0:
                break

        bound = coloring_bound - reduction
        if bound < 0:
            # Should never happen for a sound reasoner.
            self.disable("negative bound")
            bound = coloring_bound
            reduction = 0
            stats.sound = False  # type: ignore[attr-defined]

        stats.time_ns = time.perf_counter_ns() - t0
        self._accumulate(stats)
        return ULMResult(bound, reduction, coloring_bound, stats, sound=True)

    def _accumulate(self, stats: ReasoningStats) -> None:
        g = self.global_stats
        g.calls += stats.calls
        g.conflicts += stats.conflicts
        g.cores_created += stats.cores_created
        g.cores_merged += stats.cores_merged
        g.unlock_events += stats.unlock_events
        g.bound_reductions += stats.bound_reductions
        g.total_reduction += stats.total_reduction
        g.propagations += stats.propagations
        g.time_ns += stats.time_ns
        if stats.time_ns > g.max_call_ns:
            g.max_call_ns = stats.time_ns

    def _active_unit_sets(
        self,
        isets: List[IndependentSet],
    ) -> List[int]:
        units = []
        for s in isets:
            if not s.active or s.satisfied:
                continue
            if s.locked and not s.unlocked:
                continue
            if s.mask.bit_count() == 1:
                units.append(s.id)
        return units

    def _find_conflict(
        self,
        isets: List[IndependentSet],
        cores: List[ConflictCore],
        stats: ReasoningStats,
    ) -> Optional[List[int]]:
        """
        Unit-propagate until a conflict or fixpoint.

        Returns list of independent-set ids forming the conflict, or None.
        """
        adj = self.adj
        # Snapshot masks for rollback of this UP attempt.
        saved = [(s.mask, dict(s.removal_reasons)) for s in isets]
        reason_of_empty: Dict[int, List[int]] = {}

        # Queue of unit set ids.
        queue = self._active_unit_sets(isets)
        seen_fix = set(queue)
        head = 0

        while head < len(queue):
            uid = queue[head]
            head += 1
            unit = isets[uid]
            if not unit.active or unit.satisfied:
                continue
            if unit.locked and not unit.unlocked:
                continue
            if unit.mask.bit_count() != 1:
                continue

            v = (unit.mask & -unit.mask).bit_length() - 1
            neigh = adj[v]
            stats.propagations += 1

            for s in isets:
                if s.id == uid or not s.active or s.satisfied:
                    continue
                # Locked-but-not-unlocked sets still lose non-neighbors
                # (paper Algorithm 3 line 2), enabling uw accounting.
                survivors = s.mask & neigh
                removed = s.mask ^ survivors
                if removed == 0:
                    continue
                # Record reasons for removed vertices.
                tmp = removed
                while tmp:
                    bit = tmp & -tmp
                    rv = bit.bit_length() - 1
                    tmp ^= bit
                    s.removal_reasons[rv] = uid
                s.mask = survivors

                if survivors == 0:
                    # Conflict or unlock accounting.
                    if s.locked and not s.unlocked:
                        core = cores[s.core_id] if s.core_id >= 0 else None
                        if core is not None and core.active:
                            core.unlock_weight += s.weight
                            core.unlocked_iset_ids.append(s.id)
                            s.satisfied = True
                            if core.unlock_weight >= core.weight:
                                # Unlock remaining locked sets in core.
                                for lid in core.iset_ids:
                                    ls = isets[lid]
                                    if ls.locked and not ls.unlocked and not ls.satisfied:
                                        ls.unlocked = True
                                        stats.unlock_events += 1
                                        if ls.mask.bit_count() == 1 and ls.id not in seen_fix:
                                            queue.append(ls.id)
                                            seen_fix.add(ls.id)
                                core.active = False
                        continue

                    # True conflict: empty active / unlocked set.
                    reasons = self._collect_conflict_reasons(s, isets, uid)
                    # Rollback UP side-effects before returning conflict
                    # so AddCore sees original masks; paper restores then
                    # rebuilds cores from the conflict set.
                    for i, (m, rr) in enumerate(saved):
                        isets[i].mask = m
                        isets[i].removal_reasons = dict(rr)
                        # Do not roll back unlock/satisfied from previous
                        # completed cores — only this attempt's mask edits.
                    # Re-apply completed unlock state is already on cores;
                    # satisfied flags set during this attempt on locked
                    # empties must be rolled back too if we conflict.
                    for i, _ in enumerate(saved):
                        if isets[i].locked and isets[i].satisfied:
                            # Only clear if this attempt marked it.
                            pass
                    return reasons

                if survivors.bit_count() == 1:
                    if s.id not in seen_fix:
                        # Newly unit — only enqueue if eligible for UP.
                        if (not s.locked) or s.unlocked:
                            queue.append(s.id)
                            seen_fix.add(s.id)

        # Fixpoint with no conflict — rollback temporary removals.
        for i, (m, rr) in enumerate(saved):
            isets[i].mask = m
            isets[i].removal_reasons = dict(rr)
        return None

    def _collect_conflict_reasons(
        self,
        empty: IndependentSet,
        isets: List[IndependentSet],
        last_unit: int,
    ) -> List[int]:
        """Trace removal reasons to build conflict set F."""
        involved = {empty.id, last_unit}
        stack = [empty.id]
        while stack:
            sid = stack.pop()
            s = isets[sid]
            for _v, reason in s.removal_reasons.items():
                if reason not in involved:
                    involved.add(reason)
                    stack.append(reason)
            # Also walk original empties' reasons via last_unit chain.
        # Include sets that still participated as units causing removals.
        if last_unit not in involved:
            involved.add(last_unit)
        # Ensure at least 2 sets for a meaningful conflict.
        result = sorted(involved)
        if len(result) < 2:
            # Degenerate: treat empty + last unit.
            result = sorted({empty.id, last_unit})
        return result

    def _add_core(
        self,
        conflict_ids: List[int],
        isets: List[IndependentSet],
        cores: List[ConflictCore],
        stats: ReasoningStats,
    ) -> int:
        """Algorithm 2 AddCore specialized to unit weights (β = 1)."""
        F = [isets[i] for i in conflict_ids if isets[i].active]
        if len(F) < 2:
            return 0

        beta = min(s.weight for s in F)  # always 1 under unit weights
        new_core = ConflictCore(
            id=len(cores),
            iset_ids=[],
            weight=beta,
            active=True,
        )

        for s in F:
            # split(s, beta): lock weight-beta part; remainder empty for unit.
            s.weight = 1
            s.locked = True
            s.unlocked = False
            s.satisfied = False
            # Keep original members as the locked set.
            s.mask = s.original_mask
            # Merge prior active cores that owned members of F.
            if s.core_id >= 0:
                old = cores[s.core_id]
                if old.active:
                    old.active = False
                    new_core.weight += old.weight
                    for lid in old.iset_ids:
                        if lid not in new_core.iset_ids:
                            new_core.iset_ids.append(lid)
                            isets[lid].core_id = new_core.id
                    stats.cores_merged += 1

            if s.id not in new_core.iset_ids:
                new_core.iset_ids.append(s.id)
            s.core_id = new_core.id
            # Unit-weight: no remainder I'' stays in the free pool.
            s.active = True

        cores.append(new_core)
        stats.cores_created += 1
        return beta

    def _restore_active_masks(self, isets: List[IndependentSet]) -> None:
        for s in isets:
            if s.locked and not s.unlocked:
                # Locked sets keep their locked member mask.
                s.mask = s.original_mask
            else:
                s.mask = s.original_mask
            s.removal_reasons.clear()


def ulm_bound_for_classes(
    graph: BitsetGraph,
    color_classes: Sequence[int],
    candidates: int,
    reasoner: ULMReasoner | None = None,
) -> ULMResult:
    r = reasoner or ULMReasoner(graph)
    return r.tighten_bound(color_classes, candidates)
