"""Tests for the customer support API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.support import service
from apps.support.models import SupportTicket

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class SupportApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="z@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_create_and_list_ticket(self):
        resp = self.client.post(
            reverse("support_api:tickets"),
            data={"organization": self.org.id, "subject": "Help me", "body": "It broke"},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["number"])
        listed = self.client.get(reverse("support_api:tickets"), **auth(self.user))
        self.assertEqual(len(listed.json()), 1)

    def test_thread_hides_internal_notes(self):
        ticket = service.create_ticket(
            organization=self.org, user=self.user, subject="S", body="public msg"
        )
        service.add_message(ticket, author=self.user, body="internal only", internal=True)
        resp = self.client.get(
            reverse("support_api:ticket", args=[ticket.id]), **auth(self.user)
        )
        bodies = [m["body"] for m in resp.json()["messages"]]
        self.assertIn("public msg", bodies)
        self.assertNotIn("internal only", bodies)

    def test_reply_adds_message(self):
        ticket = service.create_ticket(organization=self.org, user=self.user, subject="S", body="b")
        resp = self.client.post(
            reverse("support_api:ticket-reply", args=[ticket.id]),
            data={"body": "any update?"},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("any update?", [m["body"] for m in resp.json()["messages"]])

    def test_outsider_cannot_see_ticket(self):
        ticket = service.create_ticket(organization=self.org, user=self.user, subject="S", body="b")
        resp = self.client.get(
            reverse("support_api:ticket", args=[ticket.id]), **auth(self.outsider)
        )
        self.assertEqual(resp.status_code, 404)

    def test_meta_lists_choices(self):
        resp = self.client.get(reverse("support_api:meta"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(c["value"] == "bug" for c in resp.json()["categories"]))

    def test_tickets_require_auth(self):
        self.assertEqual(self.client.get(reverse("support_api:tickets")).status_code, 401)
