"""AI debugging engine (spec §7): diagnose a real failure, propose a fix as a
reviewed change — never claim the error is fixed."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.testing import runner
from apps.testing.debug import analyze_failure, propose_fix
from apps.testing.models import TestRun, TestRunStatus

User = get_user_model()

_FAIL_LOG = """\
test_checkout (store.tests.CheckoutTests) ... FAIL

======================================================================
FAIL: test_checkout (store.tests.CheckoutTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/sandbox/wd/store/tests.py", line 42, in test_checkout
    self.assertEqual(order.total, 100)
AssertionError: 90 != 100

Ran 12 tests in 0.3s
FAILED (failures=1)
"""


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


def _failing(project):
    return {"passed": False, "ran": 12, "failures": 1, "errors": 0, "output": _FAIL_LOG}


class FailureAnalysisTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="DbgOrg")
        self.user = User.objects.create_user(email="d@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def _failed_run(self):
        return runner.run_project_tests(self.project, executor=_failing, user=self.user)

    def test_failure_log_is_captured(self):
        run = self._failed_run()
        self.assertEqual(run.status, TestRunStatus.FAILED)
        self.assertIn("AssertionError", run.log)

    def test_analysis_extracts_root_cause_from_the_real_log(self):
        d = analyze_failure(self._failed_run())
        self.assertEqual(d["category"], "assertion")
        self.assertEqual(d["exception"], "AssertionError")
        self.assertIn("test_checkout", d["failing_tests"])
        # Location is reduced to the file NAME (customer-safe — no sandbox path).
        self.assertEqual(d["location"], "tests.py:42")
        self.assertNotIn("/sandbox/", str(d))

    def test_analysis_is_none_for_a_non_failed_run(self):
        passing = runner.run_project_tests(
            self.project, executor=lambda p: {"passed": True, "ran": 3})
        self.assertIsNone(analyze_failure(passing))

    def test_propose_fix_creates_a_reviewed_change_not_a_fix(self):
        run = self._failed_run()
        change = propose_fix(run, user=self.user)
        self.assertEqual(change.project_id, self.project.id)
        self.assertIn("failing", change.description.lower())
        # The run is NOT marked fixed/passed — only a change was proposed.
        run.refresh_from_db()
        self.assertEqual(run.status, TestRunStatus.FAILED)
        self.assertEqual(run.change_id, change.id)   # linked for traceability
        # And a fresh run is what would decide success — not propose_fix.
        self.assertFalse(runner.tests_green(self.project))

    def test_cannot_propose_fix_for_a_passing_run(self):
        passing = runner.run_project_tests(
            self.project, executor=lambda p: {"passed": True, "ran": 3})
        with self.assertRaises(ValueError):
            propose_fix(passing, user=self.user)


class DebugApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="do@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="dm@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="DbgApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_get_includes_diagnosis_for_a_failed_latest(self):
        runner.run_project_tests(self.project, executor=_failing)
        resp = self.client.get(
            reverse("testing_api:tests", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["diagnosis"]["exception"], "AssertionError")

    def test_propose_fix_endpoint_creates_change(self):
        run = runner.run_project_tests(self.project, executor=_failing)
        resp = self.client.post(
            reverse("testing_api:test-fix", args=[self.project.id, run.id]),
            **auth(self.owner))
        self.assertEqual(resp.status_code, 201)
        self.assertIn("change", resp.json())

    def test_member_cannot_propose_fix(self):
        run = runner.run_project_tests(self.project, executor=_failing)
        resp = self.client.post(
            reverse("testing_api:test-fix", args=[self.project.id, run.id]),
            **auth(self.member))
        self.assertEqual(resp.status_code, 403)
