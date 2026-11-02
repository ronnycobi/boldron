"""Legal engine service (spec §2-4, §46, §52).

Document lifecycle (draft → review → approve → publish → supersede/archive),
version immutability, the "current published version" lookup with jurisdiction
fallback, durable versioned acceptance, and pending-acceptance detection when a
mandatory document changes. Every state change is audited.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.audit.service import record as audit
from apps.core.slugs import unique_slug
from apps.legal.models import (
    ConsentType,
    DocumentStatus,
    LegalAcceptance,
    LegalDocument,
    content_hash,
)
from apps.legal import registry


class LegalError(Exception):
    pass


# --- authoring lifecycle -----------------------------------------------------

def create_draft(*, document_type, title, version, content="", jurisdiction="global",
                 language="en", requires_acceptance=False, acceptance_scope="user",
                 change_summary="", effective_at=None, user=None) -> LegalDocument:
    if not registry.is_valid_type(document_type):
        raise LegalError(f"Unknown document type '{document_type}'.")
    if not registry.is_valid_jurisdiction(jurisdiction):
        raise LegalError(f"Unknown jurisdiction '{jurisdiction}'.")
    version = (version or "").strip()
    if not version:
        raise LegalError("A document needs a version (e.g. '1.0').")
    if LegalDocument.objects.filter(document_type=document_type, jurisdiction=jurisdiction,
                                    language=language, version=version).exists():
        raise LegalError(f"{document_type} {version} already exists for {jurisdiction}/{language}.")
    slug = unique_slug(LegalDocument, f"{document_type}-{jurisdiction}-{version}",
                       field="slug")
    doc = LegalDocument.objects.create(
        document_type=document_type, title=(title or registry.type_label(document_type))[:200],
        slug=slug, jurisdiction=jurisdiction, language=language, version=version,
        content=content, requires_acceptance=bool(requires_acceptance),
        acceptance_scope=acceptance_scope if acceptance_scope in ("user", "organization") else "user",
        change_summary=change_summary, effective_at=effective_at, created_by=user)
    audit("legal.document.create", actor=user, target=f"legal:{doc.id}",
          summary=f"{document_type} {version} draft")
    return doc


def update_draft(doc: LegalDocument, *, user=None, **fields) -> LegalDocument:
    if doc.is_frozen:
        raise LegalError("A published version is immutable; create a new version.")
    for f in ("title", "content", "change_summary", "acceptance_scope"):
        if f in fields and fields[f] is not None:
            setattr(doc, f, fields[f])
    if "requires_acceptance" in fields:
        doc.requires_acceptance = bool(fields["requires_acceptance"])
    if "effective_at" in fields:
        doc.effective_at = fields["effective_at"]
    doc.save()
    audit("legal.document.edit", actor=user, target=f"legal:{doc.id}", summary=doc.slug)
    return doc


def submit_for_review(doc: LegalDocument, *, user=None) -> LegalDocument:
    if doc.status != DocumentStatus.DRAFT:
        raise LegalError("Only a draft can be submitted for review.")
    doc.status = DocumentStatus.UNDER_REVIEW
    doc.save(update_fields=["status", "updated_at"])
    audit("legal.document.review", actor=user, target=f"legal:{doc.id}", summary=doc.slug)
    return doc


def approve(doc: LegalDocument, *, user=None) -> LegalDocument:
    if doc.status not in (DocumentStatus.UNDER_REVIEW, DocumentStatus.DRAFT):
        raise LegalError("Only a draft or in-review document can be approved.")
    doc.status = DocumentStatus.APPROVED
    doc.reviewed_by = user
    doc.save(update_fields=["status", "reviewed_by", "updated_at"])
    audit("legal.document.approve", actor=user, target=f"legal:{doc.id}", summary=doc.slug)
    return doc


@transaction.atomic
def publish(doc: LegalDocument, *, user=None) -> LegalDocument:
    """Freeze and publish a document. Supersedes the prior published version of the
    same type/jurisdiction/language. Content + hash are immutable afterwards."""
    if doc.status not in (DocumentStatus.APPROVED, DocumentStatus.SCHEDULED):
        raise LegalError("A document must be approved before it can be published.")
    if not doc.content.strip():
        raise LegalError("Refusing to publish an empty legal document.")
    prior = LegalDocument.objects.filter(
        document_type=doc.document_type, jurisdiction=doc.jurisdiction,
        language=doc.language, status=DocumentStatus.PUBLISHED).exclude(pk=doc.pk)
    for p in prior:
        p.status = DocumentStatus.SUPERSEDED
        p.save(update_fields=["status", "updated_at"])
        doc.supersedes = doc.supersedes or p
    doc.content_sha256 = content_hash(doc.content)
    doc.status = DocumentStatus.PUBLISHED
    doc.published_at = timezone.now()
    if not doc.effective_at:
        doc.effective_at = doc.published_at
    doc.save()
    audit("legal.document.publish", actor=user, target=f"legal:{doc.id}",
          summary=f"{doc.document_type} {doc.version} published")
    return doc


def archive(doc: LegalDocument, *, user=None) -> LegalDocument:
    doc.status = DocumentStatus.ARCHIVED
    doc.save(update_fields=["status", "updated_at"])
    audit("legal.document.archive", actor=user, target=f"legal:{doc.id}", summary=doc.slug)
    return doc


# --- lookups -----------------------------------------------------------------

def current(document_type, *, jurisdiction="global", language="en") -> LegalDocument | None:
    """The in-force published version for a type, with GLOBAL fallback when there's
    no jurisdiction-specific one."""
    base = LegalDocument.objects.filter(
        document_type=document_type, status=DocumentStatus.PUBLISHED, language=language)
    doc = base.filter(jurisdiction=jurisdiction).order_by("-published_at").first()
    if doc is None and jurisdiction != "global":
        doc = base.filter(jurisdiction="global").order_by("-published_at").first()
    return doc


def published_documents(*, jurisdiction="global", language="en") -> list[LegalDocument]:
    """The current published document per type (jurisdiction-aware)."""
    types = (LegalDocument.objects.filter(status=DocumentStatus.PUBLISHED)
             .values_list("document_type", flat=True).distinct())
    out = []
    for t in types:
        doc = current(t, jurisdiction=jurisdiction, language=language)
        if doc:
            out.append(doc)
    out.sort(key=lambda d: d.document_type)
    return out


def versions(document_type, *, jurisdiction="global", language="en"):
    """Every version of a document type (newest first) — the auditable history."""
    return LegalDocument.objects.filter(
        document_type=document_type, jurisdiction=jurisdiction, language=language
    ).exclude(status=DocumentStatus.DRAFT).order_by("-version", "-id")


# --- acceptance (durable, versioned) -----------------------------------------

def record_acceptance(user, document: LegalDocument, *, organization=None,
                      consent_type=ConsentType.MANDATORY, method="clickwrap",
                      ip_address=None, user_agent="", country="", metadata=None) -> LegalAcceptance:
    """Record that a user accepted a SPECIFIC published version. Idempotent per
    (user, version). Only published documents can be accepted."""
    if not document.is_published:
        raise LegalError("Only a published document can be accepted.")
    acc, _ = LegalAcceptance.objects.get_or_create(
        user=user, document=document,
        defaults={
            "organization": organization,
            "document_type": document.document_type,
            "version": document.version,
            "content_sha256": document.content_sha256,
            "consent_type": consent_type,
            "mandatory": consent_type == ConsentType.MANDATORY,
            "method": method[:32],
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:400],
            "country": (country or "")[:40],
            "metadata": metadata or {},
        })
    audit("legal.acceptance", actor=user, organization=organization,
          target=f"legal:{document.id}",
          summary=f"{document.document_type} {document.version}")
    return acc


def has_accepted(user, document: LegalDocument) -> bool:
    return LegalAcceptance.objects.filter(user=user, document=document).exists()


def pending_acceptances(user, *, jurisdiction="global", language="en") -> list[LegalDocument]:
    """The mandatory, currently-published documents this user has not yet accepted
    at their current version — what to prompt for at next login (spec §46)."""
    pending = []
    for doc in published_documents(jurisdiction=jurisdiction, language=language):
        if doc.requires_acceptance and not has_accepted(user, doc):
            pending.append(doc)
    return pending


def acceptance_history(user):
    return LegalAcceptance.objects.filter(user=user).select_related("document")


# --- jurisdiction rules engine (spec §5) -------------------------------------

def set_jurisdiction_config(jurisdiction, *, user=None, **fields):
    """Configure a jurisdiction's requirements (staff/legal counsel only, enforced
    at the view layer). Never infers law — only what is explicitly set applies."""
    from apps.legal.models import JurisdictionConfig
    from apps.legal import registry
    if not registry.is_valid_jurisdiction(jurisdiction):
        raise LegalError(f"Unknown jurisdiction '{jurisdiction}'.")
    allowed = {"consent_required", "cookie_consent_required", "min_age",
               "additional_notices", "mandatory_disclosures", "privacy_rights",
               "data_transfer_notes", "cancellation_rule", "refund_rule",
               "tax_notes", "enabled"}
    defaults = {k: v for k, v in fields.items() if k in allowed}
    defaults["updated_by"] = user
    config, _ = JurisdictionConfig.objects.update_or_create(
        jurisdiction=jurisdiction, defaults=defaults)
    audit("legal.jurisdiction", actor=user, target=f"jurisdiction:{jurisdiction}",
          summary=jurisdiction)
    return config


def jurisdiction_config(jurisdiction):
    from apps.legal.models import JurisdictionConfig
    return JurisdictionConfig.objects.filter(jurisdiction=jurisdiction, enabled=True).first()


def jurisdiction_notices(jurisdiction) -> dict:
    """The customer-facing notices configured for a jurisdiction. Returns
    `configured: False` honestly when counsel hasn't set anything — never a
    fabricated legal conclusion."""
    config = jurisdiction_config(jurisdiction)
    if config is None:
        return {"jurisdiction": jurisdiction, "configured": False}
    return {
        "jurisdiction": jurisdiction, "configured": True,
        "consent_required": config.consent_required,
        "cookie_consent_required": config.cookie_consent_required,
        "min_age": config.min_age,
        "additional_notices": config.additional_notices,
        "mandatory_disclosures": config.mandatory_disclosures,
        "privacy_rights": config.privacy_rights or [],
        "cancellation_rule": config.cancellation_rule,
        "refund_rule": config.refund_rule,
    }


# --- law-enforcement requests (spec §71) -------------------------------------

def log_law_request(*, authority, jurisdiction="", request_type="", data_requested="",
                    legal_basis="", affected_organization=None, user=None):
    """Record a government / legal data request. Customer data is NEVER disclosed
    automatically — the request is created pending human/legal review."""
    from apps.legal.models import LawEnforcementRequest
    authority = (authority or "").strip()
    if not authority:
        raise LegalError("A law-enforcement request needs an authority.")
    req = LawEnforcementRequest.objects.create(
        authority=authority[:200], jurisdiction=(jurisdiction or "")[:40],
        request_type=(request_type or "")[:80], data_requested=data_requested,
        legal_basis=legal_basis, affected_organization=affected_organization)
    audit("legal.law_request", actor=user,
          organization=affected_organization, target=f"law_request:{req.id}",
          summary=f"{authority}")
    return req


def review_law_request(req, decision, *, disclosed=False, note="", user=None):
    """Record a reviewed decision on a law-enforcement request. Disclosure is an
    explicit action — it is never the default."""
    from django.utils import timezone as _tz
    from apps.legal.models import LawEnforcementRequest
    if decision not in LawEnforcementRequest.Decision.values:
        raise LegalError(f"Unknown decision '{decision}'.")
    req.decision = decision
    req.disclosed = bool(disclosed)
    req.disclosure_note = (note or "")[:4000]
    req.reviewed_by = user
    req.decided_at = _tz.now()
    req.save()
    audit("legal.law_review", actor=user, organization=req.affected_organization,
          target=f"law_request:{req.id}",
          summary=f"{decision}{' · disclosed' if disclosed else ''}")
    return req
