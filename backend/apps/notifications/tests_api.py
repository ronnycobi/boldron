"""Tests for the activity/notifications feed API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.audit.service import record as audit
from apps.organizations.models import Organization, Role

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class NotificationFeedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="z@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)
        self.other_org = Organization.objects.create(name="Other")

    def test_feed_shows_own_org_events_humanized(self):
        audit("change.approved", actor=self.user, organization=self.org,
              target="change:1", summary="Add payments")
        resp = self.client.get(reverse("notifications:feed"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["notifications"]
        self.assertEqual(items[0]["title"], "Change approved")
        self.assertEqual(items[0]["detail"], "Add payments")
        self.assertFalse(resp.json()["push_available"])  # honest: no push provider

    def test_feed_excludes_other_orgs(self):
        audit("change.approved", organization=self.other_org, summary="not mine")
        resp = self.client.get(reverse("notifications:feed"), **auth(self.user))
        self.assertEqual(resp.json()["notifications"], [])

    def test_org_filter(self):
        audit("website.publish", actor=self.user, organization=self.org, summary="v1")
        resp = self.client.get(
            reverse("notifications:feed") + f"?org={self.org.id}", **auth(self.user)
        )
        self.assertEqual(len(resp.json()["notifications"]), 1)

    def test_requires_auth(self):
        self.assertEqual(self.client.get(reverse("notifications:feed")).status_code, 401)
