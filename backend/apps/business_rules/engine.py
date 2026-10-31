"""The business-rule evaluation engine (spec §12-13).

Deterministic, offline, no AI: a rule's `when` conditions are compared against a
dict of facts with a fixed set of operators, and a rule fires only when every
condition holds. This is the real decision logic — the same way the platform
keeps money/stock/auth deterministic — so a rule the engine reports as fired
genuinely did, and one it can't evaluate never silently "passes".
"""
from __future__ import annotations

from numbers import Number

_MISSING = object()


def _num(v):
    """Coerce to a number for ordered comparisons; returns None if not numeric."""
    if isinstance(v, bool):
        return None
    if isinstance(v, Number):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cmp(op, a, b, fn):
    na, nb = _num(a), _num(b)
    if na is None or nb is None:
        return False
    return fn(na, nb)


# Operator -> predicate(actual, expected). Ordered ops return False on
# non-numeric operands rather than raising, so evaluation stays total.
_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: _cmp("gt", a, b, lambda x, y: x > y),
    "gte": lambda a, b: _cmp("gte", a, b, lambda x, y: x >= y),
    "lt": lambda a, b: _cmp("lt", a, b, lambda x, y: x < y),
    "lte": lambda a, b: _cmp("lte", a, b, lambda x, y: x <= y),
    "in": lambda a, b: isinstance(b, (list, tuple)) and a in b,
    "not_in": lambda a, b: isinstance(b, (list, tuple)) and a not in b,
    "contains": lambda a, b: isinstance(a, (list, tuple, str)) and b in a,
}

OPERATORS = tuple(_OPS)


def validate_definition(defn) -> tuple[bool, str]:
    """Validate a rule definition's shape. Returns (ok, error)."""
    if not isinstance(defn, dict):
        return False, "Definition must be an object."
    when = defn.get("when", [])
    if not isinstance(when, list):
        return False, "'when' must be a list of conditions."
    for i, cond in enumerate(when):
        if not isinstance(cond, dict):
            return False, f"Condition {i} must be an object."
        fact = cond.get("fact")
        if not isinstance(fact, str) or not fact.strip():
            return False, f"Condition {i} needs a non-empty 'fact'."
        if cond.get("op") not in _OPS:
            return False, f"Condition {i} has an unknown operator '{cond.get('op')}'."
        if "value" not in cond:
            return False, f"Condition {i} needs a 'value'."
    then = defn.get("then")
    if not isinstance(then, dict) or not str(then.get("outcome", "")).strip():
        return False, "'then' must be an object with a non-empty 'outcome'."
    return True, ""


def match_conditions(conditions, facts: dict) -> bool:
    """True when every condition in a `when`-style list holds against the facts.
    Reusable by other engines (e.g. automations) so condition semantics stay
    identical everywhere: a missing fact fails its condition, and an empty list
    matches (an unconditional policy)."""
    if not isinstance(conditions, list):
        return False
    facts = facts or {}
    for cond in conditions:
        if not isinstance(cond, dict) or cond.get("op") not in _OPS:
            return False
        actual = facts.get(cond.get("fact"), _MISSING)
        if actual is _MISSING or not _OPS[cond["op"]](actual, cond.get("value")):
            return False
    return True


def evaluate_rule(definition: dict, facts: dict) -> tuple[bool, dict]:
    """Evaluate one definition against facts. Returns (fired, then-block).
    A missing fact makes its condition False — the rule never fires on data the
    caller didn't supply. An empty `when` always fires (an unconditional policy)."""
    ok, _ = validate_definition(definition)
    if not ok:
        return False, {}
    for cond in definition.get("when", []):
        actual = facts.get(cond["fact"], _MISSING)
        if actual is _MISSING:
            return False, {}
        if not _OPS[cond["op"]](actual, cond["value"]):
            return False, {}
    return True, definition.get("then", {})


def evaluate(project, facts: dict) -> dict:
    """Run every ACTIVE, enforceable rule against the facts, in priority order.
    Deterministic; returns which rules fired and their outcomes (no AI)."""
    facts = facts or {}
    fired = []
    for rule in project.business_rules.filter(status="active").order_by("priority", "id"):
        did_fire, then = evaluate_rule(rule.definition or {}, facts)
        if did_fire:
            fired.append({
                "id": rule.id, "name": rule.name, "category": rule.category,
                "outcome": then.get("outcome"),
                "params": {k: v for k, v in then.items() if k != "outcome"},
            })
    return {
        "facts": facts,
        "fired": fired,
        "outcomes": [f["outcome"] for f in fired],
        "fired_count": len(fired),
    }
