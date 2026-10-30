"""Operations Center (spec §10): composes real runtime signals into a customer-safe
health view — honest status, no fabricated green, no infrastructure exposed."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.deployments.models import Deployment, DeploymentStatus, DeployEnvironment
from apps.deployments.operations import operations_overview
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class OperationsTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="OpsOrg")
        self.user = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def _deploy(self, status, env=DeployEnvironment.PRODUCTION):
        return Deployment.objects.create(
            project=self.project, environment=env, provider="preview", status=status)

    def test_new_project_is_unknown_not_healthy(self):
        ops = operations_overview(self.project)
        self.assertEqual(ops["status"], "unknown")      # nothing deployed → honest unknown
        self.assertIsNone(ops["uptime"])
        self.assertIsNone(ops["traffic"])

    def test_successful_deploy_reads_healthy(self):
        self._deploy(DeploymentStatus.SUCCEEDED)
        ops = operations_overview(self.project)
        self.assertEqual(ops["status"], "healthy")
        self.assertEqual(ops["deployments"]["latest_status"], "succeeded")
        self.assertEqual(ops["deployments"]["total"], 1)

    def test_failed_deploy_is_degraded(self):
        self._deploy(DeploymentStatus.SUCCEEDED)
        self._deploy(DeploymentStatus.FAILED)   # newer
        ops = operations_overview(self.project)
        self.assertEqual(ops["status"], "degraded")

    def test_failed_job_degrades_status(self):
        from apps.jobs.models import Job
        self._deploy(DeploymentStatus.SUCCEEDED)
        Job.objects.create(organization=self.org, project=self.project,
                           kind="k", label="L", status=Job.FAILED)
        ops = operations_overview(self.project)
        self.assertEqual(ops["status"], "degraded")
        self.assertEqual(ops["jobs"]["failed"], 1)

    def test_high_security_finding_degrades_and_blocks(self):
        from apps.security import ledger
        self._deploy(DeploymentStatus.SUCCEEDED)
        ledger.run_scan(self.project,
                        collector=lambda p: {"a.py": 'import os\nos.system(x)\n'})
        ops = operations_overview(self.project)
        self.assertEqual(ops["status"], "degraded")
        self.assertTrue(ops["quality"]["security_blocks"])
        self.assertEqual(ops["quality"]["security"], "blocked")

    def test_storage_sums_real_file_sizes(self):
        from apps.files.models import StoredFile
        StoredFile.objects.create(organization=self.org, project=self.project,
                                  file="x", size=2048)
        ops = operations_overview(self.project)
        self.assertEqual(ops["storage"]["bytes"], 2048)
        self.assertEqual(ops["storage"]["display"], "2.0 KB")

    def test_rollback_restore_points(self):
        from apps.backups.models import ProjectBackup
        ProjectBackup.objects.create(project=self.project, label="before", commit_sha="abc")
        ops = operations_overview(self.project)
        self.assertEqual(ops["rollback"]["restore_points"], 1)
        self.assertTrue(ops["rollback"]["available"])

    def test_no_infrastructure_detail_is_exposed(self):
        self._deploy(DeploymentStatus.SUCCEEDED)
        blob = str(operations_overview(self.project)).lower()
        for leak in ("docker", "container", "/var/", "localhost", "postgres", "traceback"):
            self.assertNotIn(leak, blob)


class OperationsApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="oo@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="ox@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="OpsApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_endpoint_returns_overview(self):
        resp = self.client.get(
            reverse("deployments:operations", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("status", resp.json())
        self.assertIn("jobs", resp.json())

    def test_tenant_isolation(self):
        resp = self.client.get(
            reverse("deployments:operations", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
