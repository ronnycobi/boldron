"""Change impact analysis (spec §6, §8, §19).

Turns a change's impact plan (apps.changes.planner → {affected_areas, risk, …}) into
a CUSTOMER-FACING impact view by cross-referencing the project's real surfaces
(web, the mobile apps, commerce, payments, database, API) from Project Intelligence,
and derives the tests the change requires.

It composes existing data — the plan and the project's capabilities/mobile plan — and
invents nothing: the "surfaces touched" come from what the plan actually affects
intersected with what the project actually has, and the required tests are derived
deterministically from those surfaces (not a fabricated number). This is what powers
the §19 "proposed change" preview and the §6 "before modifying, determine what's
affected" gate.
"""
from __future__ import annotations

# Human labels for the planner's affected-area keys (spec §6).
_AREA_LABELS = {
    "database": "Database",
    "backend": "Application logic",
    "api": "API",
    "frontend": "Web interface",
    "testing": "Tests",
    "infrastructure": "Deployment",
}

_RISK_LABEL = {"low": "Low", "medium": "Medium", "high": "High"}


def _has_capability(project, *ids) -> bool:
    caps = set(project.capabilities or [])
    return any(i in caps for i in ids)


def analyze_impact(change) -> dict:
    """A customer-safe impact view for a change: surfaces touched + required tests."""
    project = change.project
    plan = change.plan or {}
    areas = plan.get("affected_areas", {}) or {}
    area_keys = set(areas.keys())
    text = f"{change.description} {plan.get('summary', '')}".lower()

    # --- surfaces touched -----------------------------------------------------
    surfaces = []

    def touch(name, detail):
        surfaces.append({"name": name, "detail": detail})

    if area_keys & {"frontend", "backend", "api"}:
        touch("Web app", "Screens and/or server logic change.")
    if "database" in area_keys:
        touch("Database", "Your data model changes — handled as a reviewed migration.")
    if "api" in area_keys:
        touch("API", "API endpoints are added or modified.")

    # Mobile apps: if the project has a mobile plan, any api/backend/frontend change
    # flows to the mobile clients too (they share the backend).
    mobile_platforms = (project.mobile_plan or {}).get("platforms", [])
    if mobile_platforms and (area_keys & {"api", "backend", "frontend"}):
        _names = {"ios": "iOS", "android": "Android", "huawei": "Huawei AppGallery"}
        touch("Mobile apps",
              "Also affects " + ", ".join(_names.get(p, p) for p in mobile_platforms)
              + " (shared backend).")

    # Commerce / payments: only when the project actually has them and the change
    # plausibly touches them.
    commerce_words = any(w in text for w in
                         ("checkout", "cart", "order", "product", "store", "commerce"))
    pay_words = any(w in text for w in
                    ("pay", "payment", "checkout", "subscription", "refund", "invoice"))
    if _has_capability(project, "ecommerce") and (commerce_words or area_keys & {"backend", "database"}):
        touch("Commerce", "Store / order functionality is involved.")
    if _has_capability(project, "payments", "subscriptions") and pay_words:
        touch("Payments", "Payment or billing behaviour is involved — extra care and tests.")

    # --- required tests (spec §8, derived — never a fabricated count) ----------
    tests: list[str] = []

    def need(label):
        if label not in tests:
            tests.append(label)

    if "database" in area_keys:
        need("Database migration test")
    if "api" in area_keys:
        need("API contract test")
        need("Input validation test")
    # Any API/backend change to a tenant-owned app must prove isolation holds.
    if (area_keys & {"api", "backend"}) and _has_capability(
            project, "ecommerce", "payments", "auth", "invoicing", "subscriptions"):
        need("Tenant isolation test")
    if _has_capability(project, "auth") and any(
            w in text for w in ("login", "auth", "password", "session", "account", "sign")):
        need("Authentication test")
    if _has_capability(project, "payments", "subscriptions") and pay_words:
        need("Payment flow test")
    if mobile_platforms and (area_keys & {"api", "backend"}):
        need("Mobile API test")
    if "frontend" in area_keys:
        need("UI test")
    # Carry any explicit test items the planner already called out.
    for item in areas.get("testing", []) or []:
        need(item if item.lower().endswith("test") else f"{item} test")
    # Every change gets a regression pass before it ships.
    need("Regression test")

    risk = change.risk
    return {
        "summary": plan.get("summary", ""),
        "surfaces": surfaces,
        "affected_areas": {
            _AREA_LABELS.get(k, k.title()): v for k, v in areas.items()
        },
        "required_tests": tests,
        "tests_required": len(tests),
        "risk": risk,
        "risk_label": _RISK_LABEL.get(risk, risk.title()),
        "requires_approval": change.requires_approval,
        "approved": change.approved,
    }
