"""The data-quality check engine (spec §9).

Deterministic checks evaluated against REAL rows: a rule is run over the data the
caller supplies and the result is a true count of violations, not an estimate.
No row data is invented and no check "passes" unless the data genuinely satisfies
it; a check that can't be evaluated (unknown type) is reported, never silently
treated as passing.
"""
from __future__ import annotations

import re

CHECKS = {
    "not_null": "Must be present and non-empty",
    "unique": "Must be unique across rows",
    "allowed_values": "Must be one of a set of values",
    "regex": "Must match a pattern",
    "range": "Must be a number within a range",
    "min_length": "Must be at least a given length",
}

_MISSING = object()


def _is_empty(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def validate_rule(check: str, params: dict) -> tuple[bool, str]:
    if check not in CHECKS:
        return False, f"Unknown check '{check}'."
    params = params or {}
    if check == "allowed_values" and not isinstance(params.get("values"), list):
        return False, "allowed_values needs a 'values' list."
    if check == "regex":
        pattern = params.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return False, "regex needs a 'pattern'."
        try:
            re.compile(pattern)
        except re.error as exc:
            return False, f"Invalid pattern: {exc}"
    if check == "range" and params.get("min") is None and params.get("max") is None:
        return False, "range needs a 'min' and/or 'max'."
    if check == "min_length" and not isinstance(params.get("min"), int):
        return False, "min_length needs an integer 'min'."
    return True, ""


def _row_fails(check: str, params: dict, value) -> bool:
    """Whether one value fails the check. A missing/empty value only fails
    not_null; other checks skip empties (they validate shape, not presence)."""
    if check == "not_null":
        return _is_empty(value)
    if _is_empty(value):
        return False
    if check == "allowed_values":
        return value not in params.get("values", [])
    if check == "regex":
        return re.search(params["pattern"], str(value)) is None
    if check == "range":
        try:
            n = float(value)
        except (TypeError, ValueError):
            return True
        lo, hi = params.get("min"), params.get("max")
        if lo is not None and n < lo:
            return True
        if hi is not None and n > hi:
            return True
        return False
    if check == "min_length":
        return len(str(value)) < params["min"]
    return False


def run_rule(rule, rows: list[dict]) -> dict:
    """Evaluate one rule across rows. Returns real checked/violation counts and a
    small sample of offending values (the caller's own data) for actionability."""
    field, check, params = rule["field"], rule["check"], rule.get("params") or {}
    checked = violations = 0
    samples = []
    seen = {}
    for i, row in enumerate(rows):
        value = row.get(field, _MISSING)
        if check == "unique":
            checked += 1
            key = None if value is _MISSING else value
            if _is_empty(key):
                continue
            if key in seen:
                violations += 1
                if len(samples) < 5:
                    samples.append({"row": i, "value": key})
            else:
                seen[key] = i
            continue
        checked += 1
        val = None if value is _MISSING else value
        if _row_fails(check, params, val):
            violations += 1
            if len(samples) < 5:
                samples.append({"row": i, "value": val})
    return {
        "field": field, "check": check,
        "checked": checked, "violations": violations,
        "passed": violations == 0,
        "compliance": round((checked - violations) / checked * 100, 1) if checked else None,
        "samples": samples,
        "severity": rule.get("severity", "error"),
    }


def evaluate(rules: list[dict], rows: list[dict]) -> dict:
    """Run all rules over rows; returns per-rule results and an honest dataset
    score (the mean rule compliance, errors weighted double). None when there is
    nothing to score."""
    results = [run_rule(r, rows) for r in rules]
    scored = [r for r in results if r["compliance"] is not None]
    if not scored:
        score = None
    else:
        num = den = 0.0
        for r in scored:
            w = 2 if r["severity"] == "error" else 1
            num += r["compliance"] * w
            den += w
        score = round(num / den) if den else None
    return {
        "rows": len(rows),
        "score": score,
        "rules": results,
        "failing": sum(1 for r in results if not r["passed"]),
    }
