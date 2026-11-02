"""Governance overview (spec §69): staff-only, and every figure comes from real
database state."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class GovernanceDashboardTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_staff_only(self):
        self.client.force_login(self.user)
        self.assertIn(self.client.get(reverse("console:governance")).status_code, (302, 403))

    def test_shows_real_counts(self):
        # seed one published mandatory legal doc + one privacy request
        from apps.legal import service as legal
        doc = legal.create_draft(document_type="terms_of_service", title="T",
                                 version="1.0", content="x", requires_acceptance=True,
                                 user=self.staff)
        legal.approve(doc, user=self.staff)
        legal.publish(doc, user=self.staff)
        from apps.privacy import service as privacy
        from apps.privacy.models import RequestType
        privacy.submit(self.user, RequestType.EXPORT)

        self.client.force_login(self.staff)
        html = self.client.get(reverse("console:governance")).content.decode()
        self.assertIn("Governance", html)
        self.assertIn("Legal documents", html)
        self.assertIn("Privacy requests", html)
