from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.marketing.models import ContactMessage
from apps.organizations.models import Membership, Organization

User = get_user_model()


class BrandingTests(TestCase):
    """The app is white-label: all customer-facing identity comes from the APP_*
    settings, never a hard-coded brand. Changing APP_NAME (and logo/url/…) changes
    the displayed identity with no source change, and the old brand never appears."""

    @override_settings(APP_NAME="Forgewright", APP_TAGLINE="Ship faster",
                       APP_LOGO_URL="https://cdn.example.com/logo.svg")
    def test_rebrand_flows_through_the_ui_from_config(self):
        for name in ["home", "how_it_works", "pricing"]:
            html = self.client.get(reverse("marketing:" + name)).content.decode()
            self.assertIn("Forgewright", html, name)
            self.assertNotIn("DevForge", html, name)
        # The configured logo URL is used in the page chrome.
        home = self.client.get(reverse("marketing:home")).content.decode()
        self.assertIn("https://cdn.example.com/logo.svg", home)

    def test_no_hard_coded_brand_leaks_by_default(self):
        # With only the neutral default APP_NAME, the retired brand must be absent.
        html = self.client.get(reverse("marketing:home")).content.decode()
        self.assertNotIn("DevForge", html)
        self.assertIn("Application", html)  # the neutral default identity


class PublicPagesTests(TestCase):
    PAGES = ["home", "platform", "how_it_works", "capabilities", "pricing", "about", "contact", "signup"]

    def test_all_public_pages_render_without_login(self):
        for name in self.PAGES:
            resp = self.client.get(reverse("marketing:" + name))
            self.assertEqual(resp.status_code, 200, name)

    def test_home_is_the_conversational_front_door(self):
        resp = self.client.get(reverse("marketing:home"))
        self.assertContains(resp, "Build software by")   # hero
        self.assertContains(resp, "Try an example")        # prompt starters
        self.assertContains(resp, 'action="/signup/"')     # prompt routes to signup

    def test_hero_idea_is_carried_into_signup_then_the_builder(self):
        # Logged-out: signup shows the idea; after signup it lands in the builder.
        from apps.accounts.models import User
        idea = "Build a booking system for my salon."
        r = self.client.get(reverse("marketing:signup"), {"idea": idea})
        self.assertContains(r, idea)
        self.client.post(reverse("marketing:signup"),
                         {"email": "new@x.com", "password": "pw12345!", "idea": idea})
        # New account is logged in; the builder prefills from the carried idea.
        home = self.client.get(reverse("dashboard:home"))
        self.assertContains(home, idea)

    def test_public_pages_never_leak_internal_machinery(self):
        # The internal agent topology / orchestration is proprietary and must not
        # appear on the public marketing site (show outcomes, hide the machinery).
        forbidden = [
            "Requirements Agent", "Architect Agent", "Backend Agent",
            "Database Agent", "Testing Agent", "Code Review Agent",
            "orchestrator", "model router", "least-privilege",
            "write_backend", "review_code",
        ]
        for name in self.PAGES:
            body = self.client.get(reverse("marketing:" + name)).content.decode().lower()
            for term in forbidden:
                self.assertNotIn(term.lower(), body, f"{term!r} leaked on marketing:{name}")


class ContactTests(TestCase):
    def test_contact_stores_message(self):
        resp = self.client.post(
            reverse("marketing:contact"),
            {"name": "Ada", "email": "ada@x.com", "message": "Hi there"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ContactMessage.objects.filter(email="ada@x.com").exists())

    def test_contact_requires_fields(self):
        self.client.post(reverse("marketing:contact"), {"name": "Ada"})
        self.assertEqual(ContactMessage.objects.count(), 0)


class SignupTests(TestCase):
    def test_signup_creates_user_org_and_logs_in(self):
        resp = self.client.post(
            reverse("marketing:signup"),
            {"email": "new@x.com", "password": "supersecret1", "org_name": "Acme"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(email="new@x.com")
        org = Organization.objects.get(name="Acme")
        self.assertTrue(Membership.objects.filter(organization=org, user=user, role="owner").exists())
        # Logged in -> the followed redirect lands on the dashboard.
        self.assertEqual(resp.request["PATH_INFO"], reverse("dashboard:home"))

    def test_signup_rejects_short_password(self):
        self.client.post(reverse("marketing:signup"), {"email": "x@x.com", "password": "short"})
        self.assertFalse(User.objects.filter(email="x@x.com").exists())

    def test_signup_rejects_duplicate_email(self):
        User.objects.create_user(email="dup@x.com", password="pw12345678")
        self.client.post(reverse("marketing:signup"), {"email": "dup@x.com", "password": "anotherpw1"})
        self.assertEqual(User.objects.filter(email="dup@x.com").count(), 1)
