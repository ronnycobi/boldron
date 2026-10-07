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
            self.assertNotIn("Boldron", html, name)
        # The configured logo URL is used in the page chrome.
        home = self.client.get(reverse("marketing:home")).content.decode()
        self.assertIn("https://cdn.example.com/logo.svg", home)

    def test_no_hard_coded_brand_leaks_by_default(self):
        # With only the neutral default APP_NAME, the retired brand must be absent.
        html = self.client.get(reverse("marketing:home")).content.decode()
        self.assertNotIn("Boldron", html)
        self.assertIn("Application", html)  # the neutral default identity


class TechnologyConfidentialityTests(TestCase):
    """The platform's own implementation stack must never appear on customer-facing
    pages. (Customer-project technologies like Python/Go/React may appear — they
    belong to the customer; these platform-specific terms must not.)"""

    FORBIDDEN = ["Django", "Django REST", "DRF", "PostgreSQL", "psycopg",
                 "Celery", "Redis", "Docker", "Kubernetes"]
    PAGES = ["home", "platform", "how_it_works", "capabilities", "pricing", "about"]

    def test_public_pages_hide_the_implementation_stack(self):
        for name in self.PAGES:
            body = self.client.get(reverse("marketing:" + name)).content.decode()
            for term in self.FORBIDDEN:
                self.assertNotIn(term, body, f"{term!r} leaked on marketing:{name}")

    def test_health_endpoint_reveals_no_framework(self):
        body = self.client.get("/api/v1/health/").json()
        self.assertEqual(set(body), {"service", "status"})
        for term in ("django", "version", "framework", "python"):
            self.assertNotIn(term, body)


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
                         {"email": "new@x.com", "password1": "pw12345!", "password2": "pw12345!", "idea": idea})
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
    def _post(self, **over):
        data = {"email": "new@x.com", "password1": "supersecret1",
                "password2": "supersecret1", "org_name": "Acme"}
        data.update(over)
        return self.client.post(reverse("marketing:signup"), data, follow=True)

    def test_signup_creates_user_org_and_logs_in(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(email="new@x.com")
        org = Organization.objects.get(name="Acme")
        self.assertTrue(Membership.objects.filter(organization=org, user=user, role="owner").exists())
        # Logged in -> the followed redirect lands on the dashboard.
        self.assertEqual(resp.request["PATH_INFO"], reverse("dashboard:home"))

    def test_signup_rejects_short_password(self):
        self.client.post(reverse("marketing:signup"),
                         {"email": "x@x.com", "password1": "short", "password2": "short"})
        self.assertFalse(User.objects.filter(email="x@x.com").exists())

    def test_signup_rejects_mismatched_passwords(self):
        r = self._post(password1="supersecret1", password2="different9")
        self.assertFalse(User.objects.filter(email="new@x.com").exists())
        self.assertContains(r, "two passwords")  # field error shown

    def test_signup_rejects_common_password(self):
        # "password" trips the CommonPasswordValidator even though it's 8 chars.
        self.client.post(reverse("marketing:signup"),
                         {"email": "c@x.com", "password1": "password", "password2": "password"})
        self.assertFalse(User.objects.filter(email="c@x.com").exists())

    def test_signup_rejects_duplicate_email(self):
        User.objects.create_user(email="dup@x.com", password="pw12345678")
        r = self.client.post(reverse("marketing:signup"),
                             {"email": "dup@x.com", "password1": "anotherpw1", "password2": "anotherpw1"})
        self.assertEqual(User.objects.filter(email="dup@x.com").count(), 1)
        self.assertContains(r, "already exists")
        self.assertEqual(User.objects.filter(email="dup@x.com").count(), 1)


class SignupThrottleTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)

    def test_signup_is_rate_limited_per_ip(self):
        for _ in range(10):
            self.client.post(reverse("marketing:signup"),
                             {"email": "a@x.com", "password1": "x", "password2": "y"})
        r = self.client.post(reverse("marketing:signup"),
                             {"email": "a@x.com", "password1": "x", "password2": "y"})
        self.assertContains(r, "Too many attempts")
