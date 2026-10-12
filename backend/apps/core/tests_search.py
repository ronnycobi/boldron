"""Tests for the global search API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="z@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)
        self.other = Organization.objects.create(name="Other")
        Project.objects.create(organization=self.org, name="Payments Dashboard")
        Project.objects.create(organization=self.other, name="Payments Secret")

    def test_search_finds_own_projects_only(self):
        resp = self.client.get(reverse("core:search") + "?q=payments", **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        names = [p["name"] for p in resp.json()["results"]["projects"]]
        self.assertEqual(names, ["Payments Dashboard"])  # not the other tenant's

    def test_empty_query_returns_empty(self):
        resp = self.client.get(reverse("core:search") + "?q=", **auth(self.user))
        self.assertEqual(resp.json()["results"], {})

    def test_outsider_sees_nothing(self):
        resp = self.client.get(reverse("core:search") + "?q=payments", **auth(self.outsider))
        self.assertEqual(resp.json()["results"]["projects"], [])

    def test_requires_auth(self):
        self.assertEqual(self.client.get(reverse("core:search") + "?q=x").status_code, 401)
