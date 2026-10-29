"""Email campaigns (spec §27) — marketing sends over the REAL email engine.

The audience is built from contacts the store genuinely collected (leads from its
forms and the customers on its paid orders), deduplicated by address. Each send
goes through apps.notifications.email.send_email (the one configured backend —
real SMTP in production, console in dev, captured in tests), and every recipient's
status records the ACTUAL outcome: 'sent' only when the backend accepted it,
'failed' with the real error otherwise. No open/click tracking is claimed, because
none is wired up — counts are dispatch results, stated plainly.
"""
from __future__ import annotations

import threading

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.audit.service import record as audit
from apps.notifications.email import send_email
from apps.publishing.models import CampaignRecipient, EmailCampaign


class CampaignError(Exception):
    pass


def build_audience(website, source="all") -> dict[str, str]:
    """email -> name, from the store's real contacts. Deduped; last non-empty name wins."""
    audience: dict[str, str] = {}
    if source in ("all", "leads"):
        for lead in website.leads.exclude(email="").only("email", "name"):
            audience.setdefault(lead.email.lower(), lead.name or audience.get(lead.email.lower(), ""))
            if lead.name:
                audience[lead.email.lower()] = lead.name
    if source in ("all", "customers"):
        for o in (website.orders.filter(status="paid").exclude(customer_email="")
                  .only("customer_email", "customer_name")):
            key = o.customer_email.lower()
            audience.setdefault(key, o.customer_name or "")
            if o.customer_name:
                audience[key] = o.customer_name
    return audience


def create_campaign(website, *, subject, body, audience_source="all", user=None) -> EmailCampaign:
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not subject:
        raise CampaignError("A campaign needs a subject.")
    if not body:
        raise CampaignError("A campaign needs a message body.")
    if audience_source not in dict(EmailCampaign.AUDIENCES):
        raise CampaignError(f"Unknown audience '{audience_source}'.")
    campaign = EmailCampaign.objects.create(
        website=website, subject=subject, body=body,
        audience_source=audience_source, created_by=user)
    audit("campaign.create", actor=user, organization=website.project.organization,
          target=f"campaign:{campaign.id}", summary=subject)
    return campaign


def _personalise(text: str, name: str) -> str:
    first = (name or "").split(" ")[0] if name else "there"
    return text.replace("{{name}}", name or "there").replace("{{first_name}}", first)


def _send_now(campaign: EmailCampaign) -> None:
    sent = failed = 0
    for r in campaign.recipients.filter(status="pending"):
        try:
            delivered = send_email(
                subject=campaign.subject,
                to=r.email,
                text=_personalise(campaign.body, r.name),
            )
            if delivered:
                r.status, r.sent_at = "sent", timezone.now()
                sent += 1
            else:
                r.status, r.error = "failed", "No message accepted by the mail backend."
                failed += 1
        except Exception as exc:                       # real delivery failure
            r.status, r.error = "failed", str(exc)[:300]
            failed += 1
        r.save(update_fields=["status", "error", "sent_at"])

    campaign.sent_count = sent
    campaign.failed_count = failed
    campaign.status = "sent" if sent and not failed else ("failed" if not sent else "sent")
    campaign.sent_at = timezone.now()
    campaign.save(update_fields=["sent_count", "failed_count", "status", "sent_at"])


def send_campaign(campaign: EmailCampaign, *, user=None) -> EmailCampaign:
    """Materialise the audience into real recipient rows and dispatch. Large sends run
    off-request; under tests they run inline so results are deterministic."""
    if campaign.status not in ("draft", "failed"):
        raise CampaignError("This campaign has already been sent.")
    audience = build_audience(campaign.website, campaign.audience_source)
    if not audience:
        raise CampaignError("No contacts to send to yet — collect leads or make a sale first.")

    # Replace any prior recipient rows (e.g. a retried failed send).
    campaign.recipients.all().delete()
    CampaignRecipient.objects.bulk_create([
        CampaignRecipient(campaign=campaign, email=email, name=name)
        for email, name in audience.items()
    ])
    campaign.total = len(audience)
    campaign.status = "sending"
    campaign.save(update_fields=["total", "status"])
    audit("campaign.send", actor=user, organization=campaign.website.project.organization,
          target=f"campaign:{campaign.id}", summary=f"{campaign.total} recipient(s)")

    if getattr(settings, "RUNNING_TESTS", False):
        _send_now(campaign)
    else:
        def _bg():
            try:
                _send_now(campaign)
            finally:
                connection.close()
        threading.Thread(target=_bg, daemon=True).start()
    campaign.refresh_from_db()
    return campaign
