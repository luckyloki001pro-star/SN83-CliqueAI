"""Independent reactive local-search agent for R-EVO (inspired / simplified)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .bitset import bits_to_list, list_to_mask
from .competitive_search import compute_C0, compute_C1
from .graph import BitsetGraph
from .greedy import extend_to_maximal, greedy_maximal_from_start
from .revo_model import ProbabilityModel
from .validation import is_clique, is_maximal_clique


@dataclass
class SearcherStats:
    moves: int = 0
    adds: int = 0
    drops: int = 0
    plateau_moves: int = 0
    tabu_blocks: int = 0
    restarts: int = 0
    improvements: int = 0
    improvement_after_restart: int = 0
    model_guided_restarts: int = 0
    model_guided_restart_improvements: int = 0
    last_improvement_step: int = 0
    last_restart_step: int = 0


@dataclass
class ReactiveSearcher:
    searcher_id: int
    graph: BitsetGraph
    rng: random.Random
    tabu_ratio: float = 0.20
    restart_factor: int = 100
    use_model: bool = True
    epsilon_floor: float = 0.0
    random_restart_probability: float = 0.0
    allow_aspiration: bool = False

    current: List[int] = field(default_factory=list)
    best: List[int] = field(default_factory=list)
    best_size: int = 0
    tabu_until: List[int] = field(default_factory=list)
    move_count: int = 0
    stats: SearcherStats = field(default_factory=SearcherStats)
    _just_restarted: bool = False

    def __post_init__(self) -> None:
        n = self.graph.n
        if not self.tabu_until:
            self.tabu_until = [0] * n

    def tabu_tenure(self, best_size: Optional[int] = None) -> int:
        bs = best_size if best_size is not None else max(self.best_size, 1)
        return max(1, int(round(self.tabu_ratio * bs)))

    def restart_threshold(self) -> int:
        return max(1, self.restart_factor * max(self.best_size, 1))

    def is_tabu(self, v: int) -> bool:
        return self.tabu_until[v] > self.move_count

    def mark_tabu(self, v: int, tenure: Optional[int] = None) -> None:
        t = tenure if tenure is not None else self.tabu_tenure()
        self.tabu_until[v] = self.move_count + t

    def _set_current(self, clique: Sequence[int], *, count_as_restart: bool = False) -> None:
        self.current = list(clique)
        if is_clique(self.graph, self.current):
            # personal best only from maximal verified
            maximal = extend_to_maximal(self.graph, self.current)
            if is_maximal_clique(self.graph, maximal) and len(maximal) > self.best_size:
                self.best = sorted(maximal)
                self.best_size = len(self.best)
                self.stats.improvements += 1
                self.stats.last_improvement_step = self.move_count
                if count_as_restart or self._just_restarted:
                    self.stats.improvement_after_restart += 1
                    if self.use_model:
                        self.stats.model_guided_restart_improvements += 1
                self._just_restarted = False

    def initialize_random(self) -> None:
        if self.graph.n == 0:
            self.current = []
            self.best = []
            self.best_size = 0
            return
        start = self.rng.randrange(self.graph.n)
        clq = greedy_maximal_from_start(self.graph, start)
        self._set_current(clq)
        self.stats.last_restart_step = self.move_count

    def build_from_probability(
        self,
        model: Optional[ProbabilityModel],
        *,
        force_uniform: bool = False,
    ) -> List[int]:
        """Probability-guided clique construction (exact intersection)."""
        n = self.graph.n
        if n == 0:
            return []
        use_uniform = force_uniform or model is None or not self.use_model
        probs = model.probability if model is not None else [0.5] * n
        floor = self.epsilon_floor if not use_uniform else 0.0

        clique: List[int] = []
        cand = self.graph.all_vertices_mask()
        while cand:
            verts = bits_to_list(cand)
            if use_uniform:
                v = self.rng.choice(verts)
            else:
                weights = []
                for u in verts:
                    w = probs[u]
                    if floor > 0.0:
                        w = max(w, floor)
                    weights.append(max(w, 1e-12))
                total = sum(weights)
                r = self.rng.random() * total
                acc = 0.0
                v = verts[-1]
                for u, w in zip(verts, weights):
                    acc += w
                    if r <= acc:
                        v = u
                        break
            clique.append(v)
            cand &= self.graph.adjacency[v]
        return extend_to_maximal(self.graph, clique)

    def restart(self, model: Optional[ProbabilityModel] = None) -> None:
        self.stats.restarts += 1
        self.stats.last_restart_step = self.move_count
        self._just_restarted = True
        # clear tabu on restart
        self.tabu_until = [0] * self.graph.n
        if (
            self.use_model
            and model is not None
            and self.rng.random() >= self.random_restart_probability
        ):
            self.stats.model_guided_restarts += 1
            clq = self.build_from_probability(model, force_uniform=False)
        else:
            clq = self.build_from_probability(model, force_uniform=True)
        self._set_current(clq, count_as_restart=True)

    def _pick_add(self, pa_mask: int) -> int:
        if pa_mask == 0:
            return -1
        verts = bits_to_list(pa_mask)
        free = [v for v in verts if not self.is_tabu(v)]
        if not free:
            if self.allow_aspiration:
                free = verts
            else:
                self.stats.tabu_blocks += 1
                return -1
        # residual connectivity among PA
        best_v = free[0]
        best_sc = -1
        adj = self.graph.adjacency
        for v in free:
            sc = (pa_mask & adj[v]).bit_count()
            if sc > best_sc:
                best_sc = sc
                best_v = v
        return best_v

    def _pick_drop(self) -> int:
        if not self.current:
            return -1
        free = [v for v in self.current if not self.is_tabu(v)]
        if not free:
            if self.allow_aspiration:
                free = list(self.current)
            else:
                self.stats.tabu_blocks += 1
                # forced fallback
                return self.rng.choice(self.current)
        # Prefer drop that maximizes new C0 after removal (approx via C1 openings)
        c1 = compute_C1(self.graph, self.current)
        conflict_count = {v: 0 for v in self.current}
        for _cand, conf in c1:
            conflict_count[conf] = conflict_count.get(conf, 0) + 1
        # higher conflict_count → removing opens more C1/C0 opportunities
        best_v = free[0]
        best_sc = -1
        for v in free:
            sc = conflict_count.get(v, 0)
            if sc > best_sc:
                best_sc = sc
                best_v = v
        return best_v

    def step(self) -> None:
        """One reactive local-search move (add, plateau, or drop)."""
        g = self.graph
        if g.n == 0:
            return
        if not self.current:
            self.initialize_random()
            return

        self.move_count += 1
        self.stats.moves += 1
        pa = compute_C0(g, self.current)

        # Try add
        v = self._pick_add(pa)
        if v >= 0:
            self.current.append(v)
            self.mark_tabu(v)
            self.stats.adds += 1
            # update personal best if improved maximal
            maximal = extend_to_maximal(g, self.current)
            if len(maximal) > self.best_size and is_maximal_clique(g, maximal):
                self.best = sorted(maximal)
                self.best_size = len(self.best)
                self.stats.improvements += 1
                self.stats.last_improvement_step = self.move_count
                if self._just_restarted:
                    self.stats.improvement_after_restart += 1
                    if self.use_model:
                        self.stats.model_guided_restart_improvements += 1
                    self._just_restarted = False
            return

        # Plateau via C1: remove conflict, add candidate
        c1 = compute_C1(g, self.current)
        free_c1 = [(c, conf) for c, conf in c1 if not self.is_tabu(c) and not self.is_tabu(conf)]
        if not free_c1 and c1 and self.allow_aspiration:
            free_c1 = c1
        if free_c1:
            # prefer residual among PA after swap (proxy: random among free)
            cand, conf = self.rng.choice(free_c1)
            new_clique = [x for x in self.current if x != conf] + [cand]
            if is_clique(g, new_clique):
                self.current = new_clique
                self.mark_tabu(cand)
                self.mark_tabu(conf)
                self.stats.plateau_moves += 1
                return

        # Drop
        d = self._pick_drop()
        if d >= 0 and d in self.current:
            self.current = [x for x in self.current if x != d]
            self.mark_tabu(d)
            self.stats.drops += 1
            return

        # Deadlock fallback: random restart of current from a clique vertex
        if self.current:
            keep = self.rng.choice(self.current)
            self.current = greedy_maximal_from_start(g, keep)

    def stagnated(self) -> bool:
        steps_since = self.move_count - self.stats.last_improvement_step
        return steps_since >= self.restart_threshold()

    def verified_best(self) -> List[int]:
        if not self.best:
            return []
        if is_clique(self.graph, self.best) and is_maximal_clique(self.graph, self.best):
            return list(self.best)
        # repair
        repaired = extend_to_maximal(self.graph, self.best)
        if is_maximal_clique(self.graph, repaired):
            return sorted(repaired)
        return []
