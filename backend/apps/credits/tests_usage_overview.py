"""Composed usage overview (spec §17): real meters only — a genuine AI-credit %
where there's an allowance, and honest counts (no fabricated limits) elsewhere."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.credits.usage import usage_overview
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class UsageOverviewTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="UsageOrg")
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_counts_are_real(self):
        Project.objects.create(organization=self.org, name="A")
        Project.objects.create(organization=self.org, name="B")
        ov = usage_overview(self.org)
        self.assertEqual(ov["projects"], 2)
        self.assertEqual(ov["members"], 1)

    def test_storage_sums_real_file_sizes(self):
        from apps.files.models import StoredFile
        StoredFile.objects.create(organization=self.org, file="x", size=5120)
        ov = usage_overview(self.org)
        self.assertEqual(ov["storage"]["bytes"], 5120)
        self.assertEqual(ov["storage"]["display"], "5.0 KB")

    def test_credits_meter_is_in_an_honest_range(self):
        # used_pct is either None (no allowance => unlimited) or a real 0-100 value,
        # never a fabricated figure outside that range.
        ov = usage_overview(self.org)
        pct = ov["credits"]["used_pct"]
        self.assertTrue(pct is None or (0 <= pct <= 100))

    def test_credits_used_pct_with_allowance(self):
        from apps.credits.models import CreditAccount
        from decimal import Decimal
        # An account on a plan with an allowance gives a real used %.
        acct = CreditAccount.objects.create(organization=self.org, plan="starter")
        acct.balance = Decimal("250")
        acct.save()
        from unittest import mock
        with mock.patch("apps.credits.services.plans", return_value={"starter": 1000}):
            ov = usage_overview(self.org)
        self.assertFalse(ov["credits"]["unlimited"])
        self.assertEqual(ov["credits"]["used_pct"], 75)   # (1000-250)/1000


class UsageOverviewApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="UApiOrg")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_endpoint(self):
        resp = self.client.get(
            reverse("credits:usage-overview", args=[self.org.id]), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("credits", resp.json())
        self.assertIn("storage", resp.json())

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("credits:usage-overview", args=[self.org.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
