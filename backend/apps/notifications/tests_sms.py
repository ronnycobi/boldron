"""SMS: honest gating. With no gateway configured the engine REFUSES (never fakes a
send); with a provider connected it dispatches and logs the real outcome."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.notifications import sms
from apps.notifications.models import SmsMessage
from apps.organizations.models import Organization, Role

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class _FakeProvider(sms.SmsProvider):
    """A connected provider stand-in for tests — represents credentials being set,
    so we can exercise the real dispatch+log path without hitting a live gateway."""
    key = "fake"
    name = "Fake"

    def __init__(self):
        self.sent = []

    def is_available(self):
        return True

    def send(self, *, to, text):
        self.sent.append((to, text))
        return {"provider": self.key, "ref": "fake-123"}


class SmsEngineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="SmsOrg")

    def test_no_provider_configured_in_this_environment(self):
        # The guardrail for this host: no real SMS credentials are set.
        self.assertFalse(sms.is_configured())
        self.assertTrue(all(not p["available"] for p in sms.provider_status()))

    def test_send_without_provider_refuses_and_logs_failed(self):
        with self.assertRaises(sms.SmsError):
            sms.send_sms(to="+15550001111", text="hi", organization=self.org)
        log = SmsMessage.objects.latest("id")
        self.assertEqual(log.status, "failed")       # never "sent"
        self.assertIn("No SMS provider", log.error)

    def test_send_with_connected_provider_dispatches_and_logs_sent(self):
        prov = _FakeProvider()
        log = sms.send_sms(to="+15550002222", text="hello", organization=self.org, provider=prov)
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.provider, "fake")
        self.assertEqual(log.provider_ref, "fake-123")
        self.assertEqual(prov.sent, [("+15550002222", "hello")])

    def test_empty_recipient_or_text_rejected(self):
        with self.assertRaises(sms.SmsError):
            sms.send_sms(to="", text="x")
        with self.assertRaises(sms.SmsError):
            sms.send_sms(to="+1555", text="")

    def test_capability_stays_planned_until_a_gateway_is_connected(self):
        from apps.capabilities.registry import get
        self.assertFalse(get("sms").is_available)   # honest: not offered until connected


class SmsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="SmsApiOrg")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_status_endpoint_is_honest(self):
        resp = self.client.get(reverse("notifications:sms-status"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["configured"])
        self.assertTrue(any(p["key"] == "twilio" for p in resp.json()["providers"]))

    def test_send_endpoint_refuses_with_503_when_unconfigured(self):
        resp = self.client.post(
            reverse("notifications:sms-send"),
            data={"to": "+15550003333", "text": "hi", "organization": self.org.id},
            content_type="application/json", **auth(self.user))
        self.assertEqual(resp.status_code, 503)      # honest unavailability, not a fake 201
