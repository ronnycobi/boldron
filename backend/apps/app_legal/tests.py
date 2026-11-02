"""Application legal analysis + generator (spec §62-68): honest heuristics over
real project config that never claim compliance, a consistency check that flags
gaps, change triggers, and generated DRAFTS that always carry the counsel
disclaimer."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.app_legal import analysis
from apps.app_legal.generator import DISCLAIMER, generate, GeneratorError
from apps.app_legal.models import GeneratedLegalDoc
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ScanTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")

    def test_detects_financial_and_personal_from_capabilities(self):
        p = Project.objects.create(organization=self.org, name="Shop",
                                   capabilities=["ecommerce", "payments", "crm"])
        cats = [d["category"] for d in analysis.scan_data_types(p)]
        self.assertIn("financial data", cats)
        self.assertIn("personal information", cats)

    def test_detects_health_and_location_from_description(self):
        p = Project.objects.create(organization=self.org, name="Clinic",
                                   description="a medical patient app with gps delivery tracking")
        cats = [d["category"] for d in analysis.scan_data_types(p)]
        self.assertIn("health information", cats)
        self.assertIn("location data", cats)

    def test_clean_app_has_no_sensitive_signals(self):
        p = Project.objects.create(organization=self.org, name="Calc",
                                   description="a simple calculator", capabilities=["database"])
        self.assertEqual(analysis.scan_data_types(p), [])


class ConsistencyAndCheckTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(
            organization=self.org, name="Store",
            capabilities=["ecommerce", "payments", "analytics"])

    def test_consistency_flags_missing_docs(self):
        findings = analysis.consistency_findings(self.project)
        self.assertTrue(findings)
        self.assertTrue(all(f["level"] == "review_required" for f in findings))

    def test_generating_docs_resolves_findings(self):
        for t in ("privacy_policy", "terms_of_service", "cookie_policy", "refund_policy"):
            generate(self.project, t)
        remaining = analysis.consistency_findings(self.project)
        self.assertEqual(remaining, [])

    def test_compliance_check_never_says_compliant(self):
        check = analysis.compliance_check(self.project)
        self.assertNotEqual(check["verdict"], "compliant")
        self.assertIn(check["verdict"], ("review_required", "warning", "no_issues_detected"))
        self.assertNotIn("compliant", check["note"].lower().replace("compliance", ""))

    def test_review_triggers_map_changes(self):
        self.assertIn("ai_terms", analysis.review_triggers("add an AI chatbot"))
        self.assertIn("cookie_policy", analysis.review_triggers("integrate Google Analytics"))
        self.assertEqual(analysis.review_triggers("rename a button"), [])


class GeneratorTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="Store",
                                              capabilities=["ecommerce", "payments"])

    def test_generated_doc_carries_disclaimer(self):
        doc = generate(self.project, "privacy_policy")
        self.assertTrue(doc.content.startswith(DISCLAIMER))
        self.assertFalse(doc.reviewed)

    def test_privacy_policy_reflects_real_features_only(self):
        doc = generate(self.project, "privacy_policy")
        self.assertIn("Payments", doc.content)       # app has payments
        self.assertNotIn("Analytics", doc.content)   # app has no analytics -> not claimed

    def test_cannot_generate_unknown_type(self):
        with self.assertRaises(GeneratorError):
            generate(self.project, "sla")


class AppLegalApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="Store",
                                              capabilities=["ecommerce", "payments"])

    def test_overview_and_generate(self):
        ov = self.client.get(reverse("app_legal:overview", args=[self.project.id]),
                             **auth(self.owner)).json()
        self.assertIn("data_types", ov)
        self.assertIn("compliance", ov)
        gen = self.client.post(reverse("app_legal:generate", args=[self.project.id]),
                               {"doc_type": "privacy_policy"},
                               content_type="application/json", **auth(self.owner))
        self.assertEqual(gen.status_code, 201)
        self.assertTrue(gen.json()["content"].startswith(DISCLAIMER))

    def test_non_member_blocked(self):
        resp = self.client.get(reverse("app_legal:overview", args=[self.project.id]),
                               **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_generate(self):
        resp = self.client.post(reverse("app_legal:generate", args=[self.project.id]),
                                {"doc_type": "privacy_policy"},
                                content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(GeneratedLegalDoc.objects.count(), 0)


class AppLegalWebTests(TestCase):
    def setUp(self):
        from apps.organizations.models import Role
        self.owner = User.objects.create_user(email="w@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="Store",
                                              capabilities=["ecommerce", "payments", "analytics"])

    def test_page_renders_and_generates(self):
        self.client.force_login(self.owner)
        html = self.client.get(
            reverse("dashboard:project_app_legal", args=[self.project.id])).content.decode()
        self.assertIn("Legal &amp; privacy", html)
        self.assertIn("Pre-launch check", html)
        self.assertNotIn("legally compliant", html.lower())
        self.client.post(reverse("dashboard:project_app_legal", args=[self.project.id]),
                         {"doc_type": "privacy_policy"})
        self.assertTrue(GeneratedLegalDoc.objects.filter(
            project=self.project, doc_type="privacy_policy").exists())
