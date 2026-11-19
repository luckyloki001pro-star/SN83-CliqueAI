"""Centered-adjacency spectral ranking (pure Python).

Defines B[i,j] = A[i,j] - p for i!=j, B[i,i]=0, and computes leading
eigenpairs via a small Lanczos iteration with Python matvecs.

NOT a line-by-line reproduction of arXiv:2210.02121 / planted-clique papers.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .bitset import bits_to_list, iter_bits
from .graph import BitsetGraph


@dataclass
class SpectralResult:
    n: int
    density: float = 0.0
    iterations: int = 0
    eigenvalues: List[float] = field(default_factory=list)
    eigenvectors: List[List[float]] = field(default_factory=list)
    residuals: List[float] = field(default_factory=list)
    construct_ms: float = 0.0
    matvec_ms: float = 0.0
    total_ms: float = 0.0
    stopped_early: bool = False
    method: str = "lanczos"
    extras: Dict[str, float] = field(default_factory=dict)


def centered_matvec(
    graph: BitsetGraph,
    x: Sequence[float],
    p: float,
    out: Optional[List[float]] = None,
) -> List[float]:
    """Compute y = Bx where B[i,j]=A[i,j]-p (i!=j), B[i,i]=0.

    Identity: (Bx)_i = (Ax)_i - p * (sum_j x_j - x_i)
    """
    n = graph.n
    if out is None:
        out = [0.0] * n
    else:
        for i in range(n):
            out[i] = 0.0
    s = 0.0
    for xi in x:
        s += xi
    for i in range(n):
        ax = 0.0
        for j in iter_bits(graph.adjacency[i]):
            ax += x[j]
        out[i] = ax - p * (s - x[i])
    return out


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def _axpy(y: List[float], a: float, x: Sequence[float]) -> None:
    for i in range(len(y)):
        y[i] += a * x[i]


def _scale(x: List[float], a: float) -> None:
    for i in range(len(x)):
        x[i] *= a


def _copy(x: Sequence[float]) -> List[float]:
    return list(x)


def _sym_tridiag_eig(alpha: Sequence[float], beta: Sequence[float]) -> Tuple[List[float], List[List[float]]]:
    """Eigen-decompose small symmetric tridiagonal via Jacobi (pure Python).

    Returns eigenvalues (descending by abs for selection later) and eigenvectors
    as columns of Q in the Krylov basis (each vector length m).
    """
    m = len(alpha)
    if m == 0:
        return [], []
    # Dense copy of T
    A = [[0.0] * m for _ in range(m)]
    for i in range(m):
        A[i][i] = alpha[i]
        if i + 1 < m:
            A[i][i + 1] = beta[i]
            A[i + 1][i] = beta[i]
    V = [[1.0 if i == j else 0.0 for j in range(m)] for i in range(m)]
    # Jacobi sweeps
    for _ in range(40 * m):
        # find largest off-diagonal
        p = 0
        q = 1
        max_abs = 0.0
        for i in range(m):
            for j in range(i + 1, m):
                if abs(A[i][j]) > max_abs:
                    max_abs = abs(A[i][j])
                    p, q = i, j
        if max_abs < 1e-12:
            break
        app, aqq, apq = A[p][p], A[q][q], A[p][q]
        tau = (aqq - app) / (2.0 * apq) if apq != 0 else 0.0
        t = math.copysign(1.0 / (abs(tau) + math.sqrt(1.0 + tau * tau)), tau) if tau != 0 else 1.0
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c
        # rotate A
        for k in range(m):
            if k == p or k == q:
                continue
            aik, aiq = A[k][p], A[k][q]
            A[k][p] = c * aik - s * aiq
            A[p][k] = A[k][p]
            A[k][q] = s * aik + c * aiq
            A[q][k] = A[k][q]
        A[p][p] = app - t * apq
        A[q][q] = aqq + t * apq
        A[p][q] = 0.0
        A[q][p] = 0.0
        for k in range(m):
            vip, viq = V[k][p], V[k][q]
            V[k][p] = c * vip - s * viq
            V[k][q] = s * vip + c * viq
    evals = [A[i][i] for i in range(m)]
    evecs = [[V[i][j] for i in range(m)] for j in range(m)]  # column j
    # sort by algebraic value descending (largest eigenvalue first)
    order = sorted(range(m), key=lambda i: evals[i], reverse=True)
    return [evals[i] for i in order], [evecs[i] for i in order]


def lanczos_centered(
    graph: BitsetGraph,
    max_iter: int = 16,
    n_eigs: int = 3,
    seed_vec: Optional[Sequence[float]] = None,
    deadline: Optional[float] = None,
    p: Optional[float] = None,
) -> SpectralResult:
    """Lanczos on centered adjacency B; returns top algebraic eigenpairs."""
    t0 = time.perf_counter()
    n = graph.n
    dens = graph.density() if p is None else float(p)
    res = SpectralResult(n=n, density=dens, method="lanczos")
    if n == 0:
        res.total_ms = 0.0
        return res
    t_construct = time.perf_counter()
    # no explicit matrix — only density cached
    res.construct_ms = (time.perf_counter() - t_construct) * 1000.0

    # initial vector
    if seed_vec is not None and len(seed_vec) == n:
        v = _copy(seed_vec)
    else:
        # deterministic pseudo-random from indices
        v = [math.sin(0.7 * (i + 1)) for i in range(n)]
    nv = _norm(v)
    if nv < 1e-15:
        v = [1.0] + [0.0] * (n - 1)
        nv = 1.0
    _scale(v, 1.0 / nv)

    V: List[List[float]] = []
    alpha: List[float] = []
    beta: List[float] = []
    matvec_ms = 0.0
    wbuf = [0.0] * n
    stopped = False
    iters = 0
    max_iter = max(1, min(max_iter, n))

    for j in range(max_iter):
        if deadline is not None and time.perf_counter() >= deadline:
            stopped = True
            break
        V.append(_copy(v))
        tmv = time.perf_counter()
        centered_matvec(graph, v, dens, out=wbuf)
        matvec_ms += (time.perf_counter() - tmv) * 1000.0
        w = _copy(wbuf)
        if j > 0:
            _axpy(w, -beta[j - 1], V[j - 1])
        a = _dot(v, w)
        alpha.append(a)
        _axpy(w, -a, v)
        # full reorthogonalization against previous V
        for vi in V:
            c = _dot(w, vi)
            _axpy(w, -c, vi)
        b = _norm(w)
        beta.append(b)
        iters = j + 1
        if b < 1e-12:
            break
        v = [wi / b for wi in w]

    # trim last unused beta
    if beta and (len(beta) == len(alpha)):
        # beta[j] is ||w|| after step j; for eig of T we need off-diagonals beta[0..m-2]
        pass
    m = len(alpha)
    beta_off = beta[: m - 1] if m else []
    evals_T, evecs_T = _sym_tridiag_eig(alpha, beta_off)

    # reconstruct Ritz vectors in R^n; take top n_eigs by algebraic eigenvalue
    keep = min(n_eigs, len(evals_T))
    eigs: List[float] = []
    vecs: List[List[float]] = []
    residuals: List[float] = []
    for k in range(keep):
        lam = evals_T[k]
        y = evecs_T[k]
        x = [0.0] * n
        for j in range(len(y)):
            coef = y[j]
            vj = V[j]
            for i in range(n):
                x[i] += coef * vj[i]
        nx = _norm(x)
        if nx > 0:
            _scale(x, 1.0 / nx)
        # residual ||Bx - lam x||
        tmv = time.perf_counter()
        centered_matvec(graph, x, dens, out=wbuf)
        matvec_ms += (time.perf_counter() - tmv) * 1000.0
        rnorm = math.sqrt(sum((wbuf[i] - lam * x[i]) ** 2 for i in range(n)))
        eigs.append(lam)
        vecs.append(x)
        residuals.append(rnorm)

    res.iterations = iters
    res.eigenvalues = eigs
    res.eigenvectors = vecs
    res.residuals = residuals
    res.matvec_ms = matvec_ms
    res.stopped_early = stopped
    res.total_ms = (time.perf_counter() - t0) * 1000.0
    return res


def power_iteration_abs(
    graph: BitsetGraph,
    max_iter: int = 16,
    deadline: Optional[float] = None,
    p: Optional[float] = None,
) -> SpectralResult:
    """Control: power iteration → eigenvalue of largest |λ| (may be negative)."""
    t0 = time.perf_counter()
    n = graph.n
    dens = graph.density() if p is None else float(p)
    res = SpectralResult(n=n, density=dens, method="power_abs")
    if n == 0:
        return res
    v = [math.sin(0.5 * (i + 1)) for i in range(n)]
    nv = _norm(v) or 1.0
    _scale(v, 1.0 / nv)
    wbuf = [0.0] * n
    lam = 0.0
    matvec_ms = 0.0
    stopped = False
    it = 0
    for it in range(1, max_iter + 1):
        if deadline is not None and time.perf_counter() >= deadline:
            stopped = True
            break
        tmv = time.perf_counter()
        centered_matvec(graph, v, dens, out=wbuf)
        matvec_ms += (time.perf_counter() - tmv) * 1000.0
        lam = _dot(v, wbuf)
        nw = _norm(wbuf)
        if nw < 1e-15:
            break
        v = [wi / nw for wi in wbuf]
    centered_matvec(graph, v, dens, out=wbuf)
    rnorm = math.sqrt(sum((wbuf[i] - lam * v[i]) ** 2 for i in range(n)))
    res.iterations = it
    res.eigenvalues = [lam]
    res.eigenvectors = [v]
    res.residuals = [rnorm]
    res.matvec_ms = matvec_ms
    res.stopped_early = stopped
    res.total_ms = (time.perf_counter() - t0) * 1000.0
    res.extras["note_largest_abs_not_necessarily_largest_algebraic"] = 1.0
    return res


def rank_from_eigenvector(
    vec: Sequence[float],
    mode: str = "abs",
) -> List[int]:
    """Return vertex indices sorted by spectral score (best first)."""
    n = len(vec)
    if mode == "abs":
        key = lambda i: abs(vec[i])
        reverse = True
    elif mode == "pos":
        key = lambda i: vec[i]
        reverse = True
    elif mode == "neg":
        key = lambda i: vec[i]
        reverse = False
    else:
        raise ValueError(mode)
    return sorted(range(n), key=key, reverse=reverse)


def combined_scores(
    vec: Sequence[float],
    residual_degree: Sequence[float],
    alpha: float = 0.6,
    beta: float = 0.4,
    use_abs: bool = True,
) -> List[float]:
    """alpha * |norm spectral| + beta * norm residual degree."""
    n = len(vec)
    svals = [abs(vec[i]) if use_abs else vec[i] for i in range(n)]
    smin, smax = min(svals), max(svals)
    dmin, dmax = min(residual_degree), max(residual_degree)
    sspan = (smax - smin) or 1.0
    dspan = (dmax - dmin) or 1.0
    out = []
    for i in range(n):
        sn = (svals[i] - smin) / sspan
        dn = (residual_degree[i] - dmin) / dspan
        out.append(alpha * sn + beta * dn)
    return out


def induced_subgraph(graph: BitsetGraph, vertices: Sequence[int], name: str = "") -> Tuple[BitsetGraph, List[int]]:
    """Build induced subgraph; returns (subgraph, map local->global)."""
    verts = list(dict.fromkeys(vertices))
    n = len(verts)
    g2l = {v: i for i, v in enumerate(verts)}
    edges = []
    for i, u in enumerate(verts):
        au = graph.adjacency[u]
        for v in verts[i + 1 :]:
            if (au >> v) & 1:
                edges.append((i, g2l[v]))
    return BitsetGraph.from_edge_list(n, edges, name=name or f"induced_{n}"), verts
