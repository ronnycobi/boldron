"""Account lifecycle & appeals (spec §42-43): status changes always record a
reason, suspension genuinely blocks building, and appeals have a reviewed
outcome. Governance records are isolated per org."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.governance import service
from apps.governance.models import AccountAction, AccountStatus, Appeal
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class StatusTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)

    def test_default_status_is_active(self):
        self.assertEqual(service.current_status(self.org), AccountStatus.ACTIVE)
        self.assertFalse(service.is_blocked(self.org))

    def test_suspension_requires_a_reason(self):
        with self.assertRaises(service.GovernanceError):
            service.set_status(self.org, AccountStatus.SUSPENDED, actor=self.staff)

    def test_status_change_is_logged_with_reason(self):
        service.set_status(self.org, AccountStatus.SUSPENDED, reason="Abuse",
                           policy_section="AUP 3.1", actor=self.staff)
        self.assertTrue(service.is_blocked(self.org))
        action = AccountAction.objects.get(organization=self.org)
        self.assertEqual(action.reason, "Abuse")
        self.assertEqual(action.from_status, "active")

    def test_restricted_is_not_blocked(self):
        service.set_status(self.org, AccountStatus.RESTRICTED, actor=self.staff)
        self.assertFalse(service.is_blocked(self.org))


class EnforcementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)

    def test_suspended_account_cannot_build(self):
        from apps.projects.builds import create_and_start_build
        service.set_status(self.org, AccountStatus.SUSPENDED, reason="x", actor=self.staff)
        with self.assertRaises(service.GovernanceError):
            create_and_start_build(self.org, "a todo app", self.user)
        self.assertEqual(Project.objects.filter(organization=self.org).count(), 0)


class AppealTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)

    def test_appeal_reason_required(self):
        with self.assertRaises(service.GovernanceError):
            service.submit_appeal(self.org, self.user, reason="")

    def test_reversed_appeal_restores_account(self):
        service.set_status(self.org, AccountStatus.SUSPENDED, reason="Abuse", actor=self.staff)
        appeal = service.submit_appeal(self.org, self.user, reason="Not us")
        service.decide_appeal(appeal, Appeal.Outcome.REVERSED, reviewer=self.staff)
        self.assertEqual(service.current_status(self.org), AccountStatus.ACTIVE)


class GovernanceApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)

    def test_member_sees_own_status(self):
        resp = self.client.get(reverse("governance:status", args=[self.org.id]), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "active")

    def test_outsider_cannot_see_status(self):
        resp = self.client.get(reverse("governance:status", args=[self.org.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_staff_can_suspend_then_customer_appeals(self):
        s = self.client.post(reverse("governance:admin_status", args=[self.org.id]),
                             {"status": "suspended", "reason": "Abuse"},
                             content_type="application/json", **auth(self.staff))
        self.assertEqual(s.json()["status"], "suspended")
        a = self.client.post(reverse("governance:appeal", args=[self.org.id]),
                             {"reason": "Please review"}, content_type="application/json",
                             **auth(self.owner))
        self.assertEqual(a.status_code, 201)

    def test_set_status_is_staff_only(self):
        resp = self.client.post(reverse("governance:admin_status", args=[self.org.id]),
                                {"status": "suspended", "reason": "x"},
                                content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 403)


class GovernanceWebTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="ow@x.com", password="pw12345!")
        self.staff = User.objects.create_user(email="st@x.com", password="pw12345!", is_staff=True)
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)

    def test_console_org_page_sets_status(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("console:org", args=[self.org.id]),
                         {"action": "set_status", "status": "suspended", "reason": "Abuse"})
        self.assertEqual(service.current_status(self.org), AccountStatus.SUSPENDED)

    def test_customer_privacy_page_shows_status_and_appeal(self):
        service.set_status(self.org, AccountStatus.SUSPENDED, reason="x", actor=self.staff)
        self.client.force_login(self.owner)
        html = self.client.get(reverse("dashboard:org_privacy")).content.decode()
        self.assertIn("Account status", html)
        self.client.post(reverse("dashboard:org_privacy"),
                         {"action": "appeal", "organization": self.org.id,
                          "reason": "Please review"})
        self.assertTrue(Appeal.objects.filter(organization=self.org).exists())
