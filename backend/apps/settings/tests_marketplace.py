"""Integration marketplace (spec §12): categorised catalogue with honest status
composed from the real subsystems — never a fabricated connection, never a secret."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.settings import marketplace as mk

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


def _flat(market):
    return {e["id"]: e for g in market["groups"] for e in g["items"]}


class MarketplaceTests(TestCase):
    def test_categories_cover_the_spec_areas(self):
        cats = {g["category"] for g in mk.marketplace()["groups"]}
        self.assertLessEqual({"Payments", "Email", "AI", "Communication", "Developer"}, cats)

    def test_manual_payments_and_builtins_are_available(self):
        items = _flat(mk.marketplace())
        self.assertEqual(items["manual"]["status"], mk.AVAILABLE)
        self.assertEqual(items["files"]["status"], mk.AVAILABLE)
        self.assertEqual(items["analytics"]["status"], mk.AVAILABLE)
        self.assertTrue(items["manual"]["usable"])

    def test_gated_integrations_need_connection_in_this_environment(self):
        # No third-party credentials are set here — gated adapters read "connect".
        items = _flat(mk.marketplace())
        for cid in ("stripe", "payfast", "twilio", "slack", "whatsapp", "github"):
            self.assertEqual(items[cid]["status"], mk.CONNECT, cid)
            self.assertFalse(items[cid]["connected"], cid)

    def test_connect_entries_expose_env_var_names_not_values(self):
        items = _flat(mk.marketplace())
        self.assertIn("STRIPE_SECRET_KEY", items["stripe"]["credential_env"])
        # Only NAMES appear — there is never a 'value'/'secret' field.
        for e in items.values():
            self.assertNotIn("value", e)
            self.assertNotIn("secret", e)

    def test_connected_reflects_a_real_credential(self):
        # Connecting Stripe (a real env key present) flips it to connected.
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"}):
            items = _flat(mk.marketplace())
            self.assertEqual(items["stripe"]["status"], mk.CONNECTED)
            self.assertTrue(items["stripe"]["connected"])

    def test_email_is_usable_via_dev_backend(self):
        items = _flat(mk.marketplace())
        # Console/dev backend in tests → available (works), not "connect".
        self.assertIn(items["email"]["status"], (mk.AVAILABLE, mk.CONNECTED))
        self.assertTrue(items["email"]["usable"])

    def test_summary_counts(self):
        m = mk.marketplace()
        self.assertEqual(m["total"], len(_flat(m)))
        self.assertGreaterEqual(m["usable"], m["connected"])


class MarketplaceApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="m@x.com", password="pw12345!")

    def test_endpoint_returns_categorised_marketplace(self):
        resp = self.client.get(reverse("settings_api:marketplace"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        cats = {g["category"] for g in resp.json()["groups"]}
        self.assertIn("Payments", cats)

    def test_endpoint_requires_auth(self):
        resp = self.client.get(reverse("settings_api:marketplace"))
        self.assertEqual(resp.status_code, 401)
