"""SMS delivery (spec §27) — real provider adapters, honestly gated.

There is NO offline path for SMS: a text message can only be delivered by a real
SMS gateway, which needs the customer's account credentials. So this module does
the real thing when a provider is configured from the environment, and REFUSES
(raising SmsError) when it is not — it never pretends a message was sent.

Credentials come from the environment only (never the database, never the
frontend). `provider_status()` reports, honestly, which providers are connected;
in an environment with no SMS credentials every provider reads "not configured",
and that is the truth shown to the customer rather than a fake "SMS enabled".
"""
from __future__ import annotations

import os

from django.utils import timezone


class SmsError(Exception):
    pass


class SmsProvider:
    key = "base"
    name = "SMS provider"

    def is_available(self) -> bool:
        return False

    def status_detail(self) -> str:
        return "Not configured."

    def send(self, *, to: str, text: str) -> dict:
        raise SmsError(f"{self.name} is not configured on this host.")


class TwilioProvider(SmsProvider):
    key = "twilio"
    name = "Twilio"

    def _creds(self):
        return (os.environ.get("TWILIO_ACCOUNT_SID", ""),
                os.environ.get("TWILIO_AUTH_TOKEN", ""),
                os.environ.get("TWILIO_FROM", ""))

    def is_available(self) -> bool:
        return all(self._creds())

    def status_detail(self) -> str:
        return ("Connected." if self.is_available()
                else "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM to enable.")

    def send(self, *, to: str, text: str) -> dict:
        sid, token, sender = self._creds()
        if not all((sid, token, sender)):
            raise SmsError("Twilio is not configured on this host.")
        import requests  # real HTTP call — only reached when credentials exist
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data={"To": to, "From": sender, "Body": text},
            auth=(sid, token), timeout=15,
        )
        if resp.status_code >= 300:
            raise SmsError(f"Twilio rejected the message ({resp.status_code}): {resp.text[:200]}")
        return {"provider": self.key, "ref": resp.json().get("sid", "")}


class AfricasTalkingProvider(SmsProvider):
    key = "africastalking"
    name = "Africa's Talking"

    def _creds(self):
        return (os.environ.get("AT_USERNAME", ""),
                os.environ.get("AT_API_KEY", ""),
                os.environ.get("AT_FROM", ""))

    def is_available(self) -> bool:
        user, key, _ = self._creds()
        return bool(user and key)

    def status_detail(self) -> str:
        return ("Connected." if self.is_available()
                else "Set AT_USERNAME and AT_API_KEY (and optionally AT_FROM) to enable.")

    def send(self, *, to: str, text: str) -> dict:
        user, key, sender = self._creds()
        if not (user and key):
            raise SmsError("Africa's Talking is not configured on this host.")
        import requests
        data = {"username": user, "to": to, "message": text}
        if sender:
            data["from"] = sender
        resp = requests.post(
            "https://api.africastalking.com/version1/messaging",
            data=data, headers={"apiKey": key, "Accept": "application/json"}, timeout=15,
        )
        if resp.status_code >= 300:
            raise SmsError(f"Africa's Talking rejected the message ({resp.status_code}).")
        return {"provider": self.key, "ref": ""}


_PROVIDERS = [TwilioProvider(), AfricasTalkingProvider()]


def all_providers() -> list[SmsProvider]:
    return list(_PROVIDERS)


def active_provider() -> SmsProvider | None:
    for p in _PROVIDERS:
        if p.is_available():
            return p
    return None


def provider_status() -> list[dict]:
    return [{"key": p.key, "name": p.name, "available": p.is_available(),
             "detail": p.status_detail()} for p in _PROVIDERS]


def is_configured() -> bool:
    return active_provider() is not None


def send_sms(*, to: str, text: str, organization=None, provider=None) -> "object":
    """Send one SMS through a configured provider, logging the real outcome. Raises
    SmsError when no provider is configured — never silently "succeeds"."""
    from apps.notifications.models import SmsMessage
    to = (to or "").strip()
    text = (text or "").strip()
    if not to:
        raise SmsError("A recipient number is required.")
    if not text:
        raise SmsError("Message text is required.")

    prov = provider or active_provider()
    log = SmsMessage.objects.create(
        organization=organization, to=to, body=text,
        provider=(prov.key if prov else ""), status="queued")
    if prov is None:
        log.status = "failed"
        log.error = ("No SMS provider is connected. Set a provider's credentials in the "
                     "environment to enable SMS.")
        log.save(update_fields=["status", "error"])
        raise SmsError(log.error)
    try:
        result = prov.send(to=to, text=text)
        log.status = "sent"
        log.provider_ref = result.get("ref", "")[:255]
        log.sent_at = timezone.now()
        log.save(update_fields=["status", "provider_ref", "sent_at"])
    except SmsError as exc:
        log.status = "failed"
        log.error = str(exc)[:300]
        log.save(update_fields=["status", "error"])
        raise
    return log
