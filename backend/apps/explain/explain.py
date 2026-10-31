"""Explain-my-application (spec §29).

A plain-language answer to "what is my app, what does it do, what's it made of,
and what state is it in" — composed READ-ONLY from the knowledge the platform
already holds (capabilities, the application graph, requirements, business rules,
acceptance criteria and the health score).

It builds nothing of its own and, like the other composed views, is CUSTOMER-SAFE
(spec §30): it talks about features, screens and data in the customer's own
terms, and never exposes the stack, AI agents, prompts, infrastructure or any
internal identifier. It also never invents capabilities — only what the project
genuinely has is described, and planned-but-unbuilt features are named as such.
"""
from __future__ import annotations

# Graph node types rendered as customer-facing "parts of your app" counts.
_PART_LABELS = {
    "feature": "features",
    "screen": "web screens",
    "mobile_screen": "mobile screens",
    "api": "data services",
    "entity": "data types",
    "integration": "integrations",
    "mobile_platform": "mobile apps",
    "environment": "environments",
}


def explain_application(project) -> dict:
    """The structured, plain-language explanation of the whole application."""
    from apps.acceptance.service import summary as acceptance_summary
    from apps.business_rules.models import RuleStatus
    from apps.capabilities.analysis import capability_ids, summary as cap_summary
    from apps.health.score import health_score
    from apps.project_context.graph import build_graph
    from apps.project_context.models import ContextKind

    ids = project.capabilities or capability_ids(project.description or project.name)
    caps = cap_summary(ids)
    graph = build_graph(project)

    parts = []
    for node_type, count in graph["stats"]["by_type"].items():
        label = _PART_LABELS.get(node_type)
        if label and count:
            parts.append({"label": label, "count": count})
    parts.sort(key=lambda p: -p["count"])

    reqs = [e.title for e in
            project.context_entries.filter(kind=ContextKind.REQUIREMENT)[:50]]
    rules = [r.name for r in
             project.business_rules.filter(status=RuleStatus.ACTIVE)[:50]]

    plan = project.mobile_plan or {}
    _names = {"ios": "iOS", "android": "Android", "huawei": "Huawei AppGallery"}
    platforms = ["Web"]
    platforms += [_names.get(p, p) for p in plan.get("platforms", [])]

    health = health_score(project)
    acc = acceptance_summary(project)

    return {
        "project": {"id": project.id, "name": project.name},
        "summary": _overview_sentence(project, caps, platforms),
        "description": (project.description or "").strip(),
        "does": caps["available_names"],          # what it can do today
        "coming": caps["planned_names"],           # named honestly as not built
        "parts": parts,
        "platforms": platforms,
        "requirements": reqs,
        "rules": rules,
        "acceptance": {
            "accepted": acc["accepted"], "met": acc["met"], "total": acc["total"]},
        "health": {"score": health["score"], "band": health["band"],
                   "headline": health["headline"]},
    }


def _overview_sentence(project, caps, platforms) -> str:
    built = caps["available_names"]
    name = project.name
    if not built:
        return f"{name} is an application that is still being set up."
    lead = ", ".join(built[:4])
    more = f" and {len(built) - 4} more" if len(built) > 4 else ""
    where = " / ".join(platforms)
    return f"{name} is a {where} application with {lead}{more}."


def explain_part(project, node_id: str) -> dict | None:
    """Explain one part of the app by tracing the application graph (spec §29 +
    §5): what it is, what it depends on, and what depends on it."""
    from apps.project_context.graph import dependency_report
    report = dependency_report(project, node_id)
    if report is None:
        return None
    node = report["node"]
    depends_on = [d["label"] for d in report["depends_on"]]
    dependents = [d["label"] for d in report["dependents"]]

    parts = [f"{node['label']} is part of {project.name}."]
    if depends_on:
        parts.append("It relies on " + _join(depends_on) + ".")
    if dependents:
        parts.append(_join(dependents) +
                     (" depends on it" if len(dependents) == 1 else " depend on it") +
                     ", so a change here affects "
                     f"{len(dependents)} other part"
                     f"{'' if len(dependents) == 1 else 's'}.")
    else:
        parts.append("Nothing else depends on it.")

    return {
        "project": report["project"],
        "node": node,
        "explanation": " ".join(parts),
        "depends_on": report["depends_on"],
        "dependents": report["dependents"],
        "impact_count": report["impact_count"],
    }


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def explain_text(project, *, max_chars=2500) -> str:
    """A compact plain-text narrative of the application, for the AI or an export."""
    data = explain_application(project)
    lines = [data["summary"]]
    if data["description"]:
        lines.append(data["description"])
    if data["does"]:
        lines.append("What it does: " + ", ".join(data["does"]) + ".")
    if data["coming"]:
        lines.append("Planned (not built yet): " + ", ".join(data["coming"]) + ".")
    if data["parts"]:
        lines.append("Made of: " + ", ".join(
            f"{p['count']} {p['label']}" for p in data["parts"]) + ".")
    if data["rules"]:
        lines.append("Business rules in force: " + ", ".join(data["rules"]) + ".")
    h = data["health"]
    if h["score"] is not None:
        lines.append(f"Health: {h['score']}/100 ({h['band']}) — {h['headline']}")
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"
