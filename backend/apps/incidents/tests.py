"""Incident management (spec §20): real lifecycle, auto-detection from failed
deploys, and the honesty rule — the AI analyses but never resolves."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.deployments.models import Deployment, DeploymentStatus, DeployEnvironment
from apps.incidents import service
from apps.incidents.models import Incident, IncidentStatus
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class IncidentLifecycleTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="IncOrg")
        self.user = User.objects.create_user(email="i@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_open_records_detection_event(self):
        inc = service.open_incident(self.project, title="Checkout down",
                                    severity="high", detail="500s on /checkout", user=self.user)
        self.assertEqual(inc.status, IncidentStatus.DETECTED)
        self.assertTrue(inc.is_open)
        self.assertEqual(inc.events.count(), 1)
        self.assertEqual(inc.events.first().kind, "detected")

    def test_transition_builds_a_timeline_and_resolving_stamps_time(self):
        inc = service.open_incident(self.project, title="x", user=self.user)
        service.transition(inc, IncidentStatus.INVESTIGATING, user=self.user)
        service.transition(inc, IncidentStatus.RESOLVED, note="rolled back", user=self.user)
        inc.refresh_from_db()
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)
        self.assertIsNotNone(inc.resolved_at)
        self.assertIsNotNone(inc.duration_seconds)
        self.assertFalse(inc.is_open)
        # Timeline: detected + 2 status changes.
        self.assertEqual(inc.events.filter(kind="status").count(), 2)

    def test_reopen_clears_resolution_time(self):
        inc = service.open_incident(self.project, title="x", user=self.user)
        service.transition(inc, IncidentStatus.RESOLVED, user=self.user)
        service.transition(inc, IncidentStatus.INVESTIGATING, user=self.user)
        inc.refresh_from_db()
        self.assertIsNone(inc.resolved_at)
        self.assertTrue(inc.is_open)

    def test_analyze_never_resolves(self):
        inc = service.open_incident(self.project, title="x", user=self.user)
        service.analyze(inc, user=self.user)
        inc.refresh_from_db()
        self.assertEqual(inc.status, IncidentStatus.DETECTED)   # unchanged
        self.assertTrue(inc.is_open)
        ev = inc.events.filter(kind="analysis").first()
        self.assertIsNotNone(ev)
        self.assertIn("until a person resolves", ev.message)

    def test_failed_deploy_auto_opens_an_incident(self):
        dep = Deployment.objects.create(
            project=self.project, environment=DeployEnvironment.PRODUCTION,
            provider="preview", status=DeploymentStatus.FAILED)
        inc = service.auto_detect_from_deploy(dep)
        self.assertIsNotNone(inc)
        self.assertEqual(inc.source, "deploy")
        self.assertEqual(inc.severity, "high")   # production failure
        self.assertEqual(inc.deployment_id, dep.id)

    def test_auto_detect_is_idempotent_while_open(self):
        dep = Deployment.objects.create(
            project=self.project, environment=DeployEnvironment.STAGING,
            provider="preview", status=DeploymentStatus.FAILED)
        a = service.auto_detect_from_deploy(dep)
        b = service.auto_detect_from_deploy(dep)   # already open → same incident
        self.assertEqual(a.id, b.id)
        self.assertEqual(self.project.incidents.count(), 1)

    def test_succeeded_deploy_opens_nothing(self):
        dep = Deployment.objects.create(
            project=self.project, environment=DeployEnvironment.PRODUCTION,
            provider="preview", status=DeploymentStatus.SUCCEEDED)
        self.assertIsNone(service.auto_detect_from_deploy(dep))

    def test_summary_counts_open_and_critical(self):
        service.open_incident(self.project, title="a", severity="critical", user=self.user)
        resolved = service.open_incident(self.project, title="b", user=self.user)
        service.transition(resolved, IncidentStatus.RESOLVED, user=self.user)
        s = service.summary(self.project)
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["open"], 1)
        self.assertEqual(s["critical_open"], 1)


class IncidentOperationsTests(TestCase):
    """An open critical incident degrades the Operations status (spec §10 × §20)."""

    def setUp(self):
        self.org = Organization.objects.create(name="IOpsOrg")
        self.project = Project.objects.create(organization=self.org, name="App")
        Deployment.objects.create(project=self.project, environment=DeployEnvironment.PRODUCTION,
                                  provider="preview", status=DeploymentStatus.SUCCEEDED)

    def test_critical_incident_marks_down(self):
        from apps.deployments.operations import operations_overview
        service.open_incident(self.project, title="outage", severity="critical")
        self.assertEqual(operations_overview(self.project)["status"], "down")

    def test_open_incident_degrades(self):
        from apps.deployments.operations import operations_overview
        service.open_incident(self.project, title="glitch", severity="low")
        self.assertEqual(operations_overview(self.project)["status"], "degraded")


class IncidentApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="io@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="im@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="ix@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="IApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_open_and_transition_via_api(self):
        create = self.client.post(
            reverse("incidents_api:list", args=[self.project.id]),
            data={"title": "DB slow", "severity": "high"},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(create.status_code, 201)
        iid = create.json()["id"]
        resp = self.client.post(
            reverse("incidents_api:transition", args=[iid]),
            data={"status": "resolved", "resolution": "restarted"},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "resolved")
        self.assertEqual(resp.json()["resolution"], "restarted")

    def test_member_cannot_open(self):
        resp = self.client.post(
            reverse("incidents_api:list", args=[self.project.id]),
            data={"title": "x"}, content_type="application/json", **auth(self.member))
        self.assertEqual(resp.status_code, 403)

    def test_tenant_isolation(self):
        resp = self.client.get(
            reverse("incidents_api:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
