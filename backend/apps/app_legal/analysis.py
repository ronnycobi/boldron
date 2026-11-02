"""Application legal analysis (spec §62, §65-68).

For a customer's generated app, this inspects what the app ACTUALLY does — its
capabilities and its brief — and:

  - flags the sensitive data categories it likely processes, with recommended
    controls (§62);
  - checks that product features are matched by the right legal documents, and
    reports mismatches / gaps (§65);
  - runs a pre-deploy legal checklist (§66);
  - maps a described change to the legal documents that need review (§67-68).

Everything is a heuristic over real project configuration. It NEVER claims the app
is "legally compliant" — findings are "review required" / "potential issue", and
recommendations are advisory, to be confirmed by qualified legal counsel.
"""
from __future__ import annotations

import re

# Sensitive data categories, inferred from capabilities and/or brief keywords.
# (category, {caps}, [keywords], [recommended controls])
_DATA_SIGNALS = [
    ("personal information", {"crm", "users", "auth", "forms", "ecommerce"},
     ["customer", "contact", "profile", "member", "account", "email", "address"],
     ["a privacy notice", "consent where required", "access controls", "retention limits"]),
    ("financial data", {"payments", "stripe", "payfast", "subscriptions", "invoicing", "ecommerce"},
     ["payment", "card", "bank", "invoice", "billing", "checkout"],
     ["a payment-processing disclosure", "PCI-aware handling (never store raw card data)"]),
    ("health information", set(),
     ["health", "medical", "patient", "clinic", "diagnosis", "therapy", "prescription"],
     ["heightened access controls", "explicit consent", "a clear lawful basis"]),
    ("location data", set(),
     ["location", "gps", "geolocation", "tracking", "map", "nearby", "delivery"],
     ["a location-permission prompt", "consent", "the ability to turn it off"]),
    ("biometric data", set(),
     ["biometric", "fingerprint", "face recognition", "facial", "retina", "voiceprint"],
     ["explicit consent", "strong protection", "a clear retention/deletion policy"]),
    ("children's data", set(),
     ["child", "children", "kid", "minor", "student", "school", "under 13", "under 18"],
     ["age assurance", "parental consent where required", "data-minimisation"]),
    ("authentication data", {"auth"},
     ["login", "password", "sign in", "sign up"],
     ["secure password storage", "session protection"]),
]


def _has_cap(project, caps) -> bool:
    return bool(caps & set(project.capabilities or []))


def _brief(project) -> str:
    return f"{project.name} {project.description}".lower()


def scan_data_types(project) -> list[dict]:
    """The sensitive data categories the app likely processes, with recommended
    controls. Advisory — never a compliance determination."""
    text = _brief(project)
    found = []
    for category, caps, words, controls in _DATA_SIGNALS:
        by_cap = _has_cap(project, caps)
        by_word = any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)
        if by_cap or by_word:
            found.append({
                "category": category,
                "signal": "capability" if by_cap else "description",
                "recommended_controls": controls,
            })
    return found


# Which legal documents a feature implies, for consistency + change review.
_FEATURE_DOCS = [
    (lambda p: _has_cap(p, {"analytics", "seo"}), ["cookie_policy", "privacy_policy"],
     "analytics / tracking"),
    (lambda p: _has_cap(p, {"payments", "stripe", "payfast", "subscriptions", "invoicing", "ecommerce"}),
     ["privacy_policy", "refund_policy"], "payments / commerce"),
    (lambda p: _has_cap(p, {"ai"}), ["ai_terms", "privacy_policy"], "AI features"),
    (lambda p: _has_cap(p, {"crm", "users", "auth", "forms"}), ["privacy_policy", "terms_of_service"],
     "user accounts / personal data"),
    (lambda p: bool((p.mobile_plan or {}).get("platforms")),
     ["mobile_terms", "privacy_policy"], "a mobile app"),
    (lambda p: _has_cap(p, {"campaigns"}), ["privacy_policy"], "marketing email"),
]


