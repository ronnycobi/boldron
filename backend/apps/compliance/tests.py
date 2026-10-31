"""Compliance (spec §16): controls per framework with HONEST status — platform-
provided controls are auto-evidenced from real facts; everything else starts
pending and needs a human attestation with evidence. Never auto-claimed met."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.compliance import service
from apps.compliance.models import ComplianceControl, ControlStatus, Framework
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ComplianceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_seed_auto_evidences_platform_controls_only(self):
        service.seed_framework(self.project, Framework.GDPR)
        export = self.project.compliance_controls.get(
            framework=Framework.GDPR, code="data_export")
        privacy = self.project.compliance_controls.get(
            framework=Framework.GDPR, code="privacy_policy")
        # platform-provided control -> auto-met with real evidence
        self.assertEqual(export.status, ControlStatus.MET)
        self.assertTrue(export.auto)
        self.assertTrue(export.evidence)
        # manual control -> pending, not auto (never optimistically met)
        self.assertEqual(privacy.status, ControlStatus.PENDING)
        self.assertFalse(privacy.auto)

    def test_seed_is_idempotent(self):
        self.assertTrue(service.seed_framework(self.project, Framework.POPIA) > 0)
        self.assertEqual(service.seed_framework(self.project, Framework.POPIA), 0)

    def test_backups_control_reflects_real_capability(self):
        service.seed_framework(self.project, Framework.SECURITY)
        backups = self.project.compliance_controls.get(
            framework=Framework.SECURITY, code="backups")
        self.assertEqual(backups.status, ControlStatus.PENDING)   # no backups capability
        self.project.capabilities = ["backups"]
        self.project.save()
        service.refresh_auto(self.project)
        backups.refresh_from_db()
        self.assertEqual(backups.status, ControlStatus.MET)

    def test_attest_requires_evidence_for_met(self):
        service.seed_framework(self.project, Framework.GDPR)
        privacy = self.project.compliance_controls.get(code="privacy_policy", framework="gdpr")
        with self.assertRaises(service.ComplianceError):
            service.attest(privacy, ControlStatus.MET, evidence="", user=self.user)
        service.attest(privacy, ControlStatus.MET, evidence="Published at /privacy", user=self.user)
        privacy.refresh_from_db()
        self.assertEqual(privacy.status, ControlStatus.MET)
        self.assertFalse(privacy.auto)
        self.assertEqual(privacy.attested_by, self.user)

    def test_score_excludes_not_applicable_and_is_honest(self):
        service.seed_framework(self.project, Framework.ACCESSIBILITY)
        controls = list(self.project.compliance_controls.all())
        # mark one met (with evidence), one N/A
        service.attest(controls[0], ControlStatus.MET, evidence="checked", user=self.user)
        service.attest(controls[1], ControlStatus.NOT_APPLICABLE, user=self.user)
        s = service.score(self.project)
        fw = next(f for f in s["frameworks"] if f["framework"] == "accessibility")
        self.assertEqual(fw["applicable"], len(controls) - 1)   # N/A excluded
        self.assertEqual(fw["met"], 1)
        self.assertNotEqual(fw["percent"], 100)                 # never inflated


class ComplianceApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_seed_then_overview(self):
        resp = self.client.post(
            reverse("compliance:seed", args=[self.project.id]),
            {"framework": "gdpr"}, content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["created"] > 0)
        ov = self.client.get(
            reverse("compliance:overview", args=[self.project.id]), **auth(self.owner)).json()
        self.assertTrue(ov["controls"])
        self.assertIn("frameworks", ov["score"])

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("compliance:overview", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_seed(self):
        resp = self.client.post(
            reverse("compliance:seed", args=[self.project.id]), {"framework": "gdpr"},
            content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(ComplianceControl.objects.count(), 0)
