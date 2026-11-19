"""NuMVC vertex-cover state: cover mask, uncovered edges, dscore, confChange."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .complement_graph import ComplementGraph
from .numvc_weights import EdgeWeights


@dataclass
class UncoveredEdgeSet:
    """Dynamic uncovered edge ID collection with O(1) add/remove/sample."""

    ids: List[int] = field(default_factory=list)
    pos: List[int] = field(default_factory=list)  # edge_id -> index in ids or -1

    def __len__(self) -> int:
        return len(self.ids)

    def clear(self, m: int) -> None:
        self.ids.clear()
        self.pos = [-1] * m

    def contains(self, e: int) -> bool:
        return 0 <= e < len(self.pos) and self.pos[e] >= 0

    def add(self, e: int) -> None:
        if self.pos[e] >= 0:
            return
        self.pos[e] = len(self.ids)
        self.ids.append(e)

    def remove(self, e: int) -> None:
        i = self.pos[e]
        if i < 0:
            return
        last = self.ids[-1]
        self.ids[i] = last
        self.pos[last] = i
        self.ids.pop()
        self.pos[e] = -1

    def sample(self, rng: random.Random) -> int:
        return self.ids[rng.randrange(len(self.ids))]


@dataclass
class NuMVCState:
    """Mutable MVC search state on a complement graph."""

    comp: ComplementGraph
    weights: EdgeWeights
    in_cover: List[bool]
    cover_members: List[int]
    cover_size: int
    dscore: List[int]
    conf_change: List[bool]
    age: List[int]  # last step vertex changed; older = smaller age
    uncovered: UncoveredEdgeSet
    step: int = 0
    use_conf_change: bool = True
    prevented_readditions: int = 0
    conf_updates: int = 0
    removals: int = 0
    additions: int = 0

    @classmethod
    def create(
        cls,
        comp: ComplementGraph,
        weights: EdgeWeights,
        *,
        use_conf_change: bool = True,
    ) -> "NuMVCState":
        n = comp.n
        m = comp.complement_edge_count
        st = cls(
            comp=comp,
            weights=weights,
            in_cover=[False] * n,
            cover_members=[],
            cover_size=0,
            dscore=[0] * n,
            conf_change=[True] * n,
            age=[0] * n,
            uncovered=UncoveredEdgeSet(),
            use_conf_change=use_conf_change,
        )
        st.uncovered.clear(m)
        # Initially empty cover: all edges uncovered
        for e in range(m):
            st.uncovered.add(e)
        st._recompute_all_dscores()
        return st

    def _recompute_all_dscores(self) -> None:
        """Full dscore from scratch (tests + after forgetting)."""
        n = self.comp.n
        w = self.weights.weights
        eu, ev = self.comp.edge_u, self.comp.edge_v
        ds = [0] * n
        in_c = self.in_cover
        for e in range(self.comp.complement_edge_count):
            u, v = eu[e], ev[e]
            we = w[e]
            iu, iv = in_c[u], in_c[v]
            if not iu and not iv:
                # uncovered: both outside gain we
                ds[u] += we
                ds[v] += we
            elif iu and not iv:
                # covered by u only: removing u uncovers
                ds[u] -= we
            elif iv and not iu:
                ds[v] -= we
            # both in cover: removing either still covered by other → no contrib
        self.dscore = ds

    def recompute_dscore_from_scratch(self) -> List[int]:
        self._recompute_all_dscores()
        return list(self.dscore)

    def cost(self) -> int:
        """Weighted uncovered cost."""
        w = self.weights.weights
        return sum(w[e] for e in self.uncovered.ids)

    def is_valid_cover(self) -> bool:
        return len(self.uncovered) == 0

    def cover_mask(self) -> int:
        m = 0
        for v, inside in enumerate(self.in_cover):
            if inside:
                m |= 1 << v
        return m

    def cover_list(self) -> List[int]:
        return [v for v, inside in enumerate(self.in_cover) if inside]

    def add_vertex(self, v: int) -> None:
        if self.in_cover[v]:
            return
        self.in_cover[v] = True
        self.cover_members.append(v)
        self.cover_size += 1
        self.additions += 1
        self.step += 1
        self.age[v] = self.step
        w = self.weights.weights
        adj_inc = self.comp.incident[v]
        eu, ev = self.comp.edge_u, self.comp.edge_v
        in_c = self.in_cover
        ds = self.dscore

        for e in adj_inc:
            u2 = eu[e]
            v2 = ev[e]
            other = v2 if u2 == v else u2
            we = w[e]
            if not in_c[other]:
                # was uncovered
                self.uncovered.remove(e)
                ds[other] -= we
                # v was outside; its outside-score from this edge goes away,
                # but v is now inside — handled after loop
            else:
                # was covered by other only; after add, covered by both
                # other no longer loses we if removed
                ds[other] += we

        # recompute dscore[v] as inside vertex
        score = 0
        for e in adj_inc:
            other = self.comp.edge_v[e] if self.comp.edge_u[e] == v else self.comp.edge_u[e]
            if not in_c[other]:
                score -= w[e]
        ds[v] = score

        # confChange: neighbors of v set to True
        if self.use_conf_change:
            for e in adj_inc:
                other = self.comp.edge_v[e] if self.comp.edge_u[e] == v else self.comp.edge_u[e]
                self.conf_change[other] = True
                self.conf_updates += 1

    def remove_vertex(self, v: int) -> None:
        if not self.in_cover[v]:
            return
        self.in_cover[v] = False
        # O(|C|) removal from member list — |C| ≪ n²
        try:
            self.cover_members.remove(v)
        except ValueError:
            pass
        self.cover_size -= 1
        self.removals += 1
        self.step += 1
        self.age[v] = self.step
        w = self.weights.weights
        adj_inc = self.comp.incident[v]
        in_c = self.in_cover
        ds = self.dscore

        for e in adj_inc:
            other = self.comp.edge_v[e] if self.comp.edge_u[e] == v else self.comp.edge_u[e]
            we = w[e]
            if not in_c[other]:
                # becomes uncovered
                self.uncovered.add(e)
                ds[other] += we
            else:
                # still covered by other; other now solely covers → dscore decreases
                ds[other] -= we

        # v now outside: dscore = sum uncovered incident weights
        score = 0
        for e in adj_inc:
            other = self.comp.edge_v[e] if self.comp.edge_u[e] == v else self.comp.edge_u[e]
            if not in_c[other]:
                score += w[e]
        ds[v] = score

        if self.use_conf_change:
            self.conf_change[v] = False
            for e in adj_inc:
                other = self.comp.edge_v[e] if self.comp.edge_u[e] == v else self.comp.edge_u[e]
                self.conf_change[other] = True
                self.conf_updates += 1

    def choose_remove_vertex(self, rng: random.Random, *, bms: int = 0) -> int:
        """Highest dscore in cover; ties → oldest (smallest age)."""
        ds = self.dscore
        age = self.age
        cover_vs = self.cover_members
        if not cover_vs:
            return -1
        if bms and bms > 0 and len(cover_vs) > bms:
            cand = [cover_vs[rng.randrange(len(cover_vs))] for _ in range(bms)]
            best = cand[0]
            for v in cand[1:]:
                if ds[v] > ds[best] or (ds[v] == ds[best] and age[v] < age[best]):
                    best = v
            return best

        best = cover_vs[0]
        best_score = ds[best]
        best_age = age[best]
        for v in cover_vs[1:]:
            if ds[v] > best_score or (ds[v] == best_score and age[v] < best_age):
                best = v
                best_score = ds[v]
                best_age = age[v]
        return best

    def choose_add_endpoint(self, e: int, rng: random.Random) -> int:
        """Choose eligible endpoint of uncovered edge e."""
        u = self.comp.edge_u[e]
        v = self.comp.edge_v[e]
        use_cc = self.use_conf_change
        cu = (not use_cc) or self.conf_change[u]
        cv = (not use_cc) or self.conf_change[v]
        if cu and not cv:
            return u
        if cv and not cu:
            return v
        if not cu and not cv:
            # Should not happen per Proposition 1 — count and fallback
            self.prevented_readditions += 1
            # emergency: pick higher dscore
            return u if self.dscore[u] >= self.dscore[v] else v
        # both eligible
        if self.dscore[u] > self.dscore[v]:
            return u
        if self.dscore[v] > self.dscore[u]:
            return v
        # tie → older (smaller age)
        if self.age[u] < self.age[v]:
            return u
        if self.age[v] < self.age[u]:
            return v
        return u if rng.random() < 0.5 else v

    def apply_weight_increments(self) -> None:
        """Increment weights of uncovered edges and update dscores of endpoints."""
        if not self.weights.enable_weights:
            return
        ids = list(self.uncovered.ids)  # snapshot
        if not ids:
            return
        w = self.weights.weights
        ds = self.dscore
        eu, ev = self.comp.edge_u, self.comp.edge_v
        for e in ids:
            w[e] += 1
            self.weights.total_weight += 1
            self.weights.weight_increments += 1
            # both endpoints outside → their dscore increases by 1
            ds[eu[e]] += 1
            ds[ev[e]] += 1

    def apply_forgetting_if_needed(self) -> bool:
        forgot = self.weights.maybe_forget()
        if forgot:
            self._recompute_all_dscores()
        return forgot

    def greedy_construct(self, rng: random.Random) -> None:
        """Greedy init: repeatedly add highest-dscore outside vertex until valid."""
        # Start from empty (already)
        while not self.is_valid_cover():
            best = -1
            best_s = -1
            # among outside
            for v in range(self.comp.n):
                if self.in_cover[v]:
                    continue
                if self.dscore[v] > best_s:
                    best_s = self.dscore[v]
                    best = v
                elif self.dscore[v] == best_s and best >= 0 and rng.random() < 0.5:
                    best = v
            if best < 0:
                break
            self.add_vertex(best)
        # remove redundant: vertices with dscore == 0 can be removed safely
        improved = True
        while improved:
            improved = False
            for v in range(self.comp.n):
                if self.in_cover[v] and self.dscore[v] == 0:
                    self.remove_vertex(v)
                    improved = True
                    break
