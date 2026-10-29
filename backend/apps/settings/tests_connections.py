"""Unified integration status: honest, env-gated, no secret ever exposed.

In this environment no third-party credentials are set, so every external
integration must read 'not connected' — the truth, never a fabricated 'enabled'.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.settings.connections import integration_status

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class IntegrationStatusTests(TestCase):
    def test_aggregates_connectors_payments_and_sms(self):
        status = integration_status()
        keys = {i["key"] for i in status["integrations"]}
        # Connectors (incl. the newly added Google/SSO + WhatsApp), gateways, SMS.
        self.assertLessEqual(
            {"github", "slack", "google", "whatsapp", "stripe", "payfast",
             "twilio", "africastalking"},
            keys)

    def test_everything_is_gated_in_this_environment(self):
        status = integration_status()
        self.assertEqual(status["connected"], 0)
        self.assertTrue(status["all_gated"])
        self.assertTrue(all(not i["connected"] for i in status["integrations"]))

    def test_no_secret_values_are_exposed(self):
        # Only env-var NAMES may appear, never a value (there are none set anyway).
        for i in integration_status()["integrations"]:
            self.assertNotIn("secret", i)
            self.assertNotIn("token", {k.lower() for k in i})

    def test_manual_payment_is_not_listed_as_an_external_integration(self):
        keys = {i["key"] for i in integration_status()["integrations"]}
        self.assertNotIn("manual", keys)

    def test_integration_capabilities_stay_planned(self):
        from apps.capabilities.registry import get
        for cid in ("google", "slack", "whatsapp", "stripe", "payfast"):
            self.assertFalse(get(cid).is_available, cid)


class IntegrationStatusApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_endpoint_reports_honest_status(self):
        resp = self.client.get(reverse("settings_api:integrations"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["all_gated"])
        self.assertEqual(body["connected"], 0)
        self.assertGreaterEqual(body["total"], 8)
