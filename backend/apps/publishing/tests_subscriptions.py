"""Recurring billing: real cycles, honest paid/unpaid state, idempotent renewals.

A subscription must never fake a charge: each cycle is a genuine order that is only
"paid" when a payment actually succeeds, and the renewal engine must not double-bill.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.publishing import ecommerce_service as shop
from apps.publishing import invoicing, subscriptions as subs
from apps.publishing.models import Website

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class SubscriptionEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="SubOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="SubStore")
        self.website = Website.objects.create(project=self.project, subdomain="substore")
        self.plan = subs.create_plan(
            self.website, name="Pro", amount_cents=2000, interval="monthly", user=self.owner)

    def test_subscribe_opens_a_real_unpaid_cycle_order(self):
        sub, order = subs.subscribe(
            self.plan, customer_name="Ann", customer_email="ann@x.com", user=self.owner)
        self.assertEqual(sub.status, "active")
        self.assertEqual(order.status, "awaiting_payment")   # NOT optimistically paid
        self.assertEqual(order.total_cents, 2000)
        self.assertEqual(sub.cycles.count(), 1)
        # The cycle order is a genuine, invoiceable order.
        d = invoicing.invoice_data(order)
        self.assertEqual(d["payment_state"], "Unpaid")
        self.assertEqual(d["total_cents"], 2000)

    def test_settle_cycle_marks_subscription_active_and_counts_renewal(self):
        sub, order = subs.subscribe(self.plan, customer_email="a@x.com", user=self.owner)
        subs.settle_cycle(order, user=self.owner)
        order.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertEqual(sub.status, "active")
        self.assertEqual(sub.renewals, 1)

    def test_renew_due_opens_next_cycle_only_when_period_ended(self):
        sub, order = subs.subscribe(self.plan, customer_email="a@x.com", user=self.owner)
        subs.settle_cycle(order, user=self.owner)
        # Not due yet.
        self.assertEqual(subs.renew_due(), 0)
        # Fast-forward past the period end.
        sub.current_period_end = timezone.now() - timedelta(minutes=1)
        sub.save(update_fields=["current_period_end"])
        self.assertEqual(subs.renew_due(), 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "past_due")        # new cycle unpaid
        self.assertEqual(sub.cycles.count(), 2)

    def test_renew_due_is_idempotent_no_double_billing(self):
        sub, order = subs.subscribe(self.plan, customer_email="a@x.com", user=self.owner)
        subs.settle_cycle(order, user=self.owner)
        sub.current_period_end = timezone.now() - timedelta(minutes=1)
        sub.save(update_fields=["current_period_end"])
        subs.renew_due()
        before = sub.cycles.count()
        subs.renew_due()   # run again immediately — must NOT stack another bill
        subs.renew_due()
        self.assertEqual(sub.cycles.count(), before)

    def test_monthly_interval_advances_a_calendar_month(self):
        import datetime
        start = datetime.datetime(2026, 1, 31, tzinfo=datetime.timezone.utc)
        nxt = subs._advance(start, "monthly")
        self.assertEqual((nxt.year, nxt.month, nxt.day), (2026, 2, 28))  # clamps

    def test_cancel_stops_future_renewals(self):
        sub, order = subs.subscribe(self.plan, customer_email="a@x.com", user=self.owner)
        subs.settle_cycle(order, user=self.owner)
        subs.cancel(sub, user=self.owner)
        sub.current_period_end = timezone.now() - timedelta(minutes=1)
        sub.save(update_fields=["current_period_end"])
        self.assertEqual(subs.renew_due(), 0)   # cancelled → no new cycle

    def test_overview_reports_real_mrr(self):
        subs.subscribe(self.plan, customer_email="a@x.com", user=self.owner)
        subs.subscribe(self.plan, customer_email="b@x.com", user=self.owner)
        ov = subs.overview(self.website)
        self.assertEqual(ov["active"], 2)
        self.assertEqual(ov["mrr_cents"], 4000)   # 2 × $20 monthly

    def test_capability_available(self):
        from apps.capabilities.registry import get
        self.assertTrue(get("subscriptions").is_available)


class SubscriptionApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o2@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="m2@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="SubApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="SubApiStore")
        self.website = Website.objects.create(project=self.project, subdomain="subapi")

    def test_create_plan_and_subscribe_via_api(self):
        create = self.client.post(
            reverse("commerce_api:admin-plans", args=[self.project.id]),
            data={"name": "Gold", "amount_cents": 5000, "interval": "monthly"},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(create.status_code, 201)
        plan_id = create.json()["id"]
        sub = self.client.post(
            reverse("commerce_api:admin-subscriptions", args=[self.project.id]),
            data={"plan_id": plan_id, "customer_email": "c@x.com"},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(sub.status_code, 201)
        self.assertTrue(sub.json()["first_cycle_order"].startswith("ORD-"))

    def test_member_cannot_create_plan(self):
        resp = self.client.post(
            reverse("commerce_api:admin-plans", args=[self.project.id]),
            data={"name": "X", "amount_cents": 100},
            content_type="application/json", **auth(self.member))
        self.assertEqual(resp.status_code, 403)

    def test_subscriptions_list_reports_overview(self):
        plan = subs.create_plan(self.website, name="Basic", amount_cents=1000, user=self.owner)
        subs.subscribe(plan, customer_email="x@x.com", user=self.owner)
        resp = self.client.get(
            reverse("commerce_api:admin-subscriptions", args=[self.project.id]),
            **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["overview"]["active"], 1)
        self.assertEqual(len(resp.json()["subscriptions"]), 1)
