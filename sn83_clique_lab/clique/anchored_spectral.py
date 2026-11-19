"""Anchored spectral recovery inside common-neighborhood subgraphs.

Inspired by (not reproducing) arXiv:2210.02121 — spectral analysis of
induced subgraphs from common neighborhoods of small seed cliques/pairs.
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Sequence, Tuple

from .bitset import bits_to_list
from .graph import BitsetGraph
from .greedy import extend_to_maximal, greedy_maximal_from_start
from .spectral_clique import (
    SpectralConfig,
    SpectralSolveResult,
    SpectralSolveStats,
    _consider,
    _maybe_ikls,
)
from .spectral_rank import induced_subgraph, lanczos_centered
from .validation import is_clique, is_maximal_clique


def select_seed_pairs(
    graph: BitsetGraph,
    rng: random.Random,
    top_k: int,
    sample: int,
) -> List[Tuple[int, int, int]]:
    """Graph-only promising pairs: (u, v, common_count)."""
    n = graph.n
    degrees = graph.degrees()
    hubs = sorted(range(n), key=lambda v: -degrees[v])[: min(n, 160)]
    scored: List[Tuple[int, int, int]] = []
    seen = set()
    probes = 0
    for u in hubs:
        neigh = bits_to_list(graph.adjacency[u])
        if len(neigh) > 40:
            neigh = rng.sample(neigh, 40)
        for v in neigh:
            if v <= u:
                continue
            key = (u, v)
            if key in seen:
                continue
            seen.add(key)
            common = (graph.adjacency[u] & graph.adjacency[v]).bit_count()
            scored.append((u, v, common))
            probes += 1
            if probes >= sample:
                break
        if probes >= sample:
            break
    while probes < sample and n >= 2:
        u = rng.randrange(n)
        neigh = bits_to_list(graph.adjacency[u])
        probes += 1
        if not neigh:
            continue
        v = rng.choice(neigh)
        if u > v:
            u, v = v, u
        if (u, v) in seen:
            continue
        seen.add((u, v))
        common = (graph.adjacency[u] & graph.adjacency[v]).bit_count()
        scored.append((u, v, common))
    scored.sort(key=lambda t: -t[2])
    out = scored[: max(1, top_k // 2)]
    rest = scored[max(1, top_k // 2) : top_k * 3]
    if rest:
        out.extend(rng.sample(rest, min(len(rest), top_k - len(out))))
    return out[:top_k]


def _clique_from_pair_residual(graph: BitsetGraph, u: int, v: int, common_mask: int) -> List[int]:
    cand = common_mask
    clique = [u, v]
    while cand:
        best_w, best_sc = -1, -1
        tmp = cand
        while tmp:
            bit = tmp & -tmp
            w = bit.bit_length() - 1
            tmp ^= bit
            sc = (cand & graph.adjacency[w]).bit_count()
            if sc > best_sc:
                best_sc = sc
                best_w = w
        if best_w < 0:
            break
        clique.append(best_w)
        cand &= graph.adjacency[best_w]
    return extend_to_maximal(graph, clique)


def _clique_from_pair_spectral_order(
    graph: BitsetGraph,
    u: int,
    v: int,
    common_mask: int,
    order: Sequence[int],
) -> List[int]:
    rank = {g: i for i, g in enumerate(order)}
    clique = [u, v]
    cand = common_mask
    while cand:
        best_w, best_r = None, 10**18
        for w in bits_to_list(cand):
            r = rank.get(w, 10**18)
            if r < best_r:
                best_r = r
                best_w = w
        if best_w is None:
            break
        clique.append(best_w)
        cand &= graph.adjacency[best_w]
    return extend_to_maximal(graph, clique)


def solve_anchored_spectral(
    graph: BitsetGraph,
    cfg: SpectralConfig,
    soft_deadline: float,
    t0: float,
) -> SpectralSolveResult:
    rng = random.Random(cfg.seed + 99)
    stats = SpectralSolveStats()
    hist: List[Dict[str, float]] = []
    best: List[int] = []

    for v in sorted(range(graph.n), key=lambda i: graph.degree(i), reverse=True)[:8]:
        if time.perf_counter() >= soft_deadline:
            break
        best = _consider(graph, greedy_maximal_from_start(graph, v), best, hist, stats, t0)

    pairs = select_seed_pairs(graph, rng, cfg.pair_top_k, cfg.pair_sample)
    spectral_cap = t0 + max(0.05, cfg.timeout_seconds * cfg.spectral_max_time_fraction)

    for u, v, _cn in pairs:
        if time.perf_counter() >= soft_deadline:
            break
        stats.pair_starts += 1
        common_mask = graph.adjacency[u] & graph.adjacency[v]
        candidates = bits_to_list(common_mask)

        best = _consider(
            graph,
            _clique_from_pair_residual(graph, u, v, common_mask),
            best,
            hist,
            stats,
            t0,
        )

        if len(candidates) < 3 or time.perf_counter() >= min(soft_deadline, spectral_cap):
            continue

        if len(candidates) > 400:
            cand_deg = [((graph.adjacency[w] & common_mask).bit_count(), w) for w in candidates]
            cand_deg.sort(reverse=True)
            candidates = [w for _, w in cand_deg[:320]]

        sub, local_to_global = induced_subgraph(graph, candidates, name=f"cn_{u}_{v}")
        if sub.n < 3:
            continue
        pair_deadline = min(soft_deadline, spectral_cap, time.perf_counter() + 0.35)
        spec = lanczos_centered(
            sub,
            max_iter=min(cfg.lanczos_iters, 12),
            n_eigs=min(2, cfg.n_eigens),
            deadline=pair_deadline,
        )
        stats.spectral_ms += spec.total_ms
        stats.lanczos_iters += spec.iterations
        if spec.residuals:
            stats.residuals = list(spec.residuals)
        if spec.eigenvalues:
            stats.eigenvalues = list(spec.eigenvalues)

        for vec_local in spec.eigenvectors[:2]:
            scores = [0.0] * graph.n
            for loc, gidx in enumerate(local_to_global):
                scores[gidx] = vec_local[loc]
            scores[u] += 1.0
            scores[v] += 1.0
            order = sorted(local_to_global, key=lambda gidx: abs(scores[gidx]), reverse=True)
            clique = _clique_from_pair_spectral_order(graph, u, v, common_mask, order)
            best = _consider(graph, clique, best, hist, stats, t0)
            if time.perf_counter() >= soft_deadline:
                break

    best = _maybe_ikls(graph, best, cfg, soft_deadline, t0, stats, hist)
    best = sorted(extend_to_maximal(graph, best)) if best else []
    valid = is_clique(graph, best)
    maximal = is_maximal_clique(graph, best) if valid else False
    hard = t0 + cfg.timeout_seconds
    stats.improvement_history = hist
    stats.extras["n_pairs"] = len(pairs)
    stats.total_ms = (time.perf_counter() - t0) * 1000.0
    return SpectralSolveResult(
        clique=best,
        clique_size=len(best),
        valid=valid,
        maximal=maximal,
        proven_optimal=False,
        variant=cfg.variant.value,
        stats=stats,
        deadline_reached=time.perf_counter() >= soft_deadline,
        response_deadline_violation=time.perf_counter() > hard + 1e-3,
    )
