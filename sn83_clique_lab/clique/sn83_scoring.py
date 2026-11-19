"""Exact local reproduction of CliqueAI CliqueScoreCalculator.

Authority: /home/CliqueAI/CliqueAI/scoring/clique_scoring.py

Field semantics as logged by validator.py (NOT the swapped W&B docs table):
  miner_omega      = raw omega = exp(-pr/rel) for valid responses
  miner_optimality = normalized omega = omega / max(omega)
  miner_diversity  = normalized uniqueness among valid responses
  miner_rewards    = optimality * (1 + difficulty) + diversity
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np


@dataclass(slots=True)
class GraphView:
    number_of_nodes: int
    adjacency_list: List[List[int]]


@dataclass
class ScoreArrays:
    rel: np.ndarray
    pr: np.ndarray
    omega: np.ndarray  # raw
    optimality: np.ndarray  # normalized omega
    diversity: np.ndarray
    rewards: np.ndarray
    validity: np.ndarray
    effective_size: np.ndarray


class CliqueScoreCalculator:
    """Byte-compatible scoring logic with the official validator calculator."""

    def __init__(
        self,
        graph: GraphView,
        difficulty: float,
        responses: List[List[int]],
    ) -> None:
        self.graph = graph
        self.difficulty = difficulty
        self.responses = responses
        # Precompute neighbor sets for faster maximality checks on large graphs.
        self._neighbor_sets = [set(nbrs) for nbrs in graph.adjacency_list]

    def is_valid_maximum_clique(self, nodes: List[int]) -> bool:
        node_set = set(nodes)
        if len(node_set) == 0:
            return False
        if len(node_set) != len(nodes):
            return False
        if not node_set.issubset(range(self.graph.number_of_nodes)):
            return False
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if nodes[j] not in self._neighbor_sets[nodes[i]]:
                    return False
        all_nodes = set(range(self.graph.number_of_nodes))
        remaining_nodes = all_nodes - node_set
        for candidate in remaining_nodes:
            if node_set.issubset(self._neighbor_sets[candidate]):
                return False
        return True

    def optimality(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        val = np.array(
            [1 if self.is_valid_maximum_clique(response) else 0 for response in self.responses]
        )
        size = np.array([len(response) for response in self.responses]) * val
        zeros = np.zeros(len(self.responses))
        if len(size) == 0:
            return zeros, zeros, zeros, zeros
        max_size = np.max(size)
        if max_size <= 0:
            return zeros, zeros, zeros, zeros
        rel = size / max_size
        pr = np.array([np.sum(size > size[i]) / len(size) for i in range(len(size))])
        omega = np.zeros(len(self.responses))
        for i, valid in enumerate(val):
            if valid:
                omega[i] = np.exp(-pr[i] / rel[i])
        max_omega = np.max(omega)
        if max_omega == 0:
            return rel, pr, omega, omega
        omega_normalized = omega / max_omega
        return rel, pr, omega, omega_normalized

    def diversity(self) -> np.ndarray:
        val = np.array(
            [1 if self.is_valid_maximum_clique(response) else 0 for response in self.responses]
        )
        canonical_responses = [tuple(sorted(r)) for r in self.responses]
        counts = Counter(canonical_responses)
        unq = np.array([1 / counts[sol] for sol in canonical_responses])
        delta = val * unq
        if len(delta) == 0:
            return np.array([])
        max_delta = np.max(delta)
        if max_delta == 0:
            return delta
        return delta / max_delta

    def get_scores(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        rel, pr, omega, optimality = self.optimality()
        diversity = self.diversity()
        rewards = optimality * (1 + self.difficulty) + diversity
        return rel, pr, omega, optimality, diversity, rewards

    def score_detailed(self) -> ScoreArrays:
        rel, pr, omega, optimality, diversity, rewards = self.get_scores()
        validity = np.array(
            [1 if self.is_valid_maximum_clique(r) else 0 for r in self.responses],
            dtype=float,
        )
        effective_size = np.array([len(r) for r in self.responses], dtype=float) * validity
        return ScoreArrays(
            rel=rel,
            pr=pr,
            omega=omega,
            optimality=optimality,
            diversity=diversity,
            rewards=rewards,
            validity=validity,
            effective_size=effective_size,
        )


def competition_rank(scores: Sequence[float], index: int) -> tuple[int, int]:
    """
    Competition rank: 1 + count(strictly higher).
    Returns (rank, n_tied_at_same_score).
    """
    s = float(scores[index])
    higher = sum(1 for x in scores if float(x) > s)
    tied = sum(1 for x in scores if float(x) == s)
    return higher + 1, tied
