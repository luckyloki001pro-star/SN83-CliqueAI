"""Offline graph fingerprinting for SN83 Phase 4A.

Uses only the input graph. Historical clique sizes may be attached by callers
for reporting, but must never feed solver decisions.
"""

from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .bitset import bits_to_list, iter_bits
from .graph import BitsetGraph


@dataclass
class GraphFingerprint:
    name: str
    n: int
    m: int
    density: float
    avg_degree: float
    min_degree: int
    max_degree: int
    degree_std: float
    degree_cv: float
    complement_density: float
    degree_p10: float
    degree_p50: float
    degree_p90: float
    sampled_triangle_count: int
    sampled_wedge_count: int
    sampled_triangle_density: float
    mean_local_clustering: float
    clustering_std: float
    cn_edge_mean: float
    cn_edge_std: float
    cn_edge_p90: float
    cn_nonedge_mean: float
    cn_nonedge_std: float
    cn_nonedge_p90: float
    neigh_density_mean: float
    neigh_density_std: float
    high_degree_internal_density: float
    degree_vs_er_z: float
    er_expected_count_threshold: int
    er_log_expected_at_threshold: float
    er_log_expected_at_threshold_plus1: float
    fingerprint_ms: float
    sample_seed: int
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        extras = row.pop("extras", {})
        row.update({f"extra_{k}": v for k, v in extras.items()})
        return row


def _percentile(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    x = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(math.floor(x))
    hi = int(math.ceil(x))
    if lo == hi:
        return float(sorted_vals[lo])
    w = x - lo
    return float(sorted_vals[lo]) * (1.0 - w) + float(sorted_vals[hi]) * w


def er_log_expected_cliques(n: int, p: float, k: int) -> float:
    """log(E[X_k]) = lgamma(n+1)-lgamma(k+1)-lgamma(n-k+1) + binom(k,2)*log(p)."""
    if k < 0 or k > n:
        return float("-inf")
    if k <= 1:
        return math.log(max(n, 1)) if k == 1 else 0.0
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        # complete graph: E = C(n,k)
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    edges = k * (k - 1) / 2.0
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + edges * math.log(p)
    )


def er_expected_count_threshold(n: int, p: float, k_max: Optional[int] = None) -> Tuple[int, float, float]:
    """Largest k with E[X_k] >= 1 (log-space). Returns (k*, logE[k*], logE[k*+1])."""
    if n <= 0:
        return 0, float("-inf"), float("-inf")
    if k_max is None:
        k_max = min(n, max(3, int(2.0 * math.log(max(n, 2)) / max(1e-12, -math.log(max(p, 1e-12)))) + 20))
        k_max = min(n, max(k_max, 40))
    best_k = 1
    best_log = er_log_expected_cliques(n, p, 1)
    prev = best_log
    for k in range(2, k_max + 1):
        lg = er_log_expected_cliques(n, p, k)
        if lg >= 0.0:
            best_k = k
            prev = lg
        else:
            return best_k, prev, lg
    return best_k, prev, er_log_expected_cliques(n, p, min(n, best_k + 1))


