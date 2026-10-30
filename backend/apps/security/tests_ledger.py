"""Security-scan ledger (spec §8): records REAL findings, never fakes a clean, and
the deploy gate blocks on high-severity findings."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.security import ledger
from apps.security.models import SecurityScanStatus

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


# Deterministic file collectors standing in for the real repo read.
def _high_risk(project):
    return {"app.py": 'import os\nos.system("rm -rf /")\nAWS = "AKIAIOSFODNN7EXAMPLE"\n'}


def _medium_only(project):
    return {"settings.py": "DEBUG = True\n"}


def _clean(project):
    return {"app.py": "def add(a, b):\n    return a + b\n"}


def _no_code(project):
    return {}


def _no_repo(project):
    return None


class SecurityLedgerTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="SecOrg")
        self.user = User.objects.create_user(email="s@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_high_severity_findings_block(self):
        scan = ledger.run_scan(self.project, collector=_high_risk, user=self.user)
        self.assertEqual(scan.status, SecurityScanStatus.BLOCKED)
        self.assertGreater(scan.high, 0)
        self.assertTrue(scan.blocks_deploy)
        self.assertFalse(ledger.security_ok(self.project))
        # Findings are persisted with real detail.
        self.assertTrue(scan.findings.filter(severity="high").exists())

    def test_medium_only_is_findings_not_blocked_and_ok(self):
        scan = ledger.run_scan(self.project, collector=_medium_only)
        self.assertEqual(scan.status, SecurityScanStatus.FINDINGS)
        self.assertEqual(scan.high, 0)
        self.assertFalse(scan.blocks_deploy)
        self.assertTrue(ledger.security_ok(self.project))   # no HIGH → deploy-ok

    def test_clean_code_is_clean(self):
        scan = ledger.run_scan(self.project, collector=_clean)
        self.assertEqual(scan.status, SecurityScanStatus.CLEAN)
        self.assertEqual(scan.total, 0)
        self.assertTrue(ledger.security_ok(self.project))

    def test_no_code_is_skipped_not_clean(self):
        scan = ledger.run_scan(self.project, collector=_no_code)
        self.assertEqual(scan.status, SecurityScanStatus.SKIPPED)
        self.assertEqual(scan.note, "no code to scan")
        # Skipped is deploy-ok (nothing to block on) but is NOT reported as clean.
        self.assertTrue(ledger.security_ok(self.project))
        self.assertNotEqual(scan.status, SecurityScanStatus.CLEAN)

    def test_no_repo_is_skipped(self):
        scan = ledger.run_scan(self.project, collector=_no_repo)
        self.assertEqual(scan.status, SecurityScanStatus.SKIPPED)
        self.assertEqual(scan.note, "no repository")

    def test_gate_reflects_latest_scan(self):
        ledger.run_scan(self.project, collector=_clean)
        self.assertTrue(ledger.security_ok(self.project))
        ledger.run_scan(self.project, collector=_high_risk)   # newer, high-risk
        self.assertFalse(ledger.security_ok(self.project))

    def test_never_scanned_is_not_ok(self):
        self.assertFalse(ledger.security_ok(self.project))


class PreDeployScanGateTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="SGateOrg")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_high_finding_blocks_and_is_recorded(self):
        from unittest import mock
        from apps.hooks import actions
        with mock.patch("apps.security.ledger._collect_files", side_effect=_high_risk):
            status, detail = actions.security_scan(self.project, {})
        self.assertEqual(status, "fail")
        self.assertEqual(self.project.security_scans.count(), 1)
        self.assertEqual(self.project.security_scans.first().trigger, "pre_deploy")


class SecurityApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="so@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="sm@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="sx@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="SApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_history_and_findings(self):
        ledger.run_scan(self.project, collector=_high_risk)
        resp = self.client.get(
            reverse("security_api:security", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["latest"]["status"], "blocked")
        self.assertTrue(len(body["latest"]["findings"]) > 0)

    def test_member_cannot_run_scan(self):
        resp = self.client.post(
            reverse("security_api:security", args=[self.project.id]), **auth(self.member))
        self.assertEqual(resp.status_code, 403)

    def test_tenant_isolation(self):
        resp = self.client.get(
            reverse("security_api:security", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
