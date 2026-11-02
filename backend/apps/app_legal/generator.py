"""Generate project-specific legal document DRAFTS (spec §63-64).

Composed deterministically from the project's REAL configuration — it never
invents a service the app doesn't use. Every generated document is prefixed with
the counsel-review disclaimer; nothing here is legal advice or a compliance
guarantee.
"""
from __future__ import annotations

from apps.app_legal.analysis import scan_data_types, _has_cap
from apps.app_legal.models import GeneratedLegalDoc
from apps.audit.service import record as audit
from apps.legal.registry import is_valid_type

DISCLAIMER = (
    "IMPORTANT: This document was generated automatically from your application's "
    "configuration for informational and operational purposes only. It is NOT legal "
    "advice and is NOT a guarantee of compliance. Review it with qualified legal "
    "counsel before publishing or relying on it."
)

# Document types the generator can draft (a subset of the registry).
GENERATABLE = ["privacy_policy", "terms_of_service", "cookie_policy", "refund_policy"]


class GeneratorError(Exception):
    pass


def _privacy_policy(project) -> str:
    app = project.name
    data = scan_data_types(project)
    lines = [f"Privacy Policy for {app}", ""]
    lines.append(f"This policy explains how {app} handles information.")
    if data:
        lines.append("")
        lines.append("Information we process")
        for d in data:
            lines.append(f"- {d['category'].capitalize()} — recommended controls: "
                         + ", ".join(d["recommended_controls"]) + ".")
    else:
        lines.append("")
        lines.append("This application does not appear to process sensitive "
                     "personal information, but confirm this before publishing.")
    if _has_cap(project, {"analytics", "seo"}):
        lines += ["", "Analytics", "We use analytics to understand usage. Where "
                  "required, we obtain consent before non-essential tracking."]
    if _has_cap(project, {"payments", "stripe", "payfast", "ecommerce"}):
        lines += ["", "Payments", "Payments are processed by third-party payment "
                  "providers; we do not store full card details."]
    lines += ["", "Your rights", "You may request access to, correction of, or "
              "deletion of your personal information, subject to applicable law."]
    return "\n".join(lines)


def _terms(project) -> str:
    app = project.name
    return "\n".join([
        f"Terms of Use for {app}", "",
        f"By using {app} you agree to these terms.",
        "You are responsible for the content you provide and for using the service "
        "lawfully. The service is provided as-is; features may change.",
    ])


def _cookie_policy(project) -> str:
    return "\n".join([
        f"Cookie Policy for {project.name}", "",
        "We use necessary cookies to run the service. Where you have enabled "
        "analytics or marketing features, additional cookies are used only with "
        "your consent, which you can change at any time.",
    ])


def _refund_policy(project) -> str:
    return "\n".join([
        f"Refund Policy for {project.name}", "",
        "Refunds are handled in line with your consumer rights and the terms of "
        "each purchase. Contact support to request a refund.",
    ])


_BUILDERS = {
    "privacy_policy": _privacy_policy,
    "terms_of_service": _terms,
    "cookie_policy": _cookie_policy,
    "refund_policy": _refund_policy,
}


def generate(project, doc_type, *, user=None) -> GeneratedLegalDoc:
    if doc_type not in _BUILDERS or not is_valid_type(doc_type):
        raise GeneratorError(f"Cannot generate '{doc_type}'.")
    body = _BUILDERS[doc_type](project)
    content = f"{DISCLAIMER}\n\n{body}"
    doc, _ = GeneratedLegalDoc.objects.update_or_create(
        project=project, doc_type=doc_type,
        defaults={"content": content, "disclaimer": DISCLAIMER,
                  "reviewed": False, "generated_by": user})
    audit("app_legal.generate", actor=user, organization=project.organization,
          target=f"project:{project.id}", summary=doc_type)
    return doc
