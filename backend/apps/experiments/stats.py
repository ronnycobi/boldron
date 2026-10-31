"""Honest significance testing for experiment results (spec §20).

A two-proportion z-test over the real exposure/conversion counts. It only ever
reports a leader when the data supports it; with too little data it says so,
rather than inventing a winner.
"""
from __future__ import annotations

import math

# Don't call anything before this many exposures per compared variant.
MIN_SAMPLE = 100
# Two-sided significance threshold.
ALPHA = 0.05


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def two_proportion_p(c1: int, n1: int, c2: int, n2: int) -> float | None:
    """Two-sided p-value for a difference in conversion rates. None if undefined."""
    if n1 <= 0 or n2 <= 0:
        return None
    p1, p2 = c1 / n1, c2 / n2
    pool = (c1 + c2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    z = (p1 - p2) / se
    return 2 * (1 - _normal_cdf(abs(z)))


def assess(variants: list[dict]) -> dict:
    """Given [{key, exposures, conversions, rate}], decide — honestly — whether
    there's a significant leader yet."""
    ranked = sorted(variants, key=lambda v: v["rate"], reverse=True)
    if len(ranked) < 2:
        return {"status": "inconclusive", "reason": "Need at least two variants.",
                "leader": None}
    best, second = ranked[0], ranked[1]
    if best["exposures"] < MIN_SAMPLE or second["exposures"] < MIN_SAMPLE:
        return {"status": "collecting",
                "reason": f"Not enough data yet (need ≥{MIN_SAMPLE} per variant).",
                "leader": None}
    p = two_proportion_p(best["conversions"], best["exposures"],
                         second["conversions"], second["exposures"])
    if p is None or p >= ALPHA:
        return {"status": "inconclusive",
                "reason": "No statistically significant difference yet.",
                "leader": None, "p_value": p}
    return {"status": "significant",
            "reason": f"{best['key']} leads significantly (p={p:.3f}).",
            "leader": best["key"], "p_value": p}
