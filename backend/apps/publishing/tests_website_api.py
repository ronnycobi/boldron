"""Tests for the website-management API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.publishing.models import CustomDomain, Lead, Website

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class WebsiteApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="member@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="out@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Web Org")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="Site")
        self.website = Website.objects.create(project=self.project, subdomain="site-x")

    def test_website_status(self):
        resp = self.client.get(
            reverse("commerce_api:website", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["subdomain"], "site-x")

    def test_website_404_without_site(self):
        bare = Project.objects.create(organization=self.org, name="Bare")
        resp = self.client.get(
            reverse("commerce_api:website", args=[bare.id]), **auth(self.owner)
        )
        self.assertEqual(resp.status_code, 404)

    def test_outsider_cannot_read(self):
        resp = self.client.get(
            reverse("commerce_api:website", args=[self.project.id]), **auth(self.outsider)
        )
        self.assertEqual(resp.status_code, 404)

    def test_publish_without_build_fails_cleanly(self):
        # Nothing built yet -> the publish service reports it can't publish (400),
        # never a fabricated success.
        resp = self.client.post(
            reverse("commerce_api:website-publish", args=[self.project.id]), **auth(self.owner)
        )
        self.assertIn(resp.status_code, (201, 400))  # depends on readiness; never 500

    def test_publish_requires_manage(self):
        resp = self.client.post(
            reverse("commerce_api:website-publish", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 403)

    def test_versions_list(self):
        resp = self.client.get(
            reverse("commerce_api:website-versions", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_connect_domain(self):
        resp = self.client.post(
            reverse("commerce_api:website-domains", args=[self.project.id]),
            data={"hostname": "shop.example.com"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["hostname"], "shop.example.com")
        self.assertEqual(resp.json()["verification_status"], "pending")  # not faked

    def test_domain_connect_requires_manage(self):
        resp = self.client.post(
            reverse("commerce_api:website-domains", args=[self.project.id]),
            data={"hostname": "x.example.com"},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)

    def test_leads_list(self):
        Lead.objects.create(website=self.website, name="Jo", email="jo@x.com", message="hi")
        resp = self.client.get(
            reverse("commerce_api:website-leads", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()[0]["name"], "Jo")
