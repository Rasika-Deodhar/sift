"""Perceptual-hash cache: avoid paying for a model call on content we already understood."""

from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")

_POP = [bin(i).count("1") for i in range(16)]


def hash_distance(a: str, b: str) -> float:
    """Normalized Hamming distance between equal-length hex hashes (1.0 if lengths differ)."""
    if len(a) != len(b) or not a:
        return 1.0
    try:
        d = sum(_POP[int(x, 16) ^ int(y, 16)] for x, y in zip(a, b, strict=True))
    except ValueError:
        return 1.0
    return d / (len(a) * 4)


def sig_distance(a: str, b: str) -> float:
    """Mean absolute difference of two hex color signatures (one byte per channel, 0-255)."""
    if len(a) != len(b) or not a or len(a) % 2:
        return 255.0
    try:
        va = bytes.fromhex(a)
        vb = bytes.fromhex(b)
    except ValueError:
        return 255.0
    return sum(abs(x - y) for x, y in zip(va, vb, strict=True)) / len(va)


class PhashCache(Generic[T]):
    """LRU map from perceptual hash -> value, with near-match lookup.

    Feed posts share layout, so a structural hash alone can match two different posts. When a
    color signature is available, a hit also requires the colors to match.
    """

    def __init__(
        self, max_distance: float = 0.02, capacity: int = 500, max_sig_distance: float = 3.0
    ) -> None:
        self.max_distance = max_distance
        self.max_sig_distance = max_sig_distance
        self.capacity = capacity
        # hash -> (owner id, value, color signature)
        self._data: OrderedDict[str, tuple[str, T, str]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._data)

    def lookup(self, phash: str, sig: str = "") -> tuple[str, T] | None:
        """Returns (owner_id, value) of the closest cached hash within max_distance."""
        best: tuple[float, str] | None = None
        for h, (_, _, s) in self._data.items():
            d = hash_distance(phash, h)
            if d > self.max_distance or (best is not None and d >= best[0]):
                continue
            if sig and s and sig_distance(sig, s) > self.max_sig_distance:
                continue
            best = (d, h)
        if best is None:
            self.misses += 1
            return None
        self.hits += 1
        self._data.move_to_end(best[1])
        owner, value, _ = self._data[best[1]]
        return owner, value

    def put(self, phash: str, owner_id: str, value: T, sig: str = "") -> None:
        self._data[phash] = (owner_id, value, sig)
        self._data.move_to_end(phash)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()
        self.hits = self.misses = 0
