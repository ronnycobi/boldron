"""Multi-currency: real formatting + deterministic conversion, honest when a rate
is missing (never an invented FX figure)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.publishing import currency, ecommerce_service as shop
from apps.publishing.models import Website

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class CurrencyEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="CurOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="CurStore")
        self.website = Website.objects.create(project=self.project, subdomain="curstore")

    def test_formats_per_currency(self):
        self.assertEqual(currency.format_amount(123456, "USD"), "$1,234.56")
        self.assertEqual(currency.format_amount(5000, "ZAR"), "R 50.00")
        self.assertEqual(currency.format_amount(5000, "JPY"), "¥5,000")  # 0 decimals

    def test_identity_rate_is_one(self):
        self.assertEqual(currency.get_rate(self.org, "USD", "USD"), Decimal(1))
        self.assertEqual(currency.convert(1000, frm="USD", to="USD", organization=self.org), 1000)

    def test_stored_rate_converts_deterministically(self):
        currency.set_rate(self.org, base="USD", quote="ZAR", rate="18.5", user=self.owner)
        # $10.00 -> R185.00
        self.assertEqual(currency.convert(1000, frm="USD", to="ZAR", organization=self.org), 18500)

    def test_inverse_rate_is_used_when_only_one_direction_stored(self):
        currency.set_rate(self.org, base="USD", quote="ZAR", rate="20", user=self.owner)
        # R2000 -> $100.00 via the inverse of the stored USD->ZAR rate
        self.assertEqual(currency.convert(200000, frm="ZAR", to="USD", organization=self.org), 10000)

    def test_missing_rate_returns_none_not_a_guess(self):
        self.assertIsNone(currency.convert(1000, frm="USD", to="GBP", organization=self.org))

    def test_live_feed_is_honestly_not_connected(self):
        self.assertFalse(currency.live_feed_status()["connected"])

    def test_revenue_by_currency_flags_unconverted(self):
        # Two paid orders in different currencies; only one rate stored.
        for code, qty in (("USD", 1), ("ZAR", 1)):
            p = shop.create_product(self.website, name=f"P-{code}", price_cents=1000, currency=code)
            o = shop.create_order(self.website, items=[{"product_id": p.id, "quantity": qty}])
            shop.start_checkout(o, provider_key="manual")
            shop.confirm_manual_payment(o, user=self.owner)
        currency.set_rate(self.org, base="ZAR", quote="USD", rate="0.05", user=self.owner)
        rep = currency.revenue_by_currency(self.website, base="USD")
        self.assertEqual(rep["currencies"], 2)
        # USD bucket converts 1:1; ZAR converts via 0.05; nothing unconverted here.
        self.assertEqual(rep["unconverted"], [])
        self.assertEqual(rep["converted_total_cents"], 1000 + 50)

    def test_revenue_flags_bucket_with_no_rate(self):
        p = shop.create_product(self.website, name="G", price_cents=1000, currency="GBP")
        o = shop.create_order(self.website, items=[{"product_id": p.id, "quantity": 1}])
        shop.start_checkout(o, provider_key="manual")
        shop.confirm_manual_payment(o, user=self.owner)
        rep = currency.revenue_by_currency(self.website, base="USD")
        self.assertIn("GBP", rep["unconverted"])

    def test_capability_available(self):
        from apps.capabilities.registry import get
        self.assertTrue(get("currency").is_available)


class CurrencyApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o2@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="m2@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="CurApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="CurApiStore")
        self.website = Website.objects.create(project=self.project, subdomain="curapi")

    def test_list_supported_and_feed_status(self):
        resp = self.client.get(
            reverse("commerce_api:admin-currency", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(c["code"] == "USD" for c in resp.json()["supported"]))
        self.assertFalse(resp.json()["live_feed"]["connected"])

    def test_owner_sets_rate_member_cannot(self):
        ok = self.client.post(
            reverse("commerce_api:admin-currency", args=[self.project.id]),
            data={"base": "USD", "quote": "EUR", "rate": "0.92"},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(ok.status_code, 201)
        denied = self.client.post(
            reverse("commerce_api:admin-currency", args=[self.project.id]),
            data={"base": "USD", "quote": "EUR", "rate": "0.92"},
            content_type="application/json", **auth(self.member))
        self.assertEqual(denied.status_code, 403)
