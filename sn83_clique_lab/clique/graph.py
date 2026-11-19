"""Bitset graph representation for undirected loop-free graphs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from .bitset import bits_to_list, full_mask, has_bit, iter_bits


@dataclass(slots=True)
class BitsetGraph:
    """Undirected simple graph with integer adjacency bitsets."""

    n: int
    adjacency: List[int]
    labels: List[int] = field(default_factory=list)
    name: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.labels:
            self.labels = list(range(self.n))
        if len(self.adjacency) != self.n:
            raise ValueError("adjacency length must equal n")
        if len(self.labels) != self.n:
            raise ValueError("labels length must equal n")

    @classmethod
    def empty(cls, n: int, name: str = "") -> "BitsetGraph":
        return cls(n=n, adjacency=[0] * n, name=name)

    @classmethod
    def from_adjacency_list(
        cls,
        adjacency_list: Sequence[Sequence[int]],
        labels: Sequence[int] | None = None,
        name: str = "",
        metadata: dict | None = None,
    ) -> "BitsetGraph":
        n = len(adjacency_list)
        adj = [0] * n
        for u, neighbors in enumerate(adjacency_list):
            mask = 0
            for v in neighbors:
                if v == u:
                    continue
                if not (0 <= v < n):
                    raise ValueError(f"neighbor {v} out of range for n={n}")
                mask |= 1 << v
            adj[u] = mask
        # Enforce undirected symmetry.
        for u in range(n):
            for v in iter_bits(adj[u]):
                if not ((adj[v] >> u) & 1):
                    adj[v] |= 1 << u
        return cls(
            n=n,
            adjacency=adj,
            labels=list(labels) if labels is not None else list(range(n)),
            name=name,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_edge_list(
        cls,
        n: int,
        edges: Iterable[tuple[int, int]],
        name: str = "",
        metadata: dict | None = None,
    ) -> "BitsetGraph":
        g = cls.empty(n, name=name)
        g.metadata = dict(metadata or {})
        for u, v in edges:
            g.add_edge(u, v)
        return g

    def add_edge(self, u: int, v: int) -> None:
        if u == v:
            return
        self.adjacency[u] |= 1 << v
        self.adjacency[v] |= 1 << u

    def has_edge(self, u: int, v: int) -> bool:
        return has_bit(self.adjacency[u], v)

    def neighbors_mask(self, v: int) -> int:
        return self.adjacency[v]

    def neighbors(self, v: int) -> List[int]:
        return bits_to_list(self.adjacency[v])

    def degree(self, v: int) -> int:
        return self.adjacency[v].bit_count()

    def degrees(self) -> List[int]:
        return [a.bit_count() for a in self.adjacency]

    def edge_count(self) -> int:
        return sum(a.bit_count() for a in self.adjacency) // 2

    def density(self) -> float:
        if self.n <= 1:
            return 0.0
        return (2.0 * self.edge_count()) / (self.n * (self.n - 1))

    def all_vertices_mask(self) -> int:
        return full_mask(self.n)

    def induced_common_neighbors(self, vertices: Sequence[int]) -> int:
        if not vertices:
            return self.all_vertices_mask()
        mask = self.adjacency[vertices[0]]
        for v in vertices[1:]:
            mask &= self.adjacency[v]
        return mask

    def to_adjacency_list(self) -> List[List[int]]:
        return [bits_to_list(a) for a in self.adjacency]

    def to_labels(self, internal_vertices: Sequence[int]) -> List[int]:
        return [self.labels[v] for v in internal_vertices]

    def content_hash(self) -> str:
        payload = {
            "n": self.n,
            "edges": [
                [u, v]
                for u in range(self.n)
                for v in bits_to_list(self.adjacency[u])
                if v > u
            ],
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()

    def validate_undirected(self) -> bool:
        for u in range(self.n):
            if has_bit(self.adjacency[u], u):
                return False
            for v in iter_bits(self.adjacency[u]):
                if not has_bit(self.adjacency[v], u):
                    return False
        return True
