"""Anytime multi-start greedy + clique-exchange local search (Methods D/E/F)."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .bitset import bits_to_list, list_to_mask
from .graph import BitsetGraph
from .greedy import extend_to_maximal
from .validation import is_clique, is_maximal_clique

CHECKPOINT_SECONDS = (0.1, 0.5, 1.0, 2.0, 3.0, 5.0)
ELITE_POOL_SIZE = 16


class AnytimeVariant(str, Enum):
    MULTISTART_GREEDY = "multistart_greedy"
    SWAP_LOCAL_SEARCH = "swap_local_search"
    TRIANGLE_GUIDED = "triangle_guided"


@dataclass
class AnytimeStats:
    constructions: int = 0
    restarts: int = 0
    unique_cliques: int = 0
    incumbent_improvements: int = 0
    time_to_first_ms: float = 0.0
    time_to_best_ms: float = 0.0
    swap_1for2_attempts: int = 0
    swap_1for2_success: int = 0
    swap_2for3_attempts: int = 0
    swap_2for3_success: int = 0
    perturbations: int = 0
    escape_improvements: int = 0
    scoring_time_ms: float = 0.0
    construction_time_ms: float = 0.0
    local_search_time_ms: float = 0.0
    triangle_prep_time_ms: float = 0.0
    deadline_reached: bool = False
    search_incomplete_at_deadline: bool = False
    response_deadline_violation: bool = False
    total_ms: float = 0.0
    improvement_history: List[Dict[str, float]] = field(default_factory=list)
    checkpoints: Dict[str, Optional[int]] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnytimeResult:
    clique: List[int]
    clique_size: int
    valid: bool
    maximal: bool
    proven_optimal: bool
    variant: str
    stats: AnytimeStats


@dataclass
class AnytimeConfig:
    variant: AnytimeVariant = AnytimeVariant.MULTISTART_GREEDY
    seed: int = 42
    timeout_seconds: float = 10.0
    safety_margin_ms: float = 500.0
    elite_pool_size: int = ELITE_POOL_SIZE
    # D selection
    policy: str = "rcl"  # max_residual | rcl | degree_common | softmax
    rcl_k: int = 8
    rcl_frac: float = 0.15
    softmax_temperature: float = 1.25
    # E local search
    enable_1for2: bool = True
    enable_2for3: bool = True
    first_improvement: bool = True
    max_2for3_remove_pairs: int = 24
    max_2for3_cand_scan: int = 48
    local_search_every: int = 1
    stall_before_2for3: int = 8
    perturbation_removals: int = 2
    # F triangle weights
    alpha: float = 0.65
    beta: float = 0.35
    noise: float = 0.15
    triangle_sample_cap: int = 64


class ElitePool:
    def __init__(self, capacity: int = ELITE_POOL_SIZE) -> None:
        self.capacity = capacity
        self._items: List[Tuple[int, Tuple[int, ...]]] = []
        self._seen: set[Tuple[int, ...]] = set()

    def add(self, clique: Sequence[int]) -> bool:
        key = tuple(sorted(clique))
        if key in self._seen:
            return False
        self._seen.add(key)
        self._items.append((len(key), key))
        self._items.sort(key=lambda x: (-x[0], x[1]))
        if len(self._items) > self.capacity:
            dropped = self._items[self.capacity :]
            self._items = self._items[: self.capacity]
            for _, k in dropped:
                self._seen.discard(k)
        return True

    def best(self) -> List[int]:
        if not self._items:
            return []
        return list(self._items[0][1])

    def sample(self, rng: random.Random) -> List[int]:
        if not self._items:
            return []
        return list(rng.choice(self._items)[1])

    def __len__(self) -> int:
        return len(self._items)


def _checkpoints_from_history(
    history: List[Dict[str, float]],
    timeout_seconds: float,
    final_size: int,
) -> Dict[str, Optional[int]]:
    out: Dict[str, Optional[int]] = {}
    for sec in CHECKPOINT_SECONDS:
        if sec > timeout_seconds + 1e-9:
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


def _pick_start(graph: BitsetGraph, rng: random.Random, elite: ElitePool, restart_i: int) -> int:
    degrees = graph.degrees()
    n = graph.n
    mode = restart_i % 5
    if mode == 0:
        return rng.randrange(n)
    if mode == 1:
        # high-degree
        return max(range(n), key=lambda v: (degrees[v], v))
    if mode == 2:
        # randomized high-degree: sample from top quartile
        ranked = sorted(range(n), key=lambda v: (-degrees[v], v))
        top = ranked[: max(1, n // 4)]
        return rng.choice(top)
    if mode == 3 and elite:
        base = elite.sample(rng)
        if base:
            return rng.choice(base)
    if mode == 4 and elite:
        # avoid elite vertices sometimes
        forbidden = set(elite.best()) if elite else set()
        candidates = [v for v in range(n) if v not in forbidden]
        if candidates:
            return rng.choice(candidates)
    return rng.randrange(n)


def _score_candidates(
    cand: int,
    adj: List[int],
    rng: random.Random,
    policy: str,
    cfg: AnytimeConfig,
    triangle_score: Optional[List[float]] = None,
) -> int:
    """Select one vertex from candidate mask using the configured policy."""
    if cand == 0:
        return -1

    # Fast path: collect (score, v) for candidates. Cap scan for huge sets by sampling.
    verts: List[int] = []
    scores: List[float] = []
    tmp = cand
    count = cand.bit_count()
    # If enormous, sample a subset of bits for ranking then pick.
    sample_limit = 256
    if count > sample_limit:
        # reservoir-like: take first sample_limit after random bit walks
        # Cheap: convert partial by clearing randomly
        picked = 0
        probe = cand
        # jump-ish: iterate until filled
        while probe and picked < sample_limit:
            bit = probe & -probe
            v = bit.bit_length() - 1
            probe ^= bit
            # keep with probability sample_limit/count approx via rng
            if rng.random() < (sample_limit / count) or picked < sample_limit // 4:
                verts.append(v)
                picked += 1
        if not verts:
            return (cand & -cand).bit_length() - 1
    else:
        while tmp:
            bit = tmp & -tmp
            v = bit.bit_length() - 1
            tmp ^= bit
            verts.append(v)

    for v in verts:
        residual = (cand & adj[v]).bit_count()
        if policy == "max_residual":
            scores.append(float(residual))
        elif policy == "degree_common":
            # residual degree + common-neighbor proxy among candidates
            common_boost = residual  # same scale
            scores.append(float(residual) + 0.5 * common_boost)
        elif policy == "softmax":
            scores.append(float(residual))
        elif policy == "triangle" or policy == "rcl_triangle":
            t = triangle_score[v] if triangle_score is not None else 0.0
            # residual normalized roughly by comparing raw mixes
            scores.append(cfg.alpha * float(residual) + cfg.beta * t + cfg.noise * rng.random())
        else:  # rcl default
            scores.append(float(residual))

    if policy == "max_residual":
        best_i = max(range(len(verts)), key=lambda i: (scores[i], verts[i]))
        return verts[best_i]

    if policy == "softmax":
        temp = max(1e-6, cfg.softmax_temperature)
        m = max(scores)
        weights = [math.exp((s - m) / temp) for s in scores]
        total = sum(weights)
        r = rng.random() * total
        acc = 0.0
        for v, w in zip(verts, weights):
            acc += w
            if acc >= r:
                return v
        return verts[-1]

    # RCL / triangle RCL: top-k then uniform
    order = sorted(range(len(verts)), key=lambda i: (-scores[i], verts[i]))
    k = cfg.rcl_k
    if cfg.rcl_frac > 0:
        k = max(k, int(math.ceil(len(order) * cfg.rcl_frac)))
    k = max(1, min(k, len(order)))
    return verts[rng.choice(order[:k])]


def greedy_construct(
    graph: BitsetGraph,
    rng: random.Random,
    start: int,
    cfg: AnytimeConfig,
    policy: str,
    triangle_score: Optional[List[float]] = None,
) -> List[int]:
    adj = graph.adjacency
    clique = [start]
    cand = adj[start]
    while cand:
        v = _score_candidates(cand, adj, rng, policy, cfg, triangle_score)
        if v < 0:
            break
        clique.append(v)
        cand &= adj[v]
    return clique


def _common_neighbors_outside(graph: BitsetGraph, clique: Sequence[int], forbidden: int) -> int:
    if not clique:
        return 0
    common = graph.all_vertices_mask() & ~forbidden
    adj = graph.adjacency
    for u in clique:
        common &= adj[u]
        if common == 0:
            return 0
    return common


def try_1for2(
    graph: BitsetGraph,
    clique: Sequence[int],
    rng: random.Random,
    first_improvement: bool,
) -> Optional[List[int]]:
    """Remove 1 vertex, add 2 mutually adjacent extensions."""
    if len(clique) < 1:
        return None
    adj = graph.adjacency
    order = list(clique)
    rng.shuffle(order)
    best: Optional[List[int]] = None
    clique_mask = list_to_mask(clique)

    for rem in order:
        remaining = [u for u in clique if u != rem]
        rem_mask = clique_mask
        common = _common_neighbors_outside(graph, remaining, rem_mask)
        if common.bit_count() < 2:
            continue
        # find adjacent pair in common
        tmp = common
        found_pair: Optional[Tuple[int, int]] = None
        while tmp:
            bit = tmp & -tmp
            e = bit.bit_length() - 1
            tmp ^= bit
            partners = common & adj[e]
            if partners:
                f = (partners & -partners).bit_length() - 1
                found_pair = (e, f)
                break
        if found_pair is None:
            continue
        e, f = found_pair
        cand = sorted(remaining + [e, f])
        if not is_clique(graph, cand):
            continue
        if first_improvement:
            return cand
        best = cand
        break
    return best


def try_2for3(
    graph: BitsetGraph,
    clique: Sequence[int],
    rng: random.Random,
    cfg: AnytimeConfig,
    deadline: float,
) -> Optional[List[int]]:
    """Remove 2 vertices, add a triangle of 3 outside vertices."""
    if len(clique) < 2:
        return None
    adj = graph.adjacency
    verts = list(clique)
    rng.shuffle(verts)
    pairs: List[Tuple[int, int]] = []
    for i in range(len(verts)):
        for j in range(i + 1, len(verts)):
            pairs.append((verts[i], verts[j]))
            if len(pairs) >= cfg.max_2for3_remove_pairs * 3:
                break
        if len(pairs) >= cfg.max_2for3_remove_pairs * 3:
            break
    rng.shuffle(pairs)
    pairs = pairs[: cfg.max_2for3_remove_pairs]
    clique_mask = list_to_mask(clique)

    for a, b in pairs:
        if time.perf_counter() >= deadline:
            return None
        remaining = [u for u in clique if u != a and u != b]
        common = _common_neighbors_outside(graph, remaining, clique_mask)
        if common.bit_count() < 3:
            continue
        # scan limited vertices in common for a triangle
        scan = bits_to_list(common)
        if len(scan) > cfg.max_2for3_cand_scan:
            scan = rng.sample(scan, cfg.max_2for3_cand_scan)
        for i, e in enumerate(scan):
            if time.perf_counter() >= deadline:
                return None
            for j in range(i + 1, len(scan)):
                f = scan[j]
                if not ((adj[e] >> f) & 1):
                    continue
                for k in range(j + 1, len(scan)):
                    g = scan[k]
                    if ((adj[e] >> g) & 1) and ((adj[f] >> g) & 1):
                        cand = sorted(remaining + [e, f, g])
                        if is_clique(graph, cand):
                            return cand
    return None


def improve_local(
    graph: BitsetGraph,
    clique: List[int],
    rng: random.Random,
    cfg: AnytimeConfig,
    deadline: float,
    stats: AnytimeStats,
    allow_2for3: bool,
) -> List[int]:
    t0 = time.perf_counter()
    cur = list(clique)
    stalled = 0
    while time.perf_counter() < deadline:
        improved = False
        if cfg.enable_1for2:
            stats.swap_1for2_attempts += 1
            nxt = try_1for2(graph, cur, rng, cfg.first_improvement)
            if nxt is not None and len(nxt) > len(cur):
                stats.swap_1for2_success += 1
                cur = nxt
                improved = True
                stalled = 0
        if not improved and allow_2for3 and cfg.enable_2for3 and stalled >= cfg.stall_before_2for3:
            stats.swap_2for3_attempts += 1
            nxt = try_2for3(graph, cur, rng, cfg, deadline)
            if nxt is not None and len(nxt) > len(cur):
                stats.swap_2for3_success += 1
                cur = nxt
                improved = True
                stalled = 0
            else:
                break
        if not improved:
            stalled += 1
            if stalled > cfg.stall_before_2for3 + 2:
                break
    stats.local_search_time_ms += (time.perf_counter() - t0) * 1000.0
    return extend_to_maximal(graph, cur)


def perturb(graph: BitsetGraph, clique: Sequence[int], rng: random.Random, removals: int) -> List[int]:
    if not clique:
        return []
    keep = list(clique)
    rng.shuffle(keep)
    k = max(0, len(keep) - max(1, removals))
    core = keep[:k] if k else []
    if not core:
        start = rng.randrange(graph.n)
        return greedy_construct(
            graph,
            rng,
            start,
            AnytimeConfig(),
            policy="rcl",
        )
    # Core is a subset of a clique, hence still a clique.
    return list(core)


def _prepare_triangle_scores(graph: BitsetGraph, cfg: AnytimeConfig) -> List[float]:
    """Lightweight per-vertex triangle participation estimate.

    Uses degree as a fast proxy on very large/dense graphs, and only samples
    common-neighbor counts for a capped neighbor set otherwise.
    """
    adj = graph.adjacency
    n = graph.n
    degrees = [a.bit_count() for a in adj]
    # Dense SN83 graphs: full triangle sampling is too expensive in pure Python.
    density = (sum(degrees) / 2) / max(1, n * (n - 1) / 2)
    if n >= 400 or density >= 0.6:
        deg_max = max(degrees) if degrees else 1
        return [d * (d / deg_max) for d in degrees]

    scores = [0.0] * n
    cap = cfg.triangle_sample_cap
    for v in range(n):
        nbr_mask = adj[v]
        # Take up to `cap` neighbor bits without materializing all neighbors.
        nbrs: List[int] = []
        tmp = nbr_mask
        while tmp and len(nbrs) < cap:
            bit = tmp & -tmp
            nbrs.append(bit.bit_length() - 1)
            tmp ^= bit
        total = 0
        for u in nbrs:
            total += (adj[v] & adj[u]).bit_count()
        scores[v] = float(total)
    mx = max(scores) if scores else 1.0
    if mx <= 0:
        return [float(d) for d in degrees]
    deg_max = max(degrees) if degrees else 1
    return [s / mx * deg_max for s in scores]


def solve_anytime(graph: BitsetGraph, config: AnytimeConfig) -> AnytimeResult:
    t_start = time.perf_counter()
    soft_deadline = t_start + max(0.0, config.timeout_seconds - config.safety_margin_ms / 1000.0)
    hard_deadline = t_start + max(0.0, config.timeout_seconds)
    rng = random.Random(config.seed)
    stats = AnytimeStats()
    elite = ElitePool(config.elite_pool_size)

    triangle_score: Optional[List[float]] = None
    policy = config.policy
    if config.variant == AnytimeVariant.TRIANGLE_GUIDED:
        t_tri = time.perf_counter()
        triangle_score = _prepare_triangle_scores(graph, config)
        stats.triangle_prep_time_ms = (time.perf_counter() - t_tri) * 1000.0
        policy = "rcl_triangle"
    elif config.variant == AnytimeVariant.MULTISTART_GREEDY:
        policy = config.policy
    else:
        policy = config.policy if config.policy != "triangle" else "rcl"

    best: List[int] = []

    def consider(clique: Sequence[int]) -> None:
        nonlocal best
        if not clique:
            return
        # Never extend a non-clique — extend_to_maximal assumes a valid seed clique.
        if not is_clique(graph, clique):
            return
        cl = extend_to_maximal(graph, clique)
        if not is_clique(graph, cl):
            return
        elite.add(cl)
        if len(cl) > len(best):
            best = list(cl)
            now = (time.perf_counter() - t_start) * 1000.0
            stats.incumbent_improvements += 1
            stats.improvement_history.append({"time_ms": now, "size": float(len(best))})
            if stats.incumbent_improvements == 1:
                stats.time_to_first_ms = now
            stats.time_to_best_ms = now

    # Ensure non-empty start
    if graph.n == 0:
        stats.total_ms = (time.perf_counter() - t_start) * 1000.0
        return AnytimeResult([], 0, False, False, False, config.variant.value, stats)

    restart_i = 0
    stalled_ls = 0
    do_local = config.variant in (
        AnytimeVariant.SWAP_LOCAL_SEARCH,
        AnytimeVariant.TRIANGLE_GUIDED,
    )

    while time.perf_counter() < soft_deadline:
        start = _pick_start(graph, rng, elite, restart_i)
        t_c0 = time.perf_counter()
        clique = greedy_construct(graph, rng, start, config, policy, triangle_score)
        stats.construction_time_ms += (time.perf_counter() - t_c0) * 1000.0
        stats.constructions += 1
        stats.restarts += 1
        consider(clique)

        if do_local and config.local_search_every > 0 and restart_i % config.local_search_every == 0:
            allow_2for3 = stalled_ls >= config.stall_before_2for3
            improved = improve_local(
                graph, list(best) if best else clique, rng, config, soft_deadline, stats, allow_2for3
            )
            before = len(best)
            consider(improved)
            if len(best) > before:
                stalled_ls = 0
            else:
                stalled_ls += 1

            # perturbation escape
            if stalled_ls >= config.stall_before_2for3 and time.perf_counter() < soft_deadline:
                stats.perturbations += 1
                base = elite.sample(rng) or best
                core = perturb(graph, base, rng, config.perturbation_removals)
                if core and is_clique(graph, core):
                    # Rebuild from a surviving core vertex; do not union incompatible sets.
                    seed_v = rng.choice(core)
                    rebuilt = greedy_construct(graph, rng, seed_v, config, "rcl", triangle_score)
                    # Prefer keeping core members that remain feasible in rebuilt clique.
                    keep = []
                    rebuilt_set = set(rebuilt)
                    for v in core:
                        if v in rebuilt_set:
                            keep.append(v)
                        else:
                            if all(graph.has_edge(v, u) for u in keep):
                                # try add into working set if adjacent to kept core
                                if all(graph.has_edge(v, u) for u in rebuilt):
                                    rebuilt.append(v)
                                    keep.append(v)
                    rebuilt = extend_to_maximal(graph, rebuilt)
                    improved2 = improve_local(
                        graph, rebuilt, rng, config, soft_deadline, stats, allow_2for3=True
                    )
                    before = len(best)
                    consider(improved2)
                    if len(best) > before:
                        stats.escape_improvements += 1
                        stalled_ls = 0

        restart_i += 1
        if restart_i > 10_000_000:
            break

    stats.deadline_reached = time.perf_counter() >= soft_deadline
    stats.search_incomplete_at_deadline = stats.deadline_reached
    # finalize
    if not best:
        degrees = graph.degrees()
        start = max(range(graph.n), key=lambda v: degrees[v])
        best = extend_to_maximal(graph, [start])
        consider(best)

    best = extend_to_maximal(graph, best)
    best = sorted(best)
    valid = is_clique(graph, best)
    maximal = is_maximal_clique(graph, best) if valid else False
    stats.unique_cliques = len(elite)
    stats.total_ms = (time.perf_counter() - t_start) * 1000.0
    stats.response_deadline_violation = time.perf_counter() > hard_deadline
    stats.checkpoints = _checkpoints_from_history(
        stats.improvement_history, config.timeout_seconds, len(best)
    )
    stats.extras = {
        "policy": policy,
        "elite_size": len(elite),
        "variant": config.variant.value,
        "soft_deadline_s": config.timeout_seconds - config.safety_margin_ms / 1000.0,
    }
    return AnytimeResult(
        clique=best,
        clique_size=len(best),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=config.variant.value,
        stats=stats,
    )
