"""Acceptance criteria (spec §3): trackable, verifiable, and HONEST — the AI
never marks a criterion met; "accepted" is only reported with real evidence."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.acceptance import service
from apps.acceptance.models import AcceptanceCriterion, CriterionStatus
from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ImportTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")
        self.ctx = ProjectContext(self.project)

    def test_imports_embedded_criteria_as_pending_records(self):
        self.ctx.add(ContextKind.REQUIREMENT, title="Checkout",
                     content="Customers can pay.",
                     data={"acceptance_criteria": [
                         "Card payment succeeds", "Receipt is emailed"]})
        created = service.import_from_requirements(self.project)
        self.assertEqual(created, 2)
        crits = self.project.acceptance_criteria.all()
        self.assertEqual(crits.count(), 2)
        # Imported criteria are PENDING — never auto-marked met.
        self.assertTrue(all(c.status == CriterionStatus.PENDING for c in crits))
        self.assertTrue(all(c.requirement_id for c in crits))

    def test_import_is_idempotent(self):
        self.ctx.add(ContextKind.REQUIREMENT, title="Login",
                     content="Users sign in.",
                     data={"acceptance_criteria": ["Valid creds log in"]})
        self.assertEqual(service.import_from_requirements(self.project), 1)
        self.assertEqual(service.import_from_requirements(self.project), 0)
        self.assertEqual(self.project.acceptance_criteria.count(), 1)


class VerifyAndSummaryTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def _crit(self):
        return service.add(self.project, "A criterion", user=self.user)

    def test_verify_met_stamps_who_and_when(self):
        c = self._crit()
        service.verify(c, CriterionStatus.MET, user=self.user, note="checked")
        c.refresh_from_db()
        self.assertEqual(c.status, CriterionStatus.MET)
        self.assertEqual(c.verified_by, self.user)
        self.assertIsNotNone(c.verified_at)

    def test_back_to_pending_clears_provenance(self):
        c = self._crit()
        service.verify(c, CriterionStatus.MET, user=self.user)
        service.verify(c, CriterionStatus.PENDING, user=self.user)
        c.refresh_from_db()
        self.assertIsNone(c.verified_by)
        self.assertIsNone(c.verified_at)

    def test_unknown_status_rejected(self):
        c = self._crit()
        with self.assertRaises(service.AcceptanceError):
            service.verify(c, "approved", user=self.user)

    def test_accepted_only_when_all_resolved_and_one_met(self):
        a = service.add(self.project, "a")
        b = service.add(self.project, "b")
        # pending => not accepted
        self.assertFalse(service.summary(self.project)["accepted"])
        service.verify(a, CriterionStatus.MET, user=self.user)
        # one still pending => not accepted
        self.assertFalse(service.summary(self.project)["accepted"])
        service.verify(b, CriterionStatus.MET, user=self.user)
        s = service.summary(self.project)
        self.assertTrue(s["accepted"])
        self.assertEqual(s["met"], 2)
        self.assertEqual(s["met_pct"], 100)

    def test_a_failed_criterion_blocks_acceptance(self):
        a = service.add(self.project, "a")
        b = service.add(self.project, "b")
        service.verify(a, CriterionStatus.MET, user=self.user)
        service.verify(b, CriterionStatus.FAILED, user=self.user)
        self.assertFalse(service.summary(self.project)["accepted"])

    def test_all_waived_is_not_accepted(self):
        a = service.add(self.project, "a")
        service.verify(a, CriterionStatus.WAIVED, user=self.user)
        # nothing actually met => honest "not accepted"
        self.assertFalse(service.summary(self.project)["accepted"])

    def test_empty_project_not_accepted(self):
        self.assertFalse(service.summary(self.project)["accepted"])


class AcceptanceApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")
        ProjectContext(self.project).add(
            ContextKind.REQUIREMENT, title="Checkout", content="Pay",
            data={"acceptance_criteria": ["Card payment succeeds"]})

    def test_import_then_list(self):
        resp = self.client.post(
            reverse("acceptance:import", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["imported"], 1)
        listing = self.client.get(
            reverse("acceptance:list", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["criteria"]), 1)
        self.assertFalse(listing.json()["summary"]["accepted"])

    def test_verify_via_api(self):
        service.import_from_requirements(self.project)
        crit = self.project.acceptance_criteria.first()
        resp = self.client.post(
            reverse("acceptance:verify", args=[crit.id]),
            {"status": "met", "note": "done"}, **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "met")
        self.assertEqual(resp.json()["verified_by"], "o@x.com")

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("acceptance:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_verify(self):
        service.import_from_requirements(self.project)
        crit = self.project.acceptance_criteria.first()
        resp = self.client.post(
            reverse("acceptance:verify", args=[crit.id]),
            {"status": "met"}, **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        crit.refresh_from_db()
        self.assertEqual(crit.status, CriterionStatus.PENDING)
