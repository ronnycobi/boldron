"""Trust Center service (spec §26, §28, §29).

The subprocessor register, an HONEST security overview composed from real controls
(never a false certification), and private vulnerability-report intake.
"""
from __future__ import annotations

from django.conf import settings

from apps.audit.service import record as audit
from apps.trust.models import Subprocessor, VulnerabilityReport


class TrustError(Exception):
    pass


# --- subprocessor register (§26) ---------------------------------------------

def register_subprocessor(*, name, category="other", service="", data_processed="",
                          purpose="", location="", transfer_mechanism="",
                          security_notes="", status="active", user=None) -> Subprocessor:
    name = (name or "").strip()
    if not name:
        raise TrustError("A subprocessor needs a name.")
    if category not in Subprocessor.Category.values:
        category = "other"
    if status not in Subprocessor.Status.values:
        status = "active"
    sp = Subprocessor.objects.create(
        name=name[:160], category=category, service=service[:200],
        data_processed=data_processed[:300], purpose=purpose[:300],
        location=location[:120], transfer_mechanism=transfer_mechanism[:160],
        security_notes=security_notes, status=status)
    audit("trust.subprocessor", actor=user, target=f"subprocessor:{sp.id}", summary=name)
    return sp


def active_subprocessors():
    return Subprocessor.objects.exclude(status=Subprocessor.Status.REMOVED)


# --- security overview (§28) — honest, composed, no false certifications ------

def security_overview() -> dict:
    """Describe the controls the platform ACTUALLY has, in customer terms. It makes
    no certification claims (SOC 2 / ISO / PCI), because none are asserted here —
    only real, in-code controls are listed."""
    controls = [
        {"area": "Authentication", "detail": "Email + password with JWT sessions; "
         "brute-force throttling; optional MFA where enabled."},
        {"area": "Access control", "detail": "Organization roles enforce least-"
         "privilege; tenant isolation is enforced server-side on every request."},
        {"area": "Secrets", "detail": "Credentials come from the environment only — "
         "never stored in the database or exposed to the frontend."},
        {"area": "Audit", "detail": "Security-relevant actions are recorded in an "
         "audit log."},
        {"area": "Backups", "detail": "Projects can create restore points and roll "
         "back."},
        {"area": "Code safety", "detail": "Generated code runs in an isolated "
         "sandbox; secret + injection scanning runs on changes."},
        {"area": "Dependencies", "detail": "Dependency and license information is "
         "tracked where technically possible."},
    ]
    return {
        "controls": controls,
        # Explicit, honest non-claims (spec §28, §77).
        "certifications": [],
        "disclaimer": ("This describes the controls the service operates today. It "
                       "is not a claim of any formal certification (e.g. SOC 2, ISO "
                       "27001, PCI DSS) unless separately and explicitly stated."),
        "security_contact": (getattr(settings, "LEGAL_SECURITY_EMAIL", "")
                             or getattr(settings, "APP_SUPPORT_EMAIL", "")),
    }


# --- responsible disclosure (§29) — private intake ---------------------------

def submit_vulnerability(*, summary, details="", reporter_email="",
                         severity_estimate="") -> VulnerabilityReport:
    summary = (summary or "").strip()
    if not summary:
        raise TrustError("Please describe the issue.")
    report = VulnerabilityReport.objects.create(
        summary=summary[:300], details=details, reporter_email=reporter_email[:254],
        severity_estimate=(severity_estimate or "")[:10])
    audit("trust.vuln_report", target=f"vuln:{report.id}", summary="report received")
    return report


def set_report_status(report: VulnerabilityReport, status: str, *, resolution="", user=None):
    if status not in VulnerabilityReport.Status.values:
        raise TrustError(f"Unknown status '{status}'.")
    report.status = status
    if resolution:
        report.resolution = resolution
    report.save(update_fields=["status", "resolution", "updated_at"])
    audit("trust.vuln_review", actor=user, target=f"vuln:{report.id}", summary=status)
    return report


def disclosure_info() -> dict:
    return {
        "security_contact": (getattr(settings, "LEGAL_SECURITY_EMAIL", "")
                             or getattr(settings, "APP_SUPPORT_EMAIL", "")),
        "guidance": ("Report suspected vulnerabilities privately to the security "
                     "contact or via this form. Please do not test against other "
                     "customers' data, run denial-of-service, or publicly disclose "
                     "before we have had a chance to remediate."),
    }


# --- security incidents (spec §30) -------------------------------------------

def open_security_incident(*, title, severity="medium", summary="", user=None):
    from apps.trust.models import SecurityIncident
    title = (title or "").strip()
    if not title:
        raise TrustError("A security incident needs a title.")
    if severity not in SecurityIncident.Severity.values:
        severity = "medium"
    inc = SecurityIncident.objects.create(
        title=title[:200], severity=severity, summary=summary)
    audit("security.incident.open", actor=user, target=f"sec_incident:{inc.id}",
          summary=f"[{severity}] {title}")
    return inc


def update_security_incident(inc, *, user=None, **fields):
    from django.utils import timezone
    from apps.trust.models import SecurityIncident
    for f in ("summary", "investigation", "containment", "remediation", "postmortem"):
        if f in fields and fields[f] is not None:
            setattr(inc, f, fields[f])
    if "severity" in fields and fields["severity"] in SecurityIncident.Severity.values:
        inc.severity = fields["severity"]
    if "status" in fields and fields["status"] in SecurityIncident.Status.values:
        inc.status = fields["status"]
        if fields["status"] in ("resolved", "closed") and not inc.resolved_at:
            inc.resolved_at = timezone.now()
    inc.save()
    audit("security.incident.update", actor=user, target=f"sec_incident:{inc.id}",
          summary=inc.status)
    return inc


def assess_notification(inc, *, required, note="", user=None):
    """Record the breach-notification assessment. This does NOT send anything —
    it's the reviewed decision that must precede any notification."""
    inc.notification_assessed = True
    inc.notification_required = bool(required)
    inc.notification_note = note
    inc.save(update_fields=["notification_assessed", "notification_required",
                            "notification_note"])
    audit("security.incident.assess", actor=user, target=f"sec_incident:{inc.id}",
          summary=f"notification {'required' if required else 'not required'}")
    return inc


def mark_notified(inc, *, user=None):
    """Mark that notification has been sent — only allowed AFTER an assessment that
    found it required (never an automatic or premature notification)."""
    if not inc.notification_assessed:
        raise TrustError("Assess whether notification is required before sending.")
    if not inc.notification_required:
        raise TrustError("The assessment found notification was not required.")
    inc.notification_sent = True
    inc.save(update_fields=["notification_sent"])
    audit("security.incident.notified", actor=user, target=f"sec_incident:{inc.id}",
          summary="notification sent")
    return inc


def security_incident_summary() -> dict:
    from apps.trust.models import SecurityIncident
    inc = SecurityIncident.objects.all()
    open_ = inc.exclude(status__in=("resolved", "closed"))
    return {
        "total": inc.count(),
        "open": open_.count(),
        "critical_open": open_.filter(severity="critical").count(),
    }
