"""Phase-3 competitive local-search solvers (simplified pure-Python adaptations).

Methods (NOT claimed as line-by-line paper reproductions):
  H  pls_penalty          — Phased Local Search style (Pullan)
  G  bls_adaptive         — Breakout Local Search style (Benlic & Hao)
  I  ikls_variable_depth  — Iterated variable-depth / k-opt style (Katayama et al.)
  J  pair_anchor          — Pair-anchored common-neighbor exploration
  P  adaptive_portfolio   — Time-sliced portfolio of G/H/I/J

References studied (ideas only; licenses not copied as source):
  - Phased Local Search (Pullan)
  - Dynamic Local Search / DLS-MC (Pullan & Hoos)
  - Breakout Local Search (Benlic & Hao)
  - Iterated k-opt / LEC-Kick (Katayama et al.)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .bitset import bits_to_list, list_to_mask
from .graph import BitsetGraph
from .greedy import extend_to_maximal, greedy_maximal_from_start
from .validation import is_clique, is_maximal_clique

CHECKPOINT_SECONDS = (0.1, 0.5, 1.0, 2.0, 3.0, 5.0)


class CompetitiveVariant(str, Enum):
    PLS_PENALTY = "pls_penalty"
    BLS_ADAPTIVE = "bls_adaptive"
    IKLS_VARIABLE_DEPTH = "ikls_variable_depth"
    PAIR_ANCHOR = "pair_anchor"
    ADAPTIVE_PORTFOLIO = "adaptive_portfolio"


@dataclass
class CompetitiveStats:
    constructions: int = 0
    plateau_moves: int = 0
    useful_plateau_moves: int = 0
    add_moves: int = 0
    perturbations: int = 0
    avg_perturbation_strength: float = 0.0
    perturbation_strength_sum: int = 0
    revisited_states: int = 0
    successful_escapes: int = 0
    phase_transitions: int = 0
    penalty_updates: int = 0
    variable_depth_sequences: int = 0
    variable_depth_improvements: int = 0
    pair_starts: int = 0
    unique_cliques: int = 0
    incumbent_improvements: int = 0
    time_to_first_ms: float = 0.0
    time_to_best_ms: float = 0.0
    local_search_time_ms: float = 0.0
    perturbation_time_ms: float = 0.0
    pair_prep_time_ms: float = 0.0
    deadline_reached: bool = False
    search_incomplete_at_deadline: bool = False
    response_deadline_violation: bool = False
    total_ms: float = 0.0
    improvement_history: List[Dict[str, float]] = field(default_factory=list)
    checkpoints: Dict[str, Optional[int]] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompetitiveResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    variant: str
    stats: CompetitiveStats


@dataclass
class CompetitiveConfig:
    variant: CompetitiveVariant = CompetitiveVariant.PLS_PENALTY
    seed: int = 42
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    elite_pool_size: int = 24
    # PLS
    pls_steps_random: int = 50
    pls_steps_degree: int = 50
    pls_steps_penalty: int = 100
    penalty_decay_period: int = 100
    # BLS
    bls_L_min: int = 2
    bls_L_max: int = 8
    bls_tabu_tenure: int = 7
    bls_stagnation_limit: int = 40
    # IKLS
    ikls_depth_limit: int = 12
    ikls_kick_removals: int = 2
    # Pair anchor
    pair_top_k: int = 64
    pair_sample: int = 4000
    # Portfolio fractions (must sum ~1)
    portfolio_fracs: Tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)


class DiverseElitePool:
    """Elite pool preferring large, structurally diverse maximal cliques."""

    def __init__(self, capacity: int = 24) -> None:
        self.capacity = capacity
        # (size, key, discovery_ms)
        self._items: List[Tuple[int, Tuple[int, ...], float]] = []
        self._seen: set[Tuple[int, ...]] = set()

    @staticmethod
    def overlap(a: Sequence[int], b: Sequence[int]) -> float:
        sa, sb = set(a), set(b)
        if not sa and not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def add(self, clique: Sequence[int], discovery_ms: float = 0.0) -> bool:
        key = tuple(sorted(clique))
        if not key or key in self._seen:
            return False
        self._seen.add(key)
        self._items.append((len(key), key, discovery_ms))
        self._items.sort(key=lambda x: (-x[0], x[2], x[1]))
        if len(self._items) > self.capacity:
            # Drop most overlapping among smallest / oldest near-best
            self._prune()
        return True

    def _prune(self) -> None:
        while len(self._items) > self.capacity:
            # Prefer dropping high-overlap duplicates among non-unique-best
            best_size = self._items[0][0]
            drop_i = len(self._items) - 1
            worst_ov = -1.0
            for i in range(1, len(self._items)):
                ov = max(
                    self.overlap(self._items[i][1], self._items[j][1])
                    for j in range(i)
                )
                if ov > worst_ov or (ov == worst_ov and self._items[i][0] < best_size):
                    worst_ov = ov
                    drop_i = i
            _, key, _ = self._items.pop(drop_i)
            self._seen.discard(key)

    def best(self) -> List[int]:
        return list(self._items[0][1]) if self._items else []

    def best_size(self) -> int:
        return self._items[0][0] if self._items else 0

    def sample_best_sized(self, rng: random.Random, mode: str = "first") -> List[int]:
        if not self._items:
            return []
        best_size = self._items[0][0]
        cands = [it for it in self._items if it[0] == best_size]
        if mode == "first":
            return list(cands[0][1])
        if mode == "random":
            return list(rng.choice(cands)[1])
        if mode == "hash":
            cands = sorted(cands, key=lambda x: hash(x[1]))
            return list(cands[0][1])
        if mode == "diverse":
            # lowest mean overlap with other best-sized
            def mean_ov(it):
                others = [o for o in cands if o is not it]
                if not others:
                    return 0.0
                return sum(self.overlap(it[1], o[1]) for o in others) / len(others)

            cands = sorted(cands, key=mean_ov)
            return list(cands[0][1])
        return list(cands[0][1])

    def __len__(self) -> int:
        return len(self._items)


def _checkpoints(history: List[Dict[str, float]], timeout: float, final_size: int) -> Dict[str, Optional[int]]:
    out: Dict[str, Optional[int]] = {}
    for sec in CHECKPOINT_SECONDS:
        if sec > timeout + 1e-9:
            out[f"{sec:g}s"] = None
            continue
        size = 0
        t_ms = sec * 1000.0
        for row in history:
            if row["time_ms"] <= t_ms + 1e-9:
                size = int(row["size"])
            else:
                break
        out[f"{sec:g}s"] = size if history else 0
    out["deadline"] = final_size
    return out


def compute_C0(graph: BitsetGraph, clique: Sequence[int]) -> int:
    """Vertices outside clique adjacent to every clique member."""
    if not clique:
        return graph.all_vertices_mask()
    common = graph.all_vertices_mask()
    adj = graph.adjacency
    for v in clique:
        common &= adj[v]
    return common & ~list_to_mask(clique)


def compute_C1(
    graph: BitsetGraph, clique: Sequence[int]
) -> List[Tuple[int, int]]:
    """Return list of (candidate, conflicting_clique_vertex) with exactly one missing edge."""
    if not clique:
        return []
    adj = graph.adjacency
    clique_mask = list_to_mask(clique)
    out: List[Tuple[int, int]] = []
    # For each clique vertex v, find verts adjacent to all others but not v.
    for v in clique:
        common = graph.all_vertices_mask()
        for u in clique:
            if u == v:
                continue
            common &= adj[u]
        # Must NOT be adjacent to v, and outside clique
        cands = common & ~adj[v] & ~clique_mask
        tmp = cands
        while tmp:
            bit = tmp & -tmp
            w = bit.bit_length() - 1
            tmp ^= bit
            out.append((w, v))
    return out


def pick_from_mask(
    mask: int,
    rng: random.Random,
    mode: str,
    graph: BitsetGraph,
    penalties: Optional[List[float]] = None,
    tabu: Optional[set] = None,
) -> int:
    if mask == 0:
        return -1
    verts = bits_to_list(mask)
    if tabu:
        free = [v for v in verts if v not in tabu]
        if free:
            verts = free
    if not verts:
        return -1
    if mode == "random":
        return rng.choice(verts)
    if mode == "degree":
        # residual degree inside mask
        best_v = verts[0]
        best = -1
        adj = graph.adjacency
        for v in verts:
            sc = (mask & adj[v]).bit_count()
            if sc > best:
                best = sc
                best_v = v
        return best_v
    if mode == "penalty":
        penalties = penalties or [0.0] * graph.n
        # prefer high residual degree - penalty
        adj = graph.adjacency
        best_v = verts[0]
        best = float("-inf")
        for v in verts:
            sc = (mask & adj[v]).bit_count() - penalties[v]
            if sc > best:
                best = sc
                best_v = v
        return best_v
    return rng.choice(verts)


def greedy_extend_from(graph: BitsetGraph, seed_clique: Sequence[int], rng: random.Random) -> List[int]:
    if not seed_clique:
        start = rng.randrange(graph.n) if graph.n else -1
        if start < 0:
            return []
        return greedy_maximal_from_start(graph, start)
    cur = list(seed_clique)
    while True:
        c0 = compute_C0(graph, cur)
        if c0 == 0:
            break
        v = pick_from_mask(c0, rng, "degree", graph)
        if v < 0:
            break
        cur.append(v)
    return sorted(cur)


# ---------------------------------------------------------------------------
# Method H — PLS-style phased local search
# ---------------------------------------------------------------------------


def _pls_step(
    graph: BitsetGraph,
    clique: List[int],
    rng: random.Random,
    mode: str,
    penalties: List[float],
    stats: CompetitiveStats,
) -> Tuple[List[int], bool]:
    """One PLS move: add from C0 or plateau swap from C1. Returns (clique, useful_plateau)."""
    useful = False
    c0 = compute_C0(graph, clique)
    if c0:
        v = pick_from_mask(c0, rng, mode if mode != "penalty" else "penalty", graph, penalties)
        if v >= 0:
            clique.append(v)
            stats.add_moves += 1
            if mode == "penalty":
                penalties[v] += 1.0
                stats.penalty_updates += 1
            return clique, False
    c1 = compute_C1(graph, clique)
    if not c1:
        return clique, False
    if mode == "random":
        w, conflict = rng.choice(c1)
    elif mode == "degree":
        best = None
        best_sc = -1
        adj = graph.adjacency
        rem_mask_base = list_to_mask(clique)
        for cand, conf in c1:
            # residual among C0-after roughly: neighbors outside
            sc = adj[cand].bit_count()
            if sc > best_sc:
                best_sc = sc
                best = (cand, conf)
        w, conflict = best if best else c1[0]
    else:  # penalty
        best = None
        best_sc = float("-inf")
        for cand, conf in c1:
            sc = graph.adjacency[cand].bit_count() - penalties[cand]
            if sc > best_sc:
                best_sc = sc
                best = (cand, conf)
        w, conflict = best if best else c1[0]
    # plateau swap
    new_clique = [u for u in clique if u != conflict] + [w]
    if not is_clique(graph, new_clique):
        return clique, False
    stats.plateau_moves += 1
    # useful if unlocks a C0 add
    if compute_C0(graph, new_clique):
        useful = True
        stats.useful_plateau_moves += 1
        # immediately take a C0 add
        c0b = compute_C0(graph, new_clique)
        v = pick_from_mask(c0b, rng, mode if mode != "penalty" else "penalty", graph, penalties)
        if v >= 0:
            new_clique.append(v)
            stats.add_moves += 1
    if mode == "penalty":
        penalties[w] += 1.0
        stats.penalty_updates += 1
    return new_clique, useful


def solve_pls(graph: BitsetGraph, cfg: CompetitiveConfig, deadline: float, t0: float, shared: Optional[dict] = None) -> CompetitiveResult:
    rng = random.Random(cfg.seed)
    stats = CompetitiveStats()
    elite = (shared or {}).get("elite") or DiverseElitePool(cfg.elite_pool_size)
    penalties = [0.0] * graph.n
    # start
    start = max(range(graph.n), key=lambda v: graph.adjacency[v].bit_count()) if graph.n else -1
    cur = greedy_maximal_from_start(graph, start) if start >= 0 else []
    stats.constructions += 1
    best = list(cur)
    hist: List[Dict[str, float]] = []

    def consider(clq: Sequence[int]) -> None:
        nonlocal best
        if not clq or not is_clique(graph, clq):
            return
        clq = extend_to_maximal(graph, clq)
        now = (time.perf_counter() - t0) * 1000.0
        elite.add(clq, now)
        if len(clq) > len(best):
            best = list(clq)
            stats.incumbent_improvements += 1
            hist.append({"time_ms": now, "size": float(len(best))})
            if stats.incumbent_improvements == 1:
                stats.time_to_first_ms = now
            stats.time_to_best_ms = now

    consider(cur)
    schedule = (
        [("random", cfg.pls_steps_random)]
        + [("degree", cfg.pls_steps_degree)]
        + [("penalty", cfg.pls_steps_penalty)]
    )
    steps_since_decay = 0
    seen: set[Tuple[int, ...]] = set()

    while time.perf_counter() < deadline and graph.n:
        for mode, nsteps in schedule:
            stats.phase_transitions += 1
            for _ in range(nsteps):
                if time.perf_counter() >= deadline:
                    break
                before = len(cur)
                key = tuple(sorted(cur))
                if key in seen:
                    stats.revisited_states += 1
                else:
                    seen.add(key)
                t_ls = time.perf_counter()
                cur, _ = _pls_step(graph, list(cur), rng, mode, penalties, stats)
                stats.local_search_time_ms += (time.perf_counter() - t_ls) * 1000.0
                if len(cur) > before:
                    consider(cur)
                elif len(cur) == before:
                    # still consider for elite diversity of equal size after maximal
                    if is_clique(graph, cur):
                        elite.add(extend_to_maximal(graph, cur), (time.perf_counter() - t0) * 1000.0)
                steps_since_decay += 1
                if steps_since_decay >= cfg.penalty_decay_period:
                    for i in range(graph.n):
                        penalties[i] *= 0.5
                    steps_since_decay = 0
                    stats.penalty_updates += 1
            if time.perf_counter() >= deadline:
                break
        # mild restart if stuck
        if time.perf_counter() < deadline:
            if rng.random() < 0.15:
                cur = greedy_maximal_from_start(graph, rng.randrange(graph.n))
                stats.constructions += 1
                consider(cur)

    best = elite.sample_best_sized(rng, mode="diverse") or extend_to_maximal(graph, best)
    return _finalize(graph, best, CompetitiveVariant.PLS_PENALTY.value, stats, hist, cfg, t0, elite, deadline)


# ---------------------------------------------------------------------------
# Method G — BLS-style adaptive breakout
# ---------------------------------------------------------------------------


def _bls_local_improve(
    graph: BitsetGraph,
    clique: List[int],
    rng: random.Random,
    tabu: Dict[int, int],
    iteration: int,
    stats: CompetitiveStats,
) -> List[int]:
    cur = list(clique)
    stalled = 0
    plateau_steps = 0
    max_plateau = 24
    for _ in range(64):  # hard cap — prevents infinite C1 cycling
        c0 = compute_C0(graph, cur)
        free = c0
        # respect tabu unless aspiration (improves best later handled outside)
        tmp = free
        allowed = 0
        while tmp:
            bit = tmp & -tmp
            v = bit.bit_length() - 1
            tmp ^= bit
            if tabu.get(v, -1) < iteration:
                allowed |= 1 << v
        use = allowed if allowed else free
        if use:
            v = pick_from_mask(use, rng, "degree", graph)
            if v >= 0:
                cur.append(v)
                stats.add_moves += 1
                stalled = 0
                plateau_steps = 0
                continue
        # plateau C1 swap
        c1 = compute_C1(graph, cur)
        c1 = [(w, c) for w, c in c1 if tabu.get(w, -1) < iteration] or c1
        if not c1:
            break
        if plateau_steps >= max_plateau:
            break
        w, conflict = rng.choice(c1)
        nxt = [u for u in cur if u != conflict] + [w]
        if is_clique(graph, nxt):
            stats.plateau_moves += 1
            plateau_steps += 1
            if compute_C0(graph, nxt):
                stats.useful_plateau_moves += 1
                plateau_steps = 0
            cur = nxt
            stalled = 0
        else:
            stalled += 1
            if stalled >= 8:
                break
    return cur


def _bls_perturb(
    graph: BitsetGraph,
    clique: List[int],
    rng: random.Random,
    L: int,
    directed: bool,
    tabu: Dict[int, int],
    iteration: int,
    tenure: int,
    stats: CompetitiveStats,
) -> List[int]:
    t_p = time.perf_counter()
    cur = list(clique)
    for _ in range(max(1, L)):
        if len(cur) <= 1:
            break
        if directed:
            # remove vertex with fewest neighbors outside / lowest residual to C1 region
            c1 = compute_C1(graph, cur)
            conflict_counts = {v: 0 for v in cur}
            for _, conf in c1:
                conflict_counts[conf] = conflict_counts.get(conf, 0) + 1
            # drop vertex that is conflict target most often (opens C1 space)
            rem = max(cur, key=lambda v: (conflict_counts.get(v, 0), -graph.adjacency[v].bit_count()))
        else:
            rem = rng.choice(cur)
        cur = [u for u in cur if u != rem]
        tabu[rem] = iteration + tenure
        # optional random C1 insert to diversify
        c1 = compute_C1(graph, cur)
        if c1 and rng.random() < 0.5:
            w, conf = rng.choice(c1)
            if conf in cur:
                trial = [u for u in cur if u != conf] + [w]
                if is_clique(graph, trial):
                    cur = trial
                    tabu[w] = iteration + tenure
    stats.perturbations += 1
    stats.perturbation_strength_sum += L
    stats.perturbation_time_ms += (time.perf_counter() - t_p) * 1000.0
    return cur if cur else [rng.randrange(graph.n)]


def solve_bls(graph: BitsetGraph, cfg: CompetitiveConfig, deadline: float, t0: float, shared: Optional[dict] = None) -> CompetitiveResult:
    rng = random.Random(cfg.seed + 17)
    stats = CompetitiveStats()
    elite = (shared or {}).get("elite") or DiverseElitePool(cfg.elite_pool_size)
    start = max(range(graph.n), key=lambda v: graph.adjacency[v].bit_count()) if graph.n else -1
    cur = greedy_maximal_from_start(graph, start) if start >= 0 else []
    stats.constructions += 1
    best = list(cur)
    hist: List[Dict[str, float]] = []
    tabu: Dict[int, int] = {}
    L = cfg.bls_L_min
    iteration = 0
    no_improve = 0
    seen: set[Tuple[int, ...]] = set()

    def consider(clq: Sequence[int]) -> bool:
        nonlocal best, no_improve, L
        if not clq or not is_clique(graph, clq):
            return False
        clq = extend_to_maximal(graph, clq)
        now = (time.perf_counter() - t0) * 1000.0
        elite.add(clq, now)
        if len(clq) > len(best):
            best = list(clq)
            no_improve = 0
            L = cfg.bls_L_min
            stats.incumbent_improvements += 1
            hist.append({"time_ms": now, "size": float(len(best))})
            if stats.incumbent_improvements == 1:
                stats.time_to_first_ms = now
            stats.time_to_best_ms = now
            return True
        no_improve += 1
        return False

    consider(cur)

    while time.perf_counter() < deadline and graph.n:
        iteration += 1
        key = tuple(sorted(cur))
        if key in seen:
            stats.revisited_states += 1
        else:
            seen.add(key)
        t_ls = time.perf_counter()
        cur = _bls_local_improve(graph, cur, rng, tabu, iteration, stats)
        stats.local_search_time_ms += (time.perf_counter() - t_ls) * 1000.0
        improved = consider(cur)
        if improved:
            L = max(cfg.bls_L_min, L - 1)
            stats.successful_escapes += 1
        if no_improve >= cfg.bls_stagnation_limit or (
            compute_C0(graph, cur) == 0 and not compute_C1(graph, cur)
        ):
            # adaptive L
            if stats.revisited_states > max(1, iteration // 3):
                L = min(cfg.bls_L_max, L + 1)
                directed = False
            else:
                directed = True
            cur = _bls_perturb(
                graph, cur if cur else best, rng, L, directed, tabu, iteration, cfg.bls_tabu_tenure, stats
            )
            cur = greedy_extend_from(graph, cur, rng)
            consider(cur)
            no_improve = 0

    if stats.perturbations:
        stats.avg_perturbation_strength = stats.perturbation_strength_sum / stats.perturbations
    best = elite.sample_best_sized(rng, mode="diverse") or extend_to_maximal(graph, best)
    return _finalize(graph, best, CompetitiveVariant.BLS_ADAPTIVE.value, stats, hist, cfg, t0, elite, deadline)


# ---------------------------------------------------------------------------
# Method I — IKLS-style variable-depth search
# ---------------------------------------------------------------------------


def _lec_kick(graph: BitsetGraph, clique: Sequence[int], rng: random.Random, k: int) -> List[int]:
    """Simplified LEC-inspired kick: drop vertices with lowest external connectivity.

    Not a line-by-line LEC-Kick reproduction; approximates 'lowest edges connectivity'
    by scoring clique verts via outside-neighbor count within the non-clique set.
    """
    if not clique:
        return []
    clique_mask = list_to_mask(clique)
    outside = graph.all_vertices_mask() & ~clique_mask
    scored = []
    for v in clique:
        # edges from v into outside
        scored.append(((graph.adjacency[v] & outside).bit_count(), v))
    scored.sort()  # lowest external connectivity first
    drop = {v for _, v in scored[: max(1, min(k, len(scored)))]}
    # optionally keep one random high-connectivity vertex if everything dropped
    keep = [v for v in clique if v not in drop]
    if not keep:
        keep = [max(clique, key=lambda v: graph.adjacency[v].bit_count())]
    return keep


def _variable_depth(
    graph: BitsetGraph,
    clique: List[int],
    rng: random.Random,
    depth_limit: int,
    deadline: float,
    stats: CompetitiveStats,
) -> List[int]:
    """Bounded add/drop sequence; commit best intermediate size."""
    stats.variable_depth_sequences += 1
    cur = list(clique)
    best_state = list(cur)
    best_size = len(cur)
    for depth in range(depth_limit):
        if time.perf_counter() >= deadline:
            break
        c0 = compute_C0(graph, cur)
        if c0:
            v = pick_from_mask(c0, rng, "degree", graph)
            if v >= 0:
                cur.append(v)
                stats.add_moves += 1
                if len(cur) > best_size:
                    best_size = len(cur)
                    best_state = list(cur)
                continue
        c1 = compute_C1(graph, cur)
        if c1:
            # try a few plateau swaps, then maybe drop
            w, conf = rng.choice(c1)
            trial = [u for u in cur if u != conf] + [w]
            if is_clique(graph, trial):
                stats.plateau_moves += 1
                cur = trial
                if compute_C0(graph, cur):
                    stats.useful_plateau_moves += 1
                continue
        # forced drop of lowest-LEC vertex then continue
        if len(cur) <= 1:
            break
        cur = _lec_kick(graph, cur, rng, 1)
    if best_size > len(clique):
        stats.variable_depth_improvements += 1
    return best_state if best_size >= len(clique) else clique


def solve_ikls(graph: BitsetGraph, cfg: CompetitiveConfig, deadline: float, t0: float, shared: Optional[dict] = None) -> CompetitiveResult:
    rng = random.Random(cfg.seed + 31)
    stats = CompetitiveStats()
    elite = (shared or {}).get("elite") or DiverseElitePool(cfg.elite_pool_size)
    start = rng.randrange(graph.n) if graph.n else -1
    cur = greedy_maximal_from_start(graph, start) if start >= 0 else []
    stats.constructions += 1
    best = list(cur)
    hist: List[Dict[str, float]] = []

    def consider(clq: Sequence[int]) -> None:
        nonlocal best
        if not clq or not is_clique(graph, clq):
            return
        clq = extend_to_maximal(graph, clq)
        now = (time.perf_counter() - t0) * 1000.0
        elite.add(clq, now)
        if len(clq) > len(best):
            best = list(clq)
            stats.incumbent_improvements += 1
            hist.append({"time_ms": now, "size": float(len(best))})
            if stats.incumbent_improvements == 1:
                stats.time_to_first_ms = now
            stats.time_to_best_ms = now

    consider(cur)
    stall = 0
    while time.perf_counter() < deadline and graph.n:
        t_ls = time.perf_counter()
        nxt = _variable_depth(graph, cur, rng, cfg.ikls_depth_limit, deadline, stats)
        stats.local_search_time_ms += (time.perf_counter() - t_ls) * 1000.0
        before = len(best)
        consider(nxt)
        if len(best) > before:
            cur = list(best)
            stall = 0
        else:
            stall += 1
            cur = nxt
        if stall >= 6:
            # LEC kick + rebuild
            stats.perturbations += 1
            core = _lec_kick(graph, best, rng, cfg.ikls_kick_removals)
            cur = greedy_extend_from(graph, core, rng)
            stats.constructions += 1
            consider(cur)
            stall = 0
        elif rng.random() < 0.08:
            cur = greedy_maximal_from_start(graph, rng.randrange(graph.n))
            stats.constructions += 1
            consider(cur)

    best = elite.sample_best_sized(rng, mode="diverse") or extend_to_maximal(graph, best)
    return _finalize(graph, best, CompetitiveVariant.IKLS_VARIABLE_DEPTH.value, stats, hist, cfg, t0, elite, deadline)


# ---------------------------------------------------------------------------
# Method J — Pair-anchored exploration
# ---------------------------------------------------------------------------


def _select_pairs(graph: BitsetGraph, cfg: CompetitiveConfig, rng: random.Random) -> List[Tuple[int, int, int]]:
    """Return list of (u, v, common_count) promising edges."""
    adj = graph.adjacency
    n = graph.n
    degrees = [a.bit_count() for a in adj]
    # sample edges from high-degree vertices
    hubs = sorted(range(n), key=lambda v: -degrees[v])[: min(n, 128)]
    scored: List[Tuple[int, int, int]] = []
    seen = set()
    probes = 0
    for u in hubs:
        nbrs = bits_to_list(adj[u])
        if len(nbrs) > 64:
            nbrs = rng.sample(nbrs, 64)
        for v in nbrs:
            if u >= v:
                continue
            key = (u, v)
            if key in seen:
                continue
            seen.add(key)
            common = (adj[u] & adj[v]).bit_count()
            scored.append((u, v, common))
            probes += 1
            if probes >= cfg.pair_sample:
                break
        if probes >= cfg.pair_sample:
            break
    scored.sort(key=lambda x: -x[2])
    top = scored[: cfg.pair_top_k]
    # randomized top mixture
    if len(scored) > cfg.pair_top_k:
        extra = rng.sample(scored[: min(len(scored), cfg.pair_top_k * 3)], min(cfg.pair_top_k // 2, len(scored)))
        for e in extra:
            if e not in top:
                top.append(e)
    rng.shuffle(top)
    return top


def solve_pair_anchor(graph: BitsetGraph, cfg: CompetitiveConfig, deadline: float, t0: float, shared: Optional[dict] = None) -> CompetitiveResult:
    rng = random.Random(cfg.seed + 99)
    stats = CompetitiveStats()
    elite = (shared or {}).get("elite") or DiverseElitePool(cfg.elite_pool_size)
    hist: List[Dict[str, float]] = []
    best: List[int] = []

    def consider(clq: Sequence[int]) -> None:
        nonlocal best
        if not clq or not is_clique(graph, clq):
            return
        clq = extend_to_maximal(graph, clq)
        now = (time.perf_counter() - t0) * 1000.0
        elite.add(clq, now)
        if len(clq) > len(best):
            best = list(clq)
            stats.incumbent_improvements += 1
            hist.append({"time_ms": now, "size": float(len(best))})
            if stats.incumbent_improvements == 1:
                stats.time_to_first_ms = now
            stats.time_to_best_ms = now

    t_prep = time.perf_counter()
    pairs = _select_pairs(graph, cfg, rng) if graph.n else []
    stats.pair_prep_time_ms = (time.perf_counter() - t_prep) * 1000.0

    # also seed with high-degree greedy
    if graph.n:
        s0 = max(range(graph.n), key=lambda v: graph.adjacency[v].bit_count())
        consider(greedy_maximal_from_start(graph, s0))
        stats.constructions += 1

    pi = 0
    while time.perf_counter() < deadline and graph.n:
        if not pairs:
            consider(greedy_maximal_from_start(graph, rng.randrange(graph.n)))
            stats.constructions += 1
            continue
        u, v, _ = pairs[pi % len(pairs)]
        pi += 1
        stats.pair_starts += 1
        # build inside common neighborhood
        common = graph.adjacency[u] & graph.adjacency[v]
        clique = [u, v]
        cand = common
        while cand:
            # residual degree in cand
            best_v = -1
            best_sc = -1
            # sample if huge
            tmp = cand
            scanned = 0
            while tmp and scanned < 128:
                bit = tmp & -tmp
                w = bit.bit_length() - 1
                tmp ^= bit
                sc = (cand & graph.adjacency[w]).bit_count()
                # light noise
                sc = sc * 10 + rng.randrange(3)
                if sc > best_sc:
                    best_sc = sc
                    best_v = w
                scanned += 1
            if best_v < 0:
                break
            # RCL among top residual: randomize a bit
            if rng.random() < 0.25 and cand.bit_count() > 1:
                best_v = pick_from_mask(cand, rng, "degree", graph)
            clique.append(best_v)
            cand &= graph.adjacency[best_v]
        clique = extend_to_maximal(graph, clique)
        stats.constructions += 1
        # light local: C0 adds + one 1-swap improvement attempt via C1→C0
        t_ls = time.perf_counter()
        plateau_steps = 0
        for _ in range(32):
            c0 = compute_C0(graph, clique)
            if c0:
                w = pick_from_mask(c0, rng, "degree", graph)
                if w >= 0:
                    clique.append(w)
                    stats.add_moves += 1
                    plateau_steps = 0
                    continue
            c1 = compute_C1(graph, clique)
            if not c1 or plateau_steps >= 12:
                break
            w, conf = rng.choice(c1)
            trial = [x for x in clique if x != conf] + [w]
            if is_clique(graph, trial):
                stats.plateau_moves += 1
                plateau_steps += 1
                clique = trial
                if compute_C0(graph, clique):
                    stats.useful_plateau_moves += 1
                    plateau_steps = 0
            else:
                break
        stats.local_search_time_ms += (time.perf_counter() - t_ls) * 1000.0
        consider(clique)

    best = elite.sample_best_sized(rng, mode="diverse") or (best and extend_to_maximal(graph, best)) or []
    return _finalize(graph, best, CompetitiveVariant.PAIR_ANCHOR.value, stats, hist, cfg, t0, elite, deadline)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


def solve_portfolio(graph: BitsetGraph, cfg: CompetitiveConfig, deadline: float, t0: float) -> CompetitiveResult:
    """Single-deadline portfolio: time-sliced G/H/I/J sharing one elite/incumbent."""
    rng = random.Random(cfg.seed + 7)
    elite = DiverseElitePool(cfg.elite_pool_size)
    shared = {"elite": elite}
    total = max(1e-6, deadline - t0)
    fracs = cfg.portfolio_fracs
    methods = [
        (CompetitiveVariant.BLS_ADAPTIVE, fracs[0], solve_bls),
        (CompetitiveVariant.PLS_PENALTY, fracs[1], solve_pls),
        (CompetitiveVariant.IKLS_VARIABLE_DEPTH, fracs[2], solve_ikls),
        (CompetitiveVariant.PAIR_ANCHOR, fracs[3], solve_pair_anchor),
    ]
    # shuffle order by seed for fairness across rounds externally; keep seeded order here
    order = list(methods)
    rng.shuffle(order)
    cursor = t0
    best: List[int] = []
    hist: List[Dict[str, float]] = []
    stats = CompetitiveStats()
    for variant, frac, fn in order:
        if time.perf_counter() >= deadline:
            break
        slice_end = min(deadline, cursor + total * frac)
        # ensure at least a tiny slice
        if slice_end <= time.perf_counter():
            slice_end = min(deadline, time.perf_counter() + 0.05)
        sub_cfg = CompetitiveConfig(
            variant=variant,
            seed=cfg.seed,
            timeout_seconds=cfg.timeout_seconds,
            safety_margin_ms=0.0,  # outer already applied
        )
        # Temporarily run with hard slice deadline
        res = fn(graph, sub_cfg, slice_end, t0, shared)
        stats.constructions += res.stats.constructions
        stats.plateau_moves += res.stats.plateau_moves
        stats.useful_plateau_moves += res.stats.useful_plateau_moves
        stats.add_moves += res.stats.add_moves
        stats.perturbations += res.stats.perturbations
        stats.variable_depth_improvements += res.stats.variable_depth_improvements
        stats.pair_starts += res.stats.pair_starts
        for row in res.stats.improvement_history:
            hist.append(row)
        if len(res.clique) > len(best):
            best = list(res.clique)
            stats.incumbent_improvements += 1
            stats.time_to_best_ms = (time.perf_counter() - t0) * 1000.0
            if stats.incumbent_improvements == 1:
                stats.time_to_first_ms = stats.time_to_best_ms
        cursor = slice_end

    # merge hist unique by time
    hist = sorted(hist, key=lambda r: r["time_ms"])
    # rebuild improvement hist monotonic
    mono: List[Dict[str, float]] = []
    best_sz = 0
    for row in hist:
        if int(row["size"]) > best_sz:
            best_sz = int(row["size"])
            mono.append(row)
    if not best and elite:
        best = elite.best()
    if not best and graph.n:
        best = greedy_maximal_from_start(graph, 0)
    best = elite.sample_best_sized(rng, mode="diverse") or extend_to_maximal(graph, best)
    stats.extras["portfolio_order"] = [m[0].value for m in order]
    stats.extras["note"] = "time-sliced single-deadline portfolio; not 4x full deadlines"
    return _finalize(graph, best, CompetitiveVariant.ADAPTIVE_PORTFOLIO.value, stats, mono, cfg, t0, elite, deadline)


def _finalize(
    graph: BitsetGraph,
    best: Sequence[int],
    variant: str,
    stats: CompetitiveStats,
    hist: List[Dict[str, float]],
    cfg: CompetitiveConfig,
    t0: float,
    elite: DiverseElitePool,
    soft_deadline: float,
) -> CompetitiveResult:
    hard = t0 + max(0.0, cfg.timeout_seconds)
    best_list = sorted(extend_to_maximal(graph, list(best))) if best else []
    valid = is_clique(graph, best_list)
    maximal = is_maximal_clique(graph, best_list) if valid else False
    stats.unique_cliques = len(elite)
    stats.improvement_history = hist
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    stats.deadline_reached = time.perf_counter() >= soft_deadline
    stats.search_incomplete_at_deadline = stats.deadline_reached
    stats.response_deadline_violation = time.perf_counter() > hard + 1e-3
    stats.checkpoints = _checkpoints(hist, cfg.timeout_seconds, len(best_list))
    stats.extras.update(
        {
            "elite_size": len(elite),
            "best_sized_variants": sum(1 for it in elite._items if it[0] == len(best_list)),
            "simplified_adaptation_note": (
                "Pure-Python adaptation of published mechanisms; not an exact paper reproduction."
            ),
        }
    )
    return CompetitiveResult(
        clique=best_list,
        clique_size=len(best_list),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=variant,
        stats=stats,
    )


def solve_competitive(graph: BitsetGraph, config: CompetitiveConfig) -> CompetitiveResult:
    t0 = time.perf_counter()
    soft = t0 + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    if graph.n == 0:
        st = CompetitiveStats(total_ms=0.0)
        return CompetitiveResult([], 0, False, False, False, config.variant.value, st)
    if config.variant == CompetitiveVariant.PLS_PENALTY:
        return solve_pls(graph, config, soft, t0)
    if config.variant == CompetitiveVariant.BLS_ADAPTIVE:
        return solve_bls(graph, config, soft, t0)
    if config.variant == CompetitiveVariant.IKLS_VARIABLE_DEPTH:
        return solve_ikls(graph, config, soft, t0)
    if config.variant == CompetitiveVariant.PAIR_ANCHOR:
        return solve_pair_anchor(graph, config, soft, t0)
    if config.variant == CompetitiveVariant.ADAPTIVE_PORTFOLIO:
        return solve_portfolio(graph, config, soft, t0)
    raise ValueError(f"Unknown competitive variant: {config.variant}")
