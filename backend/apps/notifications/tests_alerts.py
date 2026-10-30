"""Alerting engine (spec §21): records an alert, delivers to owners/admins over the
real email backend, honours the org preference, never fakes push."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.notifications import alerts
from apps.notifications.models import Alert
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class AlertEngineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="AlertOrg")
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.admin = User.objects.create_user(email="admin@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="member@x.com", password="pw12345!")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.admin, role=Role.ADMIN)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_raise_records_and_emails_owners_and_admins(self):
        mail.outbox = []
        a = alerts.raise_alert(self.project, kind="deploy_failed",
                               message="Production deploy failed", severity="high")
        self.assertIsInstance(a, Alert)
        self.assertEqual(a.emailed, 2)             # owner + admin, not the member
        self.assertEqual(len(mail.outbox), 1)      # one message to both recipients
        self.assertEqual(set(mail.outbox[0].to), {"owner@x.com", "admin@x.com"})

    def test_preference_off_suppresses_email_but_still_records(self):
        alerts.set_email_enabled(self.org, False)
        mail.outbox = []
        a = alerts.raise_alert(self.project, kind="incident", message="x")
        self.assertEqual(a.emailed, 0)             # no email
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(Alert.objects.filter(id=a.id).exists())   # event still recorded

    def test_recent_lists_history(self):
        alerts.raise_alert(self.project, kind="a", message="1")
        alerts.raise_alert(self.project, kind="b", message="2")
        self.assertEqual(len(alerts.recent(self.project)), 2)

    def test_opening_an_incident_raises_an_alert(self):
        from apps.incidents import service as inc
        mail.outbox = []
        inc.open_incident(self.project, title="Checkout down", severity="critical")
        a = Alert.objects.filter(project=self.project, kind="incident").first()
        self.assertIsNotNone(a)
        self.assertEqual(a.severity, "critical")
        self.assertEqual(len(mail.outbox), 1)      # owners/admins notified


class AlertApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="ao@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="am@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="ax@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="AlertApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_history_and_preference(self):
        alerts.raise_alert(self.project, kind="k", message="m", severity="high")
        resp = self.client.get(
            reverse("notifications:alerts", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["email_enabled"])
        self.assertEqual(len(resp.json()["alerts"]), 1)

    def test_owner_can_toggle_member_cannot(self):
        off = self.client.post(
            reverse("notifications:alerts", args=[self.project.id]),
            data={"email_enabled": False}, content_type="application/json", **auth(self.owner))
        self.assertEqual(off.status_code, 200)
        self.assertFalse(off.json()["email_enabled"])
        denied = self.client.post(
            reverse("notifications:alerts", args=[self.project.id]),
            data={"email_enabled": True}, content_type="application/json", **auth(self.member))
        self.assertEqual(denied.status_code, 403)

    def test_tenant_isolation(self):
        resp = self.client.get(
            reverse("notifications:alerts", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