def fingerprint_graph(
    graph: BitsetGraph,
    seed: int = 42,
    max_clustering_samples: int = 256,
    max_edge_cn_samples: int = 800,
    max_nonedge_cn_samples: int = 800,
    max_neigh_density_samples: int = 128,
    high_degree_frac: float = 0.05,
) -> GraphFingerprint:
    t0 = time.perf_counter()
    rng = random.Random(seed)
    n = graph.n
    m = graph.edge_count()
    dens = graph.density()
    degrees = graph.degrees()
    avg_deg = (2.0 * m / n) if n else 0.0
    min_d = min(degrees) if degrees else 0
    max_d = max(degrees) if degrees else 0
    deg_std = statistics.pstdev(degrees) if len(degrees) > 1 else 0.0
    deg_cv = (deg_std / avg_deg) if avg_deg > 1e-12 else 0.0
    sorted_deg = sorted(float(d) for d in degrees)

    # --- triangles / clustering (sampled) ---
    verts = list(range(n))
    if n > max_clustering_samples:
        sample_v = rng.sample(verts, max_clustering_samples)
    else:
        sample_v = verts
    clustering: List[float] = []
    tri_count = 0
    wedge_count = 0
    for v in sample_v:
        neigh = bits_to_list(graph.adjacency[v])
        d = len(neigh)
        if d < 2:
            clustering.append(0.0)
            continue
        # count edges among neighbors
        edges_among = 0
        for i, u in enumerate(neigh):
            au = graph.adjacency[u]
            for w in neigh[i + 1 :]:
                if (au >> w) & 1:
                    edges_among += 1
        wedges = d * (d - 1) // 2
        wedge_count += wedges
        tri_count += edges_among  # each triangle counted once per sampled apex
        clustering.append((2.0 * edges_among) / (d * (d - 1)))
    tri_density = (tri_count / wedge_count) if wedge_count else 0.0
    mean_cl = statistics.fmean(clustering) if clustering else 0.0
    cl_std = statistics.pstdev(clustering) if len(clustering) > 1 else 0.0

    # --- common neighbors: edges and non-edges ---
    edge_pairs: List[Tuple[int, int]] = []
    # reservoir-ish: scan a bounded number of adjacency lists
    scanned = 0
    for u in rng.sample(verts, n) if n else []:
        for v in iter_bits(graph.adjacency[u]):
            if v <= u:
                continue
            edge_pairs.append((u, v))
            scanned += 1
            if len(edge_pairs) >= max_edge_cn_samples * 3:
                break
        if len(edge_pairs) >= max_edge_cn_samples * 3:
            break
    if len(edge_pairs) > max_edge_cn_samples:
        edge_pairs = rng.sample(edge_pairs, max_edge_cn_samples)

    cn_edge: List[float] = []
    for u, v in edge_pairs:
        # exclude u,v themselves
        common = (graph.adjacency[u] & graph.adjacency[v]).bit_count()
        cn_edge.append(float(common))

    nonedge_pairs: List[Tuple[int, int]] = []
    attempts = 0
    while len(nonedge_pairs) < max_nonedge_cn_samples and attempts < max_nonedge_cn_samples * 40 and n >= 2:
        u = rng.randrange(n)
        v = rng.randrange(n)
        attempts += 1
        if u == v:
            continue
        if u > v:
            u, v = v, u
        if (graph.adjacency[u] >> v) & 1:
            continue
        nonedge_pairs.append((u, v))
    cn_non: List[float] = []
    for u, v in nonedge_pairs:
        cn_non.append(float((graph.adjacency[u] & graph.adjacency[v]).bit_count()))

    def _stats(vals: List[float]) -> Tuple[float, float, float]:
        if not vals:
            return 0.0, 0.0, 0.0
        s = sorted(vals)
        return statistics.fmean(vals), (statistics.pstdev(vals) if len(vals) > 1 else 0.0), _percentile(s, 90)

    cn_e_mean, cn_e_std, cn_e_p90 = _stats(cn_edge)
    cn_n_mean, cn_n_std, cn_n_p90 = _stats(cn_non)

    # --- neighborhood edge density samples ---
    nd_samples: List[float] = []
    for v in (rng.sample(verts, min(n, max_neigh_density_samples)) if n else []):
        neigh = bits_to_list(graph.adjacency[v])
        d = len(neigh)
        if d < 2:
            continue
        edges_among = 0
        for i, u in enumerate(neigh):
            au = graph.adjacency[u]
            for w in neigh[i + 1 :]:
                if (au >> w) & 1:
                    edges_among += 1
        nd_samples.append(edges_among / (d * (d - 1) / 2.0))
    nd_mean = statistics.fmean(nd_samples) if nd_samples else 0.0
    nd_std = statistics.pstdev(nd_samples) if len(nd_samples) > 1 else 0.0

    # --- high-degree subset internal density ---
    k_hi = max(1, int(math.ceil(high_degree_frac * n))) if n else 1
    hi = sorted(range(n), key=lambda v: degrees[v], reverse=True)[:k_hi]
    hi_edges = 0
    for i, u in enumerate(hi):
        au = graph.adjacency[u]
        for v in hi[i + 1 :]:
            if (au >> v) & 1:
                hi_edges += 1
    hi_possible = k_hi * (k_hi - 1) // 2
    hi_dens = (hi_edges / hi_possible) if hi_possible else 0.0

    # degree std vs ER binomial approx: Var(deg) ≈ (n-1)p(1-p)
    er_var = (n - 1) * dens * (1.0 - dens) if n > 1 else 0.0
    er_std = math.sqrt(er_var) if er_var > 0 else 0.0
    degree_vs_er_z = ((deg_std - er_std) / er_std) if er_std > 1e-12 else 0.0

    thr, log_at, log_next = er_expected_count_threshold(n, dens)

    ms = (time.perf_counter() - t0) * 1000.0
    return GraphFingerprint(
        name=graph.name or "",
        n=n,
        m=m,
        density=dens,
        avg_degree=avg_deg,
        min_degree=min_d,
        max_degree=max_d,
        degree_std=deg_std,
        degree_cv=deg_cv,
        complement_density=1.0 - dens,
        degree_p10=_percentile(sorted_deg, 10),
        degree_p50=_percentile(sorted_deg, 50),
        degree_p90=_percentile(sorted_deg, 90),
        sampled_triangle_count=tri_count,
        sampled_wedge_count=wedge_count,
        sampled_triangle_density=tri_density,
        mean_local_clustering=mean_cl,
        clustering_std=cl_std,
        cn_edge_mean=cn_e_mean,
        cn_edge_std=cn_e_std,
        cn_edge_p90=cn_e_p90,
        cn_nonedge_mean=cn_n_mean,
        cn_nonedge_std=cn_n_std,
        cn_nonedge_p90=cn_n_p90,
        neigh_density_mean=nd_mean,
        neigh_density_std=nd_std,
        high_degree_internal_density=hi_dens,
        degree_vs_er_z=degree_vs_er_z,
        er_expected_count_threshold=thr,
        er_log_expected_at_threshold=log_at,
        er_log_expected_at_threshold_plus1=log_next,
        fingerprint_ms=ms,
        sample_seed=seed,
        extras={
            "cn_edge_samples": len(cn_edge),
            "cn_nonedge_samples": len(cn_non),
            "clustering_samples": len(clustering),
            "cn_edge_vs_nonedge_mean_ratio": (cn_e_mean / cn_n_mean) if cn_n_mean > 1e-12 else float("inf"),
        },
    )
