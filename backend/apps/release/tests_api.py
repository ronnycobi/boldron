"""Tests for the mobile release API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.release import service

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ReleaseApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="member@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="out@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_providers_are_listed_and_gated(self):
        resp = self.client.get(reverse("release:providers"), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        keys = {p["key"] for p in resp.json()}
        self.assertEqual(keys, {"google_play", "apple_app_store", "huawei_appgallery"})
        self.assertTrue(all(p["available"] is False for p in resp.json()))  # honestly gated

    def test_create_and_list_mobile_app(self):
        resp = self.client.post(
            reverse("release:apps", args=[self.project.id]),
            data={"name": "My App", "package_identifier": "com.acme.app"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "My App")
        listed = self.client.get(reverse("release:apps", args=[self.project.id]), **auth(self.member))
        self.assertEqual(len(listed.json()), 1)

    def test_member_cannot_create_app(self):
        resp = self.client.post(
            reverse("release:apps", args=[self.project.id]),
            data={"name": "X"},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)

    def test_app_detail(self):
        app = service.create_mobile_application(project=self.project, name="A")
        resp = self.client.get(reverse("release:app", args=[app.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("store_apps", resp.json())
        self.assertIn("builds", resp.json())

    def test_app_detail_hidden_from_outsider(self):
        app = service.create_mobile_application(project=self.project, name="A")
        resp = self.client.get(reverse("release:app", args=[app.id]), **auth(self.outsider))
        self.assertEqual(resp.status_code, 404)

    def test_store_connections_honest_default(self):
        resp = self.client.get(
            reverse("release:store-connections", args=[self.org.id]), **auth(self.owner)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(all(r["status"] == "not_connected" for r in resp.json()))
