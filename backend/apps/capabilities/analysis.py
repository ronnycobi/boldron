"""AI requirements analysis — turn a plain-language brief into the set of
platform capabilities an app needs, grouped and with an HONEST status.

This is the spine the product principle rests on: the customer describes an
outcome, and the platform works out which reusable capabilities compose it
(auth, database, email, dashboards, …) rather than making them configure each
one. Availability is never inflated — a capability the platform doesn't build
yet is shown as "coming", never as if it were already in the app.

Nothing here generates code; it produces the plan the builder and the project's
capability map (apps.projects.Project.capabilities) are based on.
"""
from __future__ import annotations

from apps.capabilities.infer import infer_capabilities
from apps.capabilities.registry import _GROUP_ORDER, get

# Customer-facing group labels (the internal group names are already friendly,
# but keep the mapping explicit so the UI copy lives in one place).
_GROUP_LABELS = {
    "Application": "Application",
    "Business": "Business",
    "Growth": "Growth",
    "Infrastructure": "Infrastructure & hosting",
    "Protect": "Security & trust",
    "Integrations": "Integrations",
}


def _cap_dict(cap) -> dict:
    return {
        "id": cap.id,
        "name": cap.name,
        "group": cap.group,
        "status": cap.status,
        "available": cap.is_available,
        "description": cap.description,
    }


def _grouped(caps: list) -> list[dict]:
    """Group a capability list into the canonical group order, available first."""
    by_group: dict[str, list] = {}
    for c in caps:
        by_group.setdefault(c.group, []).append(c)
    out = []
    for g in _GROUP_ORDER:
        items = by_group.get(g)
        if not items:
            continue
        items = sorted(items, key=lambda c: (not c.is_available, c.name))
        out.append({
            "group": g,
            "label": _GROUP_LABELS.get(g, g),
            "items": [_cap_dict(c) for c in items],
        })
    return out


def capability_ids(brief: str) -> list[str]:
    """The ordered list of capability ids a brief implies (for persistence)."""
    return [c.id for c in infer_capabilities(brief)]


def summary(ids: list[str]) -> dict:
    """The grouped analysis for an already-known set of capability ids
    (a project's persisted capability map)."""
    caps = [c for c in (get(i) for i in (ids or [])) if c is not None]
    available = [c for c in caps if c.is_available]
    planned = [c for c in caps if not c.is_available]
    return {
        "groups": _grouped(caps),
        "available_count": len(available),
        "planned_count": len(planned),
        "total": len(caps),
        "available_names": [c.name for c in available],
        "planned_names": [c.name for c in planned],
    }


def analyze(brief: str) -> dict:
    """Full analysis of a brief: which capabilities it needs, grouped, with an
    honest built/coming split. Drives the pre-build preview and the plan."""
    data = summary(capability_ids(brief))
    data["brief"] = (brief or "").strip()
    return data
