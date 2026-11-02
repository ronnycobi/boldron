"""Legal & Compliance engine (spec §1-4, §46, §52, §78).

The keystone guarantees: published documents are immutable (a change is a new
version), acceptance is a durable VERSIONED record (never a boolean), drafts are
never exposed to customers, changing a mandatory document re-prompts acceptance,
authoring is staff-only, and a user only sees their own acceptances.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.legal import service
from apps.legal.models import DocumentStatus, LegalAcceptance, LegalDocument
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


def _publish(document_type="terms_of_service", version="1.0", content="Terms v1",
             requires_acceptance=True, user=None):
    doc = service.create_draft(document_type=document_type, title="Terms", version=version,
                               content=content, requires_acceptance=requires_acceptance,
                               user=user)
    service.approve(doc, user=user)
    return service.publish(doc, user=user)


class DocumentLifecycleTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)

    def test_publish_freezes_content_and_hash(self):
        doc = _publish(user=self.staff)
        self.assertEqual(doc.status, DocumentStatus.PUBLISHED)
        self.assertTrue(doc.content_sha256)
        self.assertIsNotNone(doc.published_at)

    def test_published_document_is_immutable(self):
        doc = _publish(user=self.staff)
        doc.content = "tampered"
        with self.assertRaises(ValueError):
            doc.save()

    def test_cannot_edit_a_frozen_document_via_service(self):
        doc = _publish(user=self.staff)
        with self.assertRaises(service.LegalError):
            service.update_draft(doc, content="new", user=self.staff)

    def test_new_version_supersedes_prior_and_keeps_history(self):
        v1 = _publish(version="1.0", content="v1", user=self.staff)
        v2 = _publish(version="2.0", content="v2", user=self.staff)
        v1.refresh_from_db()
        self.assertEqual(v1.status, DocumentStatus.SUPERSEDED)
        self.assertEqual(service.current("terms_of_service"), v2)
        # both versions remain retrievable (history preserved)
        self.assertEqual(service.versions("terms_of_service").count(), 2)

    def test_must_be_approved_before_publish(self):
        doc = service.create_draft(document_type="privacy_policy", title="P",
                                   version="1.0", content="x", user=self.staff)
        with self.assertRaises(service.LegalError):
            service.publish(doc, user=self.staff)

    def test_refuses_empty_publish(self):
        doc = service.create_draft(document_type="privacy_policy", title="P",
                                   version="1.0", content="", user=self.staff)
        service.approve(doc, user=self.staff)
        with self.assertRaises(service.LegalError):
            service.publish(doc, user=self.staff)

    def test_unknown_type_rejected(self):
        with self.assertRaises(service.LegalError):
            service.create_draft(document_type="not_a_doc", title="x", version="1.0")

    def test_jurisdiction_falls_back_to_global(self):
        _publish(user=self.staff)   # global terms
        self.assertIsNotNone(service.current("terms_of_service", jurisdiction="south_africa"))


class AcceptanceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_acceptance_is_a_versioned_record_not_a_boolean(self):
        doc = _publish(user=self.staff)
        acc = service.record_acceptance(self.user, doc, method="signup",
                                        ip_address="203.0.113.5", user_agent="UA/1.0")
        self.assertEqual(acc.version, "1.0")
        self.assertEqual(acc.content_sha256, doc.content_sha256)
        self.assertEqual(acc.ip_address, "203.0.113.5")
        self.assertTrue(acc.mandatory)

    def test_acceptance_is_idempotent_per_version(self):
        doc = _publish(user=self.staff)
        service.record_acceptance(self.user, doc)
        service.record_acceptance(self.user, doc)
        self.assertEqual(LegalAcceptance.objects.filter(user=self.user).count(), 1)

    def test_cannot_accept_a_draft(self):
        doc = service.create_draft(document_type="ai_terms", title="AI", version="1.0",
                                   content="x", user=self.staff)
        with self.assertRaises(service.LegalError):
            service.record_acceptance(self.user, doc)

    def test_changed_mandatory_document_reprompts(self):
        v1 = _publish(version="1.0", user=self.staff)
        service.record_acceptance(self.user, v1)
        self.assertEqual(service.pending_acceptances(self.user), [])
        # a new mandatory version supersedes -> acceptance of v1 no longer counts
        v2 = _publish(version="2.0", user=self.staff)
        pending = service.pending_acceptances(self.user)
        self.assertEqual([d.id for d in pending], [v2.id])

    def test_optional_document_not_in_pending(self):
        _publish(document_type="beta_terms", requires_acceptance=False, user=self.staff)
        self.assertEqual(service.pending_acceptances(self.user), [])


class LegalApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.other = User.objects.create_user(email="o@x.com", password="pw12345!")

    def test_public_sees_only_published(self):
        _publish(user=self.staff)
        service.create_draft(document_type="privacy_policy", title="P", version="1.0",
                             content="secret draft", user=self.staff)
        resp = self.client.get(reverse("legal:documents"))   # unauthenticated
        self.assertEqual(resp.status_code, 200)
        types = [d["document_type"] for d in resp.json()["documents"]]
        self.assertIn("terms_of_service", types)
        self.assertNotIn("privacy_policy", types)   # draft hidden

    def test_draft_detail_is_not_exposed(self):
        draft = service.create_draft(document_type="privacy_policy", title="P",
                                     version="1.0", content="secret", user=self.staff)
        resp = self.client.get(reverse("legal:document", args=[draft.slug]))
        self.assertIn(resp.status_code, (403, 404))

    def test_accept_via_api_captures_ip(self):
        doc = _publish(user=self.staff)
        resp = self.client.post(
            reverse("legal:acceptances"), {"document": doc.slug, "method": "clickwrap"},
            content_type="application/json", REMOTE_ADDR="198.51.100.9", **auth(self.user))
        self.assertEqual(resp.status_code, 201)
        acc = LegalAcceptance.objects.get(user=self.user, document=doc)
        self.assertEqual(acc.ip_address, "198.51.100.9")

    def test_user_sees_only_own_acceptances(self):
        doc = _publish(user=self.staff)
        service.record_acceptance(self.user, doc)
        resp = self.client.get(reverse("legal:acceptances"), **auth(self.other))
        self.assertEqual(resp.json()["acceptances"], [])

    def test_authoring_is_staff_only(self):
        resp = self.client.post(
            reverse("legal:admin_documents"),
            {"document_type": "terms_of_service", "title": "T", "version": "1.0"},
            content_type="application/json", **auth(self.user))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(LegalDocument.objects.count(), 0)

    def test_staff_can_author_and_publish_via_api(self):
        create = self.client.post(
            reverse("legal:admin_documents"),
            {"document_type": "terms_of_service", "title": "T", "version": "1.0",
             "content": "Hello", "requires_acceptance": True},
            content_type="application/json", **auth(self.staff))
        self.assertEqual(create.status_code, 201)
        doc_id = create.json()["id"]
        for action in ("approve", "publish"):
            r = self.client.post(reverse("legal:admin_action", args=[doc_id]),
                                 {"action": action}, content_type="application/json",
                                 **auth(self.staff))
            self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "published")


class LegalWebSurfaceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_staff_console_legal_create_and_publish(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("console:legal"), {
            "action": "create", "document_type": "terms_of_service",
            "jurisdiction": "global", "title": "Terms", "version": "1.0",
            "content": "Hello terms", "requires_acceptance": "on"})
        doc = LegalDocument.objects.get(document_type="terms_of_service")
        self.client.post(reverse("console:legal"), {"action": "approve", "document": doc.id})
        self.client.post(reverse("console:legal"), {"action": "publish", "document": doc.id})
        doc.refresh_from_db()
        self.assertEqual(doc.status, DocumentStatus.PUBLISHED)

    def test_console_legal_is_staff_only(self):
        self.client.force_login(self.user)   # non-staff
        resp = self.client.get(reverse("console:legal"))
        self.assertIn(resp.status_code, (302, 403))

    def test_customer_legal_center_shows_docs_and_accept(self):
        _publish(user=self.staff)
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard:legal_center")).content.decode()
        self.assertIn("Legal", html)
        self.assertIn("Action needed", html)   # pending acceptance surfaced
        # accept via the page
        doc = LegalDocument.objects.get(document_type="terms_of_service")
        self.client.post(reverse("dashboard:legal_center"),
                         {"action": "accept", "document": doc.slug})
        self.assertTrue(LegalAcceptance.objects.filter(user=self.user, document=doc).exists())


class JurisdictionAndLawRequestTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")

    def test_jurisdiction_notices_unconfigured_is_honest(self):
        notices = service.jurisdiction_notices("south_africa")
        self.assertFalse(notices["configured"])   # no auto legal conclusion

    def test_configure_jurisdiction(self):
        service.set_jurisdiction_config("south_africa", consent_required=True,
                                        additional_notices="POPIA applies.", user=self.staff)
        notices = service.jurisdiction_notices("south_africa")
        self.assertTrue(notices["configured"])
        self.assertTrue(notices["consent_required"])
        self.assertIn("POPIA", notices["additional_notices"])

    def test_unknown_jurisdiction_rejected(self):
        with self.assertRaises(service.LegalError):
            service.set_jurisdiction_config("narnia", user=self.staff)

    def test_jurisdiction_api_is_public(self):
        service.set_jurisdiction_config("eu_eea", cookie_consent_required=True, user=self.staff)
        resp = self.client.get(reverse("legal:jurisdiction", args=["eu_eea"]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["cookie_consent_required"])

    def test_law_request_starts_pending_and_undisclosed(self):
        req = service.log_law_request(authority="Court X", request_type="subpoena",
                                      user=self.staff)
        self.assertEqual(req.decision, "pending")
        self.assertFalse(req.disclosed)   # never auto-disclosed

    def test_law_request_review_is_explicit(self):
        req = service.log_law_request(authority="Court X", user=self.staff)
        service.review_law_request(req, "rejected", disclosed=False,
                                   note="No valid basis", user=self.staff)
        req.refresh_from_db()
        self.assertEqual(req.decision, "rejected")
        self.assertFalse(req.disclosed)

    def test_law_request_api_is_staff_only(self):
        self.assertEqual(
            self.client.get(reverse("legal:law_requests"), **auth(self.user)).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("legal:law_requests"), **auth(self.staff)).status_code, 200)

    def test_console_legal_configures_jurisdiction(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("console:legal"),
                         {"action": "jurisdiction", "jurisdiction": "united_kingdom",
                          "consent_required": "on"})
        from apps.legal.models import JurisdictionConfig
        self.assertTrue(JurisdictionConfig.objects.filter(
            jurisdiction="united_kingdom", consent_required=True).exists())


class BillingTermsLinkageTests(TestCase):
    """Billing/refund/trial terms are surfaced on the billing page from the legal
    engine (single source) — not duplicated (spec §31-34)."""
    def setUp(self):
        self.staff = User.objects.create_user(email="bs@x.com", password="pw12345!", is_staff=True)
        self.user = User.objects.create_user(email="bu@x.com", password="pw12345!")

    def test_usage_page_links_published_billing_terms(self):
        doc = service.create_draft(document_type="billing_terms", title="Billing Terms",
                                   version="1.0", content="Billing terms text", user=self.staff)
        service.approve(doc, user=self.staff)
        service.publish(doc, user=self.staff)
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard:usage")).content.decode()
        self.assertIn("Billing terms", html)
        self.assertIn(doc.slug, html)   # links the real published document
