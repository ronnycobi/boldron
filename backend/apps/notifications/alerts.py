"""Alerting engine (spec §21) — raise an operational alert and deliver it for real.

A single reusable primitive: `raise_alert(project, kind, message, severity)` records a
persistent Alert (the in-app notification) and, when the org hasn't opted out, emails
the org's owners/admins through the real email backend. It reports honestly how many
recipients the email actually reached; push is not attempted because no push provider
is connected, so it is never reported as sent.

Delivery is best-effort: a mail failure or no recipients never breaks the caller, and
the Alert record always stands so nothing is silently lost.
"""
from __future__ import annotations

from apps.audit.service import record as audit


def _recipients(organization) -> list[str]:
    from apps.organizations.models import Membership, Role
    emails = (Membership.objects
              .filter(organization=organization, role__in=(Role.OWNER, Role.ADMIN))
              .select_related("user").values_list("user__email", flat=True))
    return [e for e in emails if e]


def _email_enabled(organization) -> bool:
    from apps.notifications.models import AlertPreference
    pref = AlertPreference.objects.filter(organization=organization).first()
    return pref.email_enabled if pref else True   # default on


def raise_alert(project, *, kind, message, severity="medium"):
    """Record and deliver an operational alert. Returns the Alert."""
    from apps.notifications.models import Alert
    alert = Alert.objects.create(
        project=project, kind=kind, severity=severity, message=(message or "")[:300])

    if _email_enabled(project.organization):
        recipients = _recipients(project.organization)
        if recipients:
            try:
                from apps.notifications.email import send_email
                sent = send_email(
                    subject=f"[{severity.upper()}] {project.name}: {message[:80]}",
                    to=recipients,
                    text=(f"An alert was raised for {project.name}.\n\n"
                          f"Severity: {severity}\nWhat happened: {message}\n\n"
                          f"Review it: /app/projects/{project.id}/operations/\n"))
                if sent:
                    alert.emailed = len(recipients)
                    alert.save(update_fields=["emailed"])
            except Exception:
                pass  # delivery failure never loses the recorded alert

    audit("alert.raised", organization=project.organization,
          target=f"project:{project.id}", summary=f"[{severity}] {kind}: {message[:80]}")
    return alert


def recent(project, limit=25):
    return list(project.alerts.all()[:limit])


def set_email_enabled(organization, enabled: bool) -> None:
    from apps.notifications.models import AlertPreference
    AlertPreference.objects.update_or_create(
        organization=organization, defaults={"email_enabled": bool(enabled)})
