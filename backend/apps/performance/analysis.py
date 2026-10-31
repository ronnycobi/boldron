"""Honest statistics over recorded performance samples (spec §41)."""
from __future__ import annotations


def percentile(sorted_values: list[int], p: float) -> int | None:
    """Nearest-rank percentile of already-sorted values. None when empty."""
    if not sorted_values:
        return None
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    import math
    rank = math.ceil(p / 100 * len(sorted_values))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def stats_for(durations: list[int]) -> dict:
    """Count / avg / p50 / p95 / max over a list of real durations."""
    if not durations:
        return {"count": 0, "avg": None, "p50": None, "p95": None, "max": None}
    s = sorted(durations)
    return {
        "count": len(s),
        "avg": round(sum(s) / len(s)),
        "p50": percentile(s, 50),
        "p95": percentile(s, 95),
        "max": s[-1],
    }
