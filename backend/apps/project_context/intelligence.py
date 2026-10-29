"""The Project Intelligence Engine (spec §14).

Each project maintains structured, persistent knowledge — not just conversation
history. This module COMPOSES that knowledge from the data the platform already
keeps (project context entries, the capability map, the mobile plan, change history,
version snapshots and membership) into one structured view the AI consults before a
significant modification, and that the web + mobile UIs render.

It builds nothing new of its own — it is a read-only projection over existing
sources (extend/reuse, not duplicate). It is also CUSTOMER-SAFE (spec §30): it never
exposes the internal stack, AI agent/model names, prompts, task ids, infrastructure
or the `source` of a context entry. Internal-only context kinds (stack proposals,
infrastructure, agent decisions, internal review findings) are excluded.
"""
from __future__ import annotations

from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext

# Context kinds that are internal implementation detail and must never surface to a
# customer (spec §30): the chosen stack (Django/Python/…), infra, and the AI's own
# agent decisions / review findings.
_INTERNAL_KINDS = {
    ContextKind.STACK, ContextKind.INFRASTRUCTURE,
    ContextKind.AGENT_DECISION, ContextKind.REVIEW,
}

# (area key, label, context kind) — the customer-facing knowledge areas (spec §14).
# UI and Mobile both come from SCREEN entries, split by platform below.
_AREA_KINDS = [
    ("requirements", "Requirements", ContextKind.REQUIREMENT),
    ("business_rules", "Business rules", ContextKind.BUSINESS_RULE),
    ("architecture", "Architecture", ContextKind.ARCHITECTURE),
    ("database", "Database", ContextKind.SCHEMA),
    ("apis", "APIs", ContextKind.API),
    ("dependencies", "Dependencies", ContextKind.DEPENDENCY),
    ("security_rules", "Security rules", ContextKind.SECURITY),
    ("tests", "Tests", ContextKind.TESTING),
    ("known_issues", "Known issues", ContextKind.KNOWN_ISSUE),
    ("technical_decisions", "Technical decisions", ContextKind.TECH_DECISION),
    ("deployment", "Deployment", ContextKind.DEPLOYMENT),
]


def _clip(text: str, n: int = 240) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _items(entries, kind, *, platform=None, exclude_platform=None):
    out = []
    for e in entries:
        if e.kind != kind:
            continue
        plat = (e.data or {}).get("platform")
        if platform is not None and plat != platform:
            continue
        if exclude_platform is not None and plat == exclude_platform:
            continue
        out.append({"title": e.title or e.key, "summary": _clip(e.content)})
    return out


def _capability_split(project):
    from apps.capabilities.analysis import capability_ids, summary
    ids = project.capabilities or capability_ids(project.description or project.name)
    data = summary(ids)
    built, coming = [], []
    for g in data.get("groups", []):
        for item in g["items"]:
            (built if item["available"] else coming).append(item["name"])
    return {"built": built, "coming": coming,
            "built_count": data.get("available_count", len(built)),
            "coming_count": data.get("planned_count", len(coming))}


def _permissions(project):
    roles: dict[str, int] = {}
    members = 0
    for m in project.organization.memberships.all():
        roles[m.role] = roles.get(m.role, 0) + 1
        members += 1
    return {"members": members, "by_role": roles}


def _change_history(project, limit=10):
    rows = []
    for c in project.changes.all()[:limit]:
        plan = c.plan or {}
        rows.append({
            "description": _clip(c.description, 160),
            "status": c.status,
            "summary": _clip(plan.get("summary", ""), 160),
            "affected_areas": plan.get("affected_areas", []),
            "created_at": c.created_at.isoformat(),
        })
    return rows


def _version_history(project, limit=10):
    return [{"label": b.label, "created_at": b.created_at.isoformat()}
            for b in project.backups.all()[:limit]]


def build_intelligence(project) -> dict:
    """The structured, customer-safe project intelligence (spec §14)."""
    entries = [e for e in ProjectContext(project).all() if e.kind not in _INTERNAL_KINDS]

    areas = []
    for key, label, kind in _AREA_KINDS:
        items = _items(entries, kind)
        areas.append({"key": key, "label": label, "count": len(items), "items": items})

    # UI and Mobile both derive from SCREEN entries, split by platform.
    ui_items = _items(entries, ContextKind.SCREEN, exclude_platform="mobile")
    mobile_items = _items(entries, ContextKind.SCREEN, platform="mobile")
    areas.insert(5, {"key": "ui", "label": "UI / screens",
                     "count": len(ui_items), "items": ui_items})

    plan = project.mobile_plan or {}
    _platform_names = {"ios": "iOS", "android": "Android", "huawei": "Huawei AppGallery"}
    mobile = {
        "key": "mobile", "label": "Mobile", "count": len(mobile_items),
        "items": mobile_items,
        "platforms": [_platform_names.get(p, p) for p in plan.get("platforms", [])],
        "capabilities": plan.get("capabilities", []),
    }
    areas.insert(6, mobile)

    return {
        "project": {"id": project.id, "name": project.name},
        "areas": areas,
        "capabilities": _capability_split(project),
        "permissions": _permissions(project),
        "change_history": _change_history(project),
        "version_history": _version_history(project),
    }


def intelligence_digest(project, *, max_chars=3000) -> str:
    """A compact text digest of the intelligence, for the AI to consult before a
    significant change (spec §14). Customer-safe, deterministic."""
    intel = build_intelligence(project)
    lines = [f"PROJECT: {intel['project']['name']}"]
    caps = intel["capabilities"]
    if caps["built"]:
        lines.append("Built capabilities: " + ", ".join(caps["built"]))
    if caps["coming"]:
        lines.append("Planned (not built): " + ", ".join(caps["coming"]))
    for area in intel["areas"]:
        if not area["count"]:
            continue
        lines.append(f"\n{area['label']} ({area['count']}):")
        for it in area["items"][:8]:
            lines.append(f"  - {it['title']}: {it['summary']}")
    if intel["change_history"]:
        lines.append("\nRecent changes:")
        for c in intel["change_history"][:5]:
            lines.append(f"  - [{c['status']}] {c['description']}")
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"
