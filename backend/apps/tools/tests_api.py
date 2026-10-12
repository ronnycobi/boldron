"""Tests for the integrations API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens

User = get_user_model()


class IntegrationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(self.user)['access']}"}

    def test_lists_integrations_with_honest_status(self):
        resp = self.client.get(reverse("tools:integrations"), **self._auth())
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["integrations"]
        self.assertIsInstance(items, list)
        for it in items:
            self.assertIn("configured", it)
            self.assertIsInstance(it["configured"], bool)
            self.assertNotIn("credential_env", it)  # env-var name not exposed

    def test_requires_auth(self):
        self.assertEqual(self.client.get(reverse("tools:integrations")).status_code, 401)
