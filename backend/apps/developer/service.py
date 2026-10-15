"""Webhook delivery — real, signed, best-effort, and fully logged.

dispatch(organization, event, payload) delivers an event to every active webhook
in that org subscribed to it, over HTTPS, signed with the webhook's secret (HMAC
SHA-256 in the `X-Boldron-Signature` header). Every attempt is recorded as a
WebhookDelivery; a failure is logged, never hidden, and never raised into the
caller (a build must not break because a customer endpoint is down).

Delivery is synchronous and short-timeout (no queue/broker in this phase). Under
tests no network call is made unless the HTTP sender is patched.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request

from django.conf import settings

from apps.developer.events import is_known
from apps.developer.models import Webhook, WebhookDelivery

_TIMEOUT = 6  # seconds — a customer endpoint must never hang a build


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(url: str, body: bytes, headers: dict) -> int:
    """Send the POST and return the HTTP status. Isolated so tests can patch it."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 (https URLs)
        return resp.status


def deliver(webhook: Webhook, event: str, payload: dict) -> WebhookDelivery:
    """Deliver one event to one webhook, recording the outcome."""
    body = json.dumps({"event": event, "data": payload}, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Boldron-Event": event,
        "X-Boldron-Signature": sign(webhook.secret, body),
        "User-Agent": "Boldron-Webhooks/1",
    }
    delivery = WebhookDelivery(webhook=webhook, event=event)
    try:
        status = _post(webhook.url, body, headers)
        delivery.status_code = status
        delivery.success = 200 <= status < 300
        if not delivery.success:
            delivery.error = f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        delivery.status_code = exc.code
        delivery.error = f"HTTP {exc.code}"[:300]
    except Exception as exc:  # network error, timeout, bad URL — log, never raise
        delivery.error = str(exc)[:300]
    delivery.save()
    return delivery


def dispatch(organization, event: str, payload: dict) -> list[WebhookDelivery]:
    """Fan an event out to the org's subscribed webhooks. Returns the deliveries
    (empty when there are no subscribers). Never raises."""
    if not is_known(event):
        return []
    # Belt-and-braces: don't attempt real network in the test suite.
    if getattr(settings, "RUNNING_TESTS", False) and not getattr(
        settings, "WEBHOOKS_ALLOW_IN_TESTS", False
    ):
        return []
    out = []
    for webhook in Webhook.objects.filter(organization=organization, active=True):
        if webhook.subscribes_to(event):
            try:
                out.append(deliver(webhook, event, payload))
            except Exception:
                pass  # a single bad endpoint never stops the fan-out
    return out
