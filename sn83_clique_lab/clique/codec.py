"""Base92 graph codec compatible with CliqueAI GraphCodec."""

from __future__ import annotations

import math
from typing import List

from .graph import BitsetGraph

DEFAULT_BASE92_ALPHABET = "".join(
    chr(c) for c in range(32, 127) if c not in (34, 39, 92)
)


class GraphCodec:
    """Bitwise Base92 adjacency-matrix codec (SN83-compatible)."""

    def __init__(
        self,
        hdr_digits: int = 5,
        chunk_bits: int = 1246,
        chunk_digits: int = 191,
    ) -> None:
        self.alphabet = DEFAULT_BASE92_ALPHABET
        self.index = {ch: i for i, ch in enumerate(self.alphabet)}
        self.HDR_DIGITS = hdr_digits
        self.CHUNK_BITS = chunk_bits
        self.CHUNK_DIGITS = chunk_digits

    def _min_digits_for_bits(self, r_bits: int) -> int:
        if r_bits <= 0:
            return 0
        m = math.ceil(r_bits / math.log2(len(self.alphabet)))
        while (len(self.alphabet) ** (m - 1) if m > 0 else 0) >= (1 << r_bits):
            m -= 1
        while len(self.alphabet) ** m < (1 << r_bits):
            m += 1
        return m

    def _enc_fixed_int(self, val: int, digits: int) -> str:
        out = []
        base = len(self.alphabet)
        for _ in range(digits):
            val, rem = divmod(val, base)
            out.append(self.alphabet[rem])
        if val:
            raise ValueError("Overflow...")
        return "".join(reversed(out))

    def _dec_fixed_to_int(self, s: str) -> int:
        val = 0
        base = len(self.alphabet)
        for ch in s:
            if ch not in self.index:
                raise ValueError(f"invalid base92 char: {repr(ch)}")
            val = val * base + self.index[ch]
        return val

    def decode_matrix(self, s: str) -> List[List[int]]:
        if len(s) < self.HDR_DIGITS:
            raise ValueError("truncated header")
        n = self._dec_fixed_to_int(s[: self.HDR_DIGITS])
        total_bits = n * (n - 1) // 2
        full = total_bits // self.CHUNK_BITS
        rem_bits = total_bits % self.CHUNK_BITS
        tail_digits = self._min_digits_for_bits(rem_bits)
        expected = self.HDR_DIGITS + full * self.CHUNK_DIGITS + tail_digits
        if len(s) != expected:
            raise ValueError(
                f"length mismatch: got {len(s)}, expect {expected} for n={n}"
            )

        pos = self.HDR_DIGITS

        def next_chunk():
            nonlocal pos, full, rem_bits
            if full:
                chunk_str = s[pos : pos + self.CHUNK_DIGITS]
                pos += self.CHUNK_DIGITS
                full -= 1
                return self._dec_fixed_to_int(chunk_str), self.CHUNK_BITS
            if rem_bits:
                m = self._min_digits_for_bits(rem_bits)
                chunk_str = s[pos : pos + m]
                pos += m
                b = rem_bits
                rem_bits = 0
                return self._dec_fixed_to_int(chunk_str), b
            return None

        adj_matrix = [[0] * n for _ in range(n)]
        if total_bits == 0:
            return adj_matrix

        result = next_chunk()
        if result is None:
            raise ValueError("Unexpected end of encoded string")
        val, bits_left = result

        for i in range(n):
            for j in range(i + 1, n):
                if bits_left == 0:
                    result = next_chunk()
                    if result is None:
                        raise ValueError("Unexpected end of encoded string")
                    val, bits_left = result
                bit = (val >> (bits_left - 1)) & 1
                bits_left -= 1
                adj_matrix[i][j] = adj_matrix[j][i] = int(bit)
        return adj_matrix

    def matrix_to_list(self, adj_matrix: List[List[int]]) -> List[List[int]]:
        return [
            [j for j, v in enumerate(row) if v == 1]
            for row in adj_matrix
        ]

    def decode_graph(self, encoded: str, name: str = "") -> BitsetGraph:
        mat = self.decode_matrix(encoded)
        n = len(mat)
        edges = 0
        for i in range(n):
            if mat[i][i] != 0:
                raise ValueError("diagonal must be 0")
            for j in range(i + 1, n):
                if mat[i][j] != mat[j][i]:
                    raise ValueError("matrix must be symmetric")
                if mat[i][j]:
                    edges += 1
        g = BitsetGraph.from_adjacency_list(
            self.matrix_to_list(mat),
            name=name,
            metadata={"edges": edges, "source": "base92"},
        )
        return g
