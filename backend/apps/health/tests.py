"""Project Health Score (spec §30): composed READ-ONLY from real ledgers. A new
project with no signal scores None (never a fabricated 100); each pillar reflects
the latest recorded fact; details are customer-safe."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.health.score import health_score
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class HealthScoreTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def _pillar(self, data, key):
        return next(p for p in data["pillars"] if p["key"] == key)

    def test_new_project_has_no_fabricated_score(self):
        data = health_score(self.project)
        # Nothing scanned/tested/accepted/deployed yet -> honestly unmeasurable,
        # except incidents (none open is genuinely good).
        self.assertEqual(data["measured"], 1)   # only the incidents pillar
        self.assertEqual(data["score"], 100)    # that one pillar is good
        self.assertEqual(self._pillar(data, "security")["status"], "unknown")
        self.assertEqual(self._pillar(data, "tests")["status"], "unknown")
        self.assertEqual(self._pillar(data, "acceptance")["status"], "unknown")

    def test_high_severity_security_drags_health_down(self):
        from apps.security import ledger
        ledger.run_scan(self.project,
                        collector=lambda pr: {"app.py": 'import os\nos.system("x")\n'})
        data = health_score(self.project)
        sec = self._pillar(data, "security")
        self.assertEqual(sec["status"], "poor")
        self.assertEqual(sec["score"], 0)
        self.assertIn(sec, data["attention"])

    def test_failing_tests_are_poor(self):
        from apps.testing.models import TestRun, TestRunStatus
        TestRun.objects.create(project=self.project, status=TestRunStatus.FAILED,
                               ran=10, failures=3)
        data = health_score(self.project)
        self.assertEqual(self._pillar(data, "tests")["status"], "poor")

    def test_accepted_criteria_are_good(self):
        from apps.acceptance import service as acc
        from apps.acceptance.models import CriterionStatus
        c = acc.add(self.project, "A criterion")
        acc.verify(c, CriterionStatus.MET)
        data = health_score(self.project)
        self.assertEqual(self._pillar(data, "acceptance")["status"], "good")

    def test_open_critical_incident_is_poor(self):
        from apps.incidents import service as inc
        inc.open_incident(self.project, title="Down", severity="critical")
        data = health_score(self.project)
        self.assertEqual(self._pillar(data, "incidents")["status"], "poor")

    def test_customer_safe_no_paths_or_stack(self):
        from apps.security import ledger
        ledger.run_scan(self.project,
                        collector=lambda pr: {"secrets.py": "AWS_KEY='AKIA...'\n"})
        blob = str(health_score(self.project))
        self.assertNotIn("secrets.py", blob)   # no file paths leak
        self.assertNotIn(".py", blob)


class HealthApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_endpoint(self):
        resp = self.client.get(
            reverse("health:score", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("pillars", resp.json())
        self.assertIn("band", resp.json())

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("health:score", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
