"""Privacy requests & data rights (spec §17-19, §75): a tracked workflow, a
secrets-safe export, deletion that is never an instant wipe, and strict isolation
(a user sees only their own requests; the queue is staff-only)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.privacy import service
from apps.privacy.models import PrivacyRequest, RequestStatus, RequestType
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)

    def test_submit_sets_received_and_deadline(self):
        req = service.submit(self.user, RequestType.EXPORT)
        self.assertEqual(req.status, RequestStatus.RECEIVED)
        self.assertIsNotNone(req.deadline)
        self.assertEqual(req.events.count(), 1)

    def test_unknown_type_rejected(self):
        with self.assertRaises(service.PrivacyError):
            service.submit(self.user, "teleport")

    def test_lifecycle_and_resolution(self):
        req = service.submit(self.user, RequestType.ACCESS)
        service.transition(req, RequestStatus.VERIFIED, actor=self.staff)
        req.refresh_from_db()
        self.assertTrue(req.identity_verified)
        self.assertTrue(req.is_open)
        service.resolve(req, resolution="Provided", actor=self.staff)
        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.COMPLETED)
        self.assertFalse(req.is_open)
        self.assertIsNotNone(req.resolved_at)

    def test_deletion_is_a_tracked_request_not_an_instant_wipe(self):
        req = service.submit(self.user, RequestType.DELETION)
        # submitting does NOT delete the user — it opens a workflow
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(req.status, RequestStatus.RECEIVED)


class ExportTests(TestCase):
    def test_export_excludes_secrets(self):
        user = User.objects.create_user(email="e@x.com", password="pw12345!")
        data = service.build_export(user)
        blob = str(data).lower()
        for leak in ("password", "secret", "private_key", "cvv"):
            self.assertNotIn(leak, blob)

    def test_strip_secrets_drops_credential_keys(self):
        dirty = {"email": "a@x.com", "api_secret": "shh",
                 "nested": {"password": "p", "name": "ok"}}
        clean = service._strip_secrets(dirty)
        self.assertIn("email", clean)
        self.assertNotIn("api_secret", clean)
        self.assertNotIn("password", clean["nested"])
        self.assertIn("name", clean["nested"])


class PrivacyApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.other = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)

    def test_submit_and_list_own(self):
        resp = self.client.post(reverse("privacy_api:requests"),
                                {"request_type": "export"},
                                content_type="application/json", **auth(self.user))
        self.assertEqual(resp.status_code, 201)
        listing = self.client.get(reverse("privacy_api:requests"), **auth(self.user)).json()
        self.assertEqual(len(listing["requests"]), 1)

    def test_cannot_see_another_users_request(self):
        req = service.submit(self.user, RequestType.ACCESS)
        resp = self.client.get(reverse("privacy_api:request", args=[req.id]), **auth(self.other))
        self.assertEqual(resp.status_code, 403)

    def test_export_endpoint_returns_data(self):
        resp = self.client.get(reverse("privacy_api:export"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)

    def test_admin_queue_is_staff_only(self):
        resp = self.client.get(reverse("privacy_api:admin"), **auth(self.user))
        self.assertEqual(resp.status_code, 403)
        ok = self.client.get(reverse("privacy_api:admin"), **auth(self.staff))
        self.assertEqual(ok.status_code, 200)

    def test_staff_can_resolve(self):
        req = service.submit(self.user, RequestType.CORRECTION)
        resp = self.client.post(
            reverse("privacy_api:admin_action", args=[req.id]),
            {"action": "resolve", "resolution": "Fixed"},
            content_type="application/json", **auth(self.staff))
        self.assertEqual(resp.json()["status"], "completed")


class PrivacyWebTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="w@x.com", password="pw12345!")
        self.staff = User.objects.create_user(email="st@x.com", password="pw12345!", is_staff=True)

    def test_customer_can_submit_privacy_request(self):
        self.client.force_login(self.user)
        self.client.post(reverse("dashboard:org_privacy"),
                         {"action": "privacy_request", "request_type": "export"})
        self.assertTrue(PrivacyRequest.objects.filter(user=self.user,
                                                      request_type="export").exists())
        html = self.client.get(reverse("dashboard:org_privacy")).content.decode()
        self.assertIn("Privacy requests", html)

    def test_console_privacy_queue_is_staff_only(self):
        self.client.force_login(self.user)
        self.assertIn(self.client.get(reverse("console:privacy")).status_code, (302, 403))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("console:privacy")).status_code, 200)

    def test_staff_transition_via_console(self):
        req = service.submit(self.user, RequestType.ACCESS)
        self.client.force_login(self.staff)
        self.client.post(reverse("console:privacy"),
                         {"request": req.id, "action": "transition", "status": "verified"})
        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.VERIFIED)
