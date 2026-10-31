"""Localization / i18n (spec §17-18): real locales + strings + translations, with
HONEST coverage and fallback-flagged bundles — a missing translation is never
shown as translated."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.localization import service
from apps.localization.models import ProjectLocale, Translation
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class LocalizationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_first_locale_becomes_default(self):
        en = service.add_locale(self.project, code="en")
        self.assertTrue(en.is_default)
        fr = service.add_locale(self.project, code="fr")
        self.assertFalse(fr.is_default)
        self.assertEqual(service.default_code(self.project), "en")

    def test_rtl_detected(self):
        ar = service.add_locale(self.project, code="ar")
        self.assertTrue(ar.rtl)
        self.assertFalse(service.add_locale(self.project, code="fr").rtl)

    def test_coverage_counts_real_translations_only(self):
        service.add_locale(self.project, code="en")
        service.add_locale(self.project, code="fr")
        a = service.add_string(self.project, key="greeting", source_text="Hello")
        service.add_string(self.project, key="bye", source_text="Goodbye")
        service.set_translation(a, "fr", "Bonjour")
        cov = {c["code"]: c for c in service.coverage(self.project)}
        self.assertEqual(cov["fr"]["translated"], 1)
        self.assertEqual(cov["fr"]["total"], 2)
        self.assertEqual(cov["fr"]["percent"], 50)

    def test_bundle_flags_fallbacks_and_never_fakes(self):
        service.add_locale(self.project, code="en")
        service.add_locale(self.project, code="fr")
        a = service.add_string(self.project, key="greeting", source_text="Hello")
        service.add_string(self.project, key="bye", source_text="Goodbye")
        service.set_translation(a, "fr", "Bonjour")
        b = service.bundle(self.project, "fr")
        self.assertEqual(b["strings"]["greeting"], {"value": "Bonjour", "fallback": False})
        # untranslated -> falls back to source AND is flagged, never shown as translated
        self.assertEqual(b["strings"]["bye"], {"value": "Goodbye", "fallback": True})
        self.assertIn("bye", b["missing"])
        self.assertFalse(b["complete"])

    def test_default_bundle_is_source(self):
        service.add_locale(self.project, code="en")
        service.add_string(self.project, key="k", source_text="Hi")
        b = service.bundle(self.project, "en")
        self.assertTrue(b["is_default"])
        self.assertFalse(b["strings"]["k"]["fallback"])

    def test_cannot_translate_into_default_locale(self):
        service.add_locale(self.project, code="en")
        s = service.add_string(self.project, key="k", source_text="Hi")
        with self.assertRaises(service.LocalizationError):
            service.set_translation(s, "en", "x")

    def test_clearing_translation_returns_to_missing(self):
        service.add_locale(self.project, code="en")
        service.add_locale(self.project, code="fr")
        s = service.add_string(self.project, key="k", source_text="Hi")
        service.set_translation(s, "fr", "Salut")
        service.set_translation(s, "fr", "")   # cleared
        self.assertIn("k", service.bundle(self.project, "fr")["missing"])

    def test_duplicate_locale_and_key_rejected(self):
        service.add_locale(self.project, code="en")
        with self.assertRaises(service.LocalizationError):
            service.add_locale(self.project, code="en")
        service.add_string(self.project, key="k", source_text="a")
        with self.assertRaises(service.LocalizationError):
            service.add_string(self.project, key="k", source_text="b")


class LocalizationApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_add_locale_string_translate_and_bundle(self):
        self.client.post(reverse("localization:locales", args=[self.project.id]),
                         {"code": "en"}, content_type="application/json", **auth(self.owner))
        self.client.post(reverse("localization:locales", args=[self.project.id]),
                         {"code": "fr"}, content_type="application/json", **auth(self.owner))
        s = self.client.post(reverse("localization:strings", args=[self.project.id]),
                             {"key": "hi", "source_text": "Hello"},
                             content_type="application/json", **auth(self.owner)).json()
        self.client.post(reverse("localization:translate", args=[self.project.id]),
                         {"string": s["id"], "locale": "fr", "value": "Bonjour"},
                         content_type="application/json", **auth(self.owner))
        bundle = self.client.get(
            reverse("localization:bundle", args=[self.project.id]) + "?locale=fr",
            **auth(self.owner)).json()
        self.assertEqual(bundle["strings"]["hi"]["value"], "Bonjour")

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("localization:overview", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_add_locale(self):
        resp = self.client.post(
            reverse("localization:locales", args=[self.project.id]), {"code": "fr"},
            content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(ProjectLocale.objects.count(), 0)
