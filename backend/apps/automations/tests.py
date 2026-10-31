"""Automations (spec §10-11): a trigger→conditions→actions engine that fires from
REAL platform events, runs only when conditions match, and records each action's
HONEST outcome (done / skipped / failed) — never a faked success. Automations do
not cascade (loop-safe)."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.automations import engine, service
from apps.automations.models import RunStatus, Workflow, WorkflowStatus
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class EngineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def _wf(self, **kw):
        defaults = dict(name="A", trigger="incident.opened",
                        actions=[{"type": "note", "params": {"text": "seen {title}"}}])
        defaults.update(kw)
        return service.create(self.project, **defaults)

    def test_fire_runs_matching_active_workflow(self):
        wf = self._wf()
        service.set_status(wf, WorkflowStatus.ACTIVE)
        runs = engine.fire(self.project, "incident.opened", {"title": "DB down"})
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, RunStatus.COMPLETED)
        # the {title} token was really substituted into the note
        from apps.project_context.models import ContextKind
        note = self.project.context_entries.filter(kind=ContextKind.NOTE).first()
        self.assertIn("DB down", note.content)

    def test_draft_workflow_does_not_fire(self):
        self._wf()  # left draft
        self.assertEqual(engine.fire(self.project, "incident.opened", {}), [])

    def test_conditions_gate_execution(self):
        wf = self._wf(conditions=[{"fact": "severity", "op": "eq", "value": "critical"}])
        service.set_status(wf, WorkflowStatus.ACTIVE)
        self.assertEqual(
            len(engine.fire(self.project, "incident.opened", {"severity": "low"})), 0)
        self.assertEqual(
            len(engine.fire(self.project, "incident.opened", {"severity": "critical"})), 1)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_action_is_skipped_when_not_configured(self):
        wf = self._wf(actions=[{"type": "email",
                                "params": {"to": "x@y.com", "message": "hi"}}])
        service.set_status(wf, WorkflowStatus.ACTIVE)
        run = engine.fire(self.project, "incident.opened", {})[0]
        # locmem is not real delivery -> honestly skipped, never "sent".
        self.assertEqual(run.results[0]["outcome"], "skipped")
        self.assertEqual(run.status, RunStatus.PARTIAL)

    def test_email_gate_keys_off_a_real_backend(self):
        from apps.automations.actions import _email_configured
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
            self.assertTrue(_email_configured())
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            self.assertFalse(_email_configured())

    def test_automations_do_not_cascade(self):
        # An automation whose action opens an incident must NOT re-trigger the
        # incident.opened automations (loop guard).
        wf = self._wf(actions=[{"type": "open_incident",
                                "params": {"title": "from automation"}}])
        service.set_status(wf, WorkflowStatus.ACTIVE)
        engine.fire(self.project, "incident.opened", {"title": "root"})
        # exactly one incident opened (the action's), no runaway recursion
        self.assertEqual(self.project.incidents.count(), 1)

    def test_run_now_respects_conditions(self):
        wf = self._wf(conditions=[{"fact": "severity", "op": "eq", "value": "high"}])
        run = engine.run_now(wf, {"severity": "low"})
        self.assertEqual(run.status, RunStatus.SKER)


class RealEmitterTests(TestCase):
    """Every offered trigger is wired to a real event — prove the incident one."""

    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_opening_an_incident_fires_the_automation(self):
        wf = service.create(
            self.project, name="Alert on incident", trigger="incident.opened",
            actions=[{"type": "note", "params": {"text": "incident {title}"}}])
        service.set_status(wf, WorkflowStatus.ACTIVE)
        from apps.incidents import service as inc
        inc.open_incident(self.project, title="API 500s", severity="high")
        wf.refresh_from_db()
        self.assertEqual(wf.run_count, 1)


class ValidationAndApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_unknown_trigger_rejected(self):
        with self.assertRaises(service.AutomationError):
            service.create(self.project, name="x", trigger="nope",
                           actions=[{"type": "note", "params": {"text": "hi"}}])

    def test_unknown_action_rejected(self):
        with self.assertRaises(service.AutomationError):
            service.create(self.project, name="x", trigger="manual",
                           actions=[{"type": "launch_missiles", "params": {}}])

    def test_needs_at_least_one_action(self):
        with self.assertRaises(service.AutomationError):
            service.create(self.project, name="x", trigger="manual", actions=[])

    def test_create_and_test_run_via_api(self):
        resp = self.client.post(
            reverse("automations:list", args=[self.project.id]),
            {"name": "Note it", "trigger": "manual",
             "actions": [{"type": "note", "params": {"text": "ran"}}]},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 201)
        wf_id = resp.json()["id"]
        run = self.client.post(
            reverse("automations:run", args=[wf_id]), {"facts": {}},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["status"], "completed")

    def test_catalog_lists_triggers_and_actions(self):
        resp = self.client.get(
            reverse("automations:list", args=[self.project.id]), **auth(self.owner))
        cat = resp.json()["catalog"]
        self.assertTrue(any(t["key"] == "incident.opened" for t in cat["triggers"]))
        self.assertTrue(any(a["key"] == "notify" for a in cat["actions"]))

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("automations:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_create(self):
        resp = self.client.post(
            reverse("automations:list", args=[self.project.id]),
            {"name": "x", "trigger": "manual",
             "actions": [{"type": "note", "params": {"text": "x"}}]},
            content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(Workflow.objects.count(), 0)
