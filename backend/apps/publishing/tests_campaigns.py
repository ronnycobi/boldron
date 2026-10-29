"""Email campaigns: real sends over the email engine, honest per-recipient results."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.publishing import campaigns, ecommerce_service as shop
from apps.publishing.models import Lead, Website

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class CampaignEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="CampOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="CampStore")
        self.website = Website.objects.create(project=self.project, subdomain="campstore")

    def _add_lead(self, email, name=""):
        return Lead.objects.create(website=self.website, email=email, name=name)

    def _paid_customer(self, email, name=""):
        p = shop.create_product(self.website, name="P", price_cents=500)
        o = shop.create_order(self.website, items=[{"product_id": p.id, "quantity": 1}],
                              customer_email=email, customer_name=name)
        shop.start_checkout(o, provider_key="manual")
        shop.confirm_manual_payment(o, user=self.owner)
        return o

    def test_audience_merges_leads_and_customers_deduped(self):
        self._add_lead("a@x.com", "Ann")
        self._add_lead("a@x.com", "Ann Again")   # dup address
        self._paid_customer("b@x.com", "Bob")
        audience = campaigns.build_audience(self.website, "all")
        self.assertEqual(set(audience), {"a@x.com", "b@x.com"})

    def test_audience_source_filtering(self):
        self._add_lead("lead@x.com")
        self._paid_customer("cust@x.com")
        self.assertEqual(set(campaigns.build_audience(self.website, "leads")), {"lead@x.com"})
        self.assertEqual(set(campaigns.build_audience(self.website, "customers")), {"cust@x.com"})

    def test_send_dispatches_real_email_and_records_results(self):
        self._add_lead("ann@x.com", "Ann Smith")
        self._add_lead("ben@x.com", "Ben")
        c = campaigns.create_campaign(
            self.website, subject="News", body="Hi {{first_name}}!", user=self.owner)
        mail.outbox = []
        campaigns.send_campaign(c, user=self.owner)
        c.refresh_from_db()
        self.assertEqual(c.status, "sent")
        self.assertEqual(c.total, 2)
        self.assertEqual(c.sent_count, 2)
        self.assertEqual(c.failed_count, 0)
        self.assertEqual(len(mail.outbox), 2)       # genuinely dispatched
        # Personalisation really happened.
        bodies = sorted(m.body for m in mail.outbox)
        self.assertIn("Hi Ann!", bodies)
        self.assertIn("Hi Ben!", bodies)
        self.assertEqual(c.recipients.filter(status="sent").count(), 2)

    def test_send_with_no_audience_is_refused_not_faked(self):
        c = campaigns.create_campaign(self.website, subject="S", body="B", user=self.owner)
        with self.assertRaises(campaigns.CampaignError):
            campaigns.send_campaign(c, user=self.owner)
        c.refresh_from_db()
        self.assertEqual(c.status, "draft")         # never flips to "sent" with nobody to send to

    def test_create_requires_subject_and_body(self):
        with self.assertRaises(campaigns.CampaignError):
            campaigns.create_campaign(self.website, subject="", body="x", user=self.owner)
        with self.assertRaises(campaigns.CampaignError):
            campaigns.create_campaign(self.website, subject="x", body="", user=self.owner)

    def test_capability_available(self):
        from apps.capabilities.registry import get
        self.assertTrue(get("campaigns").is_available)


class CampaignApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o2@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="m2@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="CampApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="CampApiStore")
        self.website = Website.objects.create(project=self.project, subdomain="campapi")
        Lead.objects.create(website=self.website, email="x@x.com", name="X")

    def test_create_and_send_via_api(self):
        create = self.client.post(
            reverse("commerce_api:admin-campaigns", args=[self.project.id]),
            data={"subject": "Hello", "body": "Hi {{name}}", "audience_source": "leads"},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(create.status_code, 201)
        cid = create.json()["id"]
        mail.outbox = []
        send = self.client.post(
            reverse("commerce_api:admin-campaign-send", args=[self.project.id, cid]),
            **auth(self.owner))
        self.assertEqual(send.status_code, 200)
        self.assertEqual(send.json()["sent_count"], 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_member_cannot_create_campaign(self):
        resp = self.client.post(
            reverse("commerce_api:admin-campaigns", args=[self.project.id]),
            data={"subject": "S", "body": "B"},
            content_type="application/json", **auth(self.member))
        self.assertEqual(resp.status_code, 403)

    def test_list_reports_audience_size(self):
        resp = self.client.get(
            reverse("commerce_api:admin-campaigns", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["audience_size"], 1)
