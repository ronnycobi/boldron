"""Consent management (spec §21, §45, §60): necessary cookies always on, optional
off until opted in (no dark patterns), marketing opt-IN and kept separate from
service communications; append-only history is preserved."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.consent import service
from apps.consent.models import CookieConsent, MarketingConsent
from apps.notifications import preferences

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class CookieConsentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_no_consent_means_optional_cookies_are_off(self):
        self.assertTrue(service.cookie_allowed("necessary", user=self.user))
        self.assertFalse(service.cookie_allowed("analytics", user=self.user))
        self.assertFalse(service.cookie_allowed("marketing", user=self.user))

    def test_opting_in_allows_only_chosen_categories(self):
        service.record_cookie_consent(user=self.user,
                                      categories={"analytics": True, "marketing": False})
        self.assertTrue(service.cookie_allowed("analytics", user=self.user))
        self.assertFalse(service.cookie_allowed("marketing", user=self.user))

    def test_necessary_is_forced_on_even_if_declined(self):
        rec = service.record_cookie_consent(user=self.user,
                                            categories={"necessary": False})
        self.assertTrue(rec.necessary)   # cannot be turned off

    def test_decline_all_is_a_valid_choice(self):
        service.record_cookie_consent(user=self.user, categories={})
        state = service.cookie_state(user=self.user)
        self.assertTrue(state["recorded"])
        self.assertFalse(state["analytics"])

    def test_history_is_append_only(self):
        service.record_cookie_consent(user=self.user, categories={"analytics": True})
        service.record_cookie_consent(user=self.user, categories={"analytics": False})
        self.assertEqual(CookieConsent.objects.filter(user=self.user).count(), 2)
        # latest wins
        self.assertFalse(service.cookie_allowed("analytics", user=self.user))

    def test_anonymous_consent_by_id(self):
        service.record_cookie_consent(anon_id="abc123", categories={"preferences": True})
        self.assertTrue(service.cookie_allowed("preferences", anon_id="abc123"))
        self.assertFalse(service.cookie_allowed("preferences", anon_id="other"))


class MarketingConsentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_marketing_defaults_off_optin(self):
        self.assertFalse(service.marketing_opted_in(self.user))

    def test_opt_in_then_out_is_logged(self):
        service.set_marketing_consent(self.user, True, source="signup")
        self.assertTrue(service.marketing_opted_in(self.user))
        service.set_marketing_consent(self.user, False)
        self.assertFalse(service.marketing_opted_in(self.user))
        self.assertEqual(MarketingConsent.objects.filter(user=self.user).count(), 2)

    def test_marketing_is_separate_from_service_comms(self):
        # service/transactional prefs (opt-out) are untouched by marketing opt-out
        service.set_marketing_consent(self.user, False)
        self.assertTrue(preferences.wants(self.user, "support_updates"))


class ConsentApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_cookie_consent_works_anonymously(self):
        resp = self.client.post(
            reverse("consent:cookies"),
            {"anon_id": "visitor1", "categories": {"analytics": True}},
            content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["analytics"])

    def test_marketing_requires_auth_and_toggles(self):
        anon = self.client.get(reverse("consent:marketing"))
        self.assertIn(anon.status_code, (401, 403))
        resp = self.client.post(reverse("consent:marketing"), {"opted_in": True},
                                content_type="application/json", **auth(self.user))
        self.assertTrue(resp.json()["opted_in"])


class ConsentWebTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="w@x.com", password="pw12345!")

    def test_legal_center_saves_cookie_and_marketing_prefs(self):
        self.client.force_login(self.user)
        self.client.post(reverse("dashboard:legal_center"),
                         {"action": "cookies", "analytics": "on"})
        self.assertTrue(service.cookie_allowed("analytics", user=self.user))
        self.assertFalse(service.cookie_allowed("marketing", user=self.user))
        self.client.post(reverse("dashboard:legal_center"),
                         {"action": "marketing", "opted_in": "on"})
        self.assertTrue(service.marketing_opted_in(self.user))
        html = self.client.get(reverse("dashboard:legal_center")).content.decode()
        self.assertIn("Cookie &amp; marketing preferences", html)
