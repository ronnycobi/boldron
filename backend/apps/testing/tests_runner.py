"""Test-run ledger (spec §8): records REAL outcomes, never fakes a pass, and the
deploy gate (tests_green) is honest about skipped / failed / never-run."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.testing import runner
from apps.testing.models import TestRunStatus

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


# Deterministic executors standing in for the real sandbox run.
def _passing(project):
    return {"passed": True, "ran": 12, "failures": 0, "errors": 0}


def _failing(project):
    return {"passed": False, "ran": 10, "failures": 2, "errors": 1}


def _nothing(project):
    return {"passed": None, "ran": 0, "note": "no repository"}


def _boom(project):
    raise RuntimeError("sandbox exploded")


class TestRunLedgerTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="QAOrg")
        self.user = User.objects.create_user(email="q@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_passing_run_is_recorded_green(self):
        run = runner.run_project_tests(self.project, executor=_passing, user=self.user)
        self.assertEqual(run.status, TestRunStatus.PASSED)
        self.assertEqual(run.ran, 12)
        self.assertTrue(run.passed)
        self.assertTrue(runner.tests_green(self.project))
        self.assertIsNotNone(run.finished_at)

    def test_failing_run_is_recorded_and_not_green(self):
        run = runner.run_project_tests(self.project, executor=_failing)
        self.assertEqual(run.status, TestRunStatus.FAILED)
        self.assertEqual(run.failures, 2)
        self.assertFalse(runner.tests_green(self.project))

    def test_nothing_to_run_is_skipped_not_passed(self):
        run = runner.run_project_tests(self.project, executor=_nothing)
        self.assertEqual(run.status, TestRunStatus.SKIPPED)
        self.assertFalse(run.passed)
        self.assertFalse(runner.tests_green(self.project))   # skipped != green

    def test_executor_exception_is_error_not_a_fake_pass(self):
        run = runner.run_project_tests(self.project, executor=_boom)
        self.assertEqual(run.status, TestRunStatus.ERROR)
        self.assertIn("exploded", run.note)
        self.assertFalse(runner.tests_green(self.project))

    def test_gate_reflects_only_the_latest_run(self):
        runner.run_project_tests(self.project, executor=_passing)
        self.assertTrue(runner.tests_green(self.project))
        runner.run_project_tests(self.project, executor=_failing)   # newer, failed
        self.assertFalse(runner.tests_green(self.project))

    def test_no_runs_is_not_green(self):
        self.assertFalse(runner.tests_green(self.project))


class PreDeployGateTests(TestCase):
    """The run_tests hook records a ledger run and blocks on failure."""

    def setUp(self):
        self.org = Organization.objects.create(name="GateOrg")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_failing_tests_block_and_are_recorded(self):
        from apps.hooks import actions
        from unittest import mock
        with mock.patch("apps.codegen.service.run_repo_tests", side_effect=_failing):
            status, detail = actions.run_tests(self.project, {})
        self.assertEqual(status, "fail")
        self.assertEqual(self.project.test_runs.count(), 1)
        self.assertEqual(self.project.test_runs.first().trigger, "pre_deploy")


class TestsApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="to@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="tm@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="tx@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="TApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_history_and_green_flag(self):
        runner.run_project_tests(self.project, executor=_passing)
        resp = self.client.get(
            reverse("testing_api:tests", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["green"])
        self.assertEqual(body["latest"]["status"], "passed")
        self.assertEqual(len(body["runs"]), 1)

    def test_member_cannot_trigger_run(self):
        resp = self.client.post(
            reverse("testing_api:tests", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 403)

    def test_tenant_isolation(self):
        resp = self.client.get(
            reverse("testing_api:tests", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
