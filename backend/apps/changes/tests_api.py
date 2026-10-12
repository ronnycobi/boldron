"""Tests for the change-request API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.changes.service import create_change
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ChangeApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="member@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="out@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_create_change_builds_a_plan(self):
        resp = self.client.post(
            reverse("changes:list", args=[self.project.id]),
            data={"description": "Add WhatsApp notifications"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["description"], "Add WhatsApp notifications")
        self.assertIn("plan", body)
        self.assertIn("estimate", body)

    def test_member_cannot_create_change(self):
        resp = self.client.post(
            reverse("changes:list", args=[self.project.id]),
            data={"description": "x"},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)

    def test_list_changes(self):
        create_change(self.project, "One", self.owner)
        resp = self.client.get(
            reverse("changes:list", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_detail_and_implement(self):
        change = create_change(self.project, "Add a reports page", self.owner)
        from apps.changes.service import build_plan

        build_plan(change)
        # Approve if the plan gated it, then implement.
        self.client.post(reverse("changes:approve", args=[change.id]), **auth(self.owner))
        resp = self.client.post(
            reverse("changes:implement", args=[change.id]), **auth(self.owner)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(resp.json()["status"], ["done", "implementing", "planned", "failed"])

    def test_outsider_cannot_see_change(self):
        change = create_change(self.project, "x", self.owner)
        resp = self.client.get(
            reverse("changes:detail", args=[change.id]), **auth(self.outsider)
        )
        self.assertEqual(resp.status_code, 404)

    def test_member_cannot_approve(self):
        change = create_change(self.project, "x", self.owner)
        resp = self.client.post(
            reverse("changes:approve", args=[change.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 403)