def _generated_types(project) -> set:
    from apps.app_legal.models import GeneratedLegalDoc
    return set(project.generated_legal_docs.values_list("doc_type", flat=True))


def consistency_findings(project) -> list[dict]:
    """Mismatches between what the app does and the legal documents it has (§65)."""
    have = _generated_types(project)
    findings = []
    for applies, needed_docs, feature in _FEATURE_DOCS:
        if not applies(project):
            continue
        missing = [d for d in needed_docs if d not in have]
        if missing:
            findings.append({
                "level": "review_required", "feature": feature,
                "message": f"Your app uses {feature} but has no "
                           + ", ".join(m.replace('_', ' ') for m in missing) + " yet.",
                "missing": missing,
            })
    return findings


_CHECK_ITEMS = [
    ("terms_of_service", "Terms of Use", True),
    ("privacy_policy", "Privacy Policy", True),
    ("cookie_policy", "Cookie Policy", False),
    ("refund_policy", "Refund Policy", False),
]


def compliance_check(project) -> dict:
    """A pre-deploy legal checklist (§66). Reports PASS / WARNING / REVIEW REQUIRED —
    never 'legally compliant'."""
    have = _generated_types(project)
    needs_commerce = _has_cap(project, {"payments", "ecommerce", "subscriptions"})
    items = []

    def add(label, ok, *, required):
        if ok:
            items.append({"item": label, "status": "pass"})
        else:
            items.append({"item": label,
                          "status": "review_required" if required else "warning"})

    add("Terms of Use available", "terms_of_service" in have, required=True)
    add("Privacy Policy available", "privacy_policy" in have, required=True)
    add("Cookie Policy (if using analytics)",
        "cookie_policy" in have or not _has_cap(project, {"analytics", "seo"}),
        required=False)
    add("Refund Policy (if selling)",
        "refund_policy" in have or not needs_commerce, required=needs_commerce)
    add("Payment processing disclosed",
        "privacy_policy" in have or not needs_commerce, required=needs_commerce)

    blockers = [i for i in items if i["status"] == "review_required"]
    warnings = [i for i in items if i["status"] == "warning"]
    return {
        "items": items,
        # Honest overall signal — never "compliant".
        "verdict": ("review_required" if blockers else
                    "warning" if warnings else "no_issues_detected"),
        "note": ("Potential compliance issues were detected — review with qualified "
                 "legal counsel before going live." if blockers or warnings else
                 "No obvious gaps detected. This is not a determination of legal "
                 "compliance — have your documents reviewed by qualified counsel."),
    }


# Change keyword -> doc types that should be reviewed (§67-68).
_CHANGE_TRIGGERS = [
    (r"\banalytic|tracking|cookie\b", ["cookie_policy", "privacy_policy"]),
    (r"\bai\b|chatbot|model|recommend", ["ai_terms", "privacy_policy", "subprocessor_policy"]),
    (r"\bpay|payment|card|checkout|billing|subscription\b", ["privacy_policy", "billing_terms", "refund_policy"]),
    (r"\blocation|gps|geoloc", ["privacy_policy"]),
    (r"\bmarketplace|sell|seller\b", ["marketplace_terms", "ip_policy", "terms_of_service"]),
    (r"\bmobile|ios|android|app store\b", ["mobile_terms", "privacy_policy"]),
    (r"\bexport|delete my data|data request\b", ["privacy_policy"]),
    (r"\bemail|marketing|newsletter\b", ["privacy_policy"]),
]


def review_triggers(change_text: str) -> list[str]:
    """The legal document types a described change should trigger a review of."""
    text = (change_text or "").lower()
    triggered = []
    for pattern, docs in _CHANGE_TRIGGERS:
        if re.search(pattern, text):
            for d in docs:
                if d not in triggered:
                    triggered.append(d)
    return triggered
