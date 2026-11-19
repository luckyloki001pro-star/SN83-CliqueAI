"""Integer-bitset helpers for adjacency and candidate sets."""

from __future__ import annotations

from typing import Iterator, List


def bit_count(mask: int) -> int:
    return mask.bit_count()


def lowest_bit(mask: int) -> int:
    """Return the lowest set bit as a power-of-two integer, or 0."""
    return mask & -mask


def lowest_vertex(mask: int) -> int:
    """Index of the lowest set bit. Undefined if mask == 0."""
    return (mask & -mask).bit_length() - 1


def iter_bits(mask: int) -> Iterator[int]:
    """Yield vertex indices of set bits, low to high."""
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def bits_to_list(mask: int) -> List[int]:
    out: List[int] = []
    while mask:
        bit = mask & -mask
        out.append(bit.bit_length() - 1)
        mask ^= bit
    return out


def list_to_mask(vertices: List[int] | set[int]) -> int:
    mask = 0
    for v in vertices:
        mask |= 1 << v
    return mask


def clear_bit(mask: int, v: int) -> int:
    return mask & ~(1 << v)


def set_bit(mask: int, v: int) -> int:
    return mask | (1 << v)


def has_bit(mask: int, v: int) -> bool:
    return (mask >> v) & 1 == 1


def intersect_neighbors(mask: int, adjacency: List[int], v: int) -> int:
    return mask & adjacency[v]


def full_mask(n: int) -> int:
    return (1 << n) - 1 if n > 0 else 0
