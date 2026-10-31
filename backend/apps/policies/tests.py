"""Policy engine (spec §44): declarative governance that genuinely gates a real
action. A block policy stops a deploy; a require-approval policy forces approval;
policies can only target scopes the platform actually enforces."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.deployments import service as deploy
from apps.deployments.models import DeployEnvironment, DeploymentStatus
from apps.organizations.models import Organization, Role
from apps.policies import service
from apps.policies.engine import decide
from apps.policies.models import Policy, PolicyEffect
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class EngineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_block_policy_denies(self):
        service.create(self.project, name="No prod on Friday", effect="block",
                       conditions=[{"fact": "is_production", "op": "eq", "value": True}],
                       message="Production is frozen.")
        d = decide(self.project, "deploy", {"is_production": True})
        self.assertFalse(d["allowed"])
        self.assertEqual(d["blocks"][0]["message"], "Production is frozen.")
        # staging is unaffected
        self.assertTrue(decide(self.project, "deploy", {"is_production": False})["allowed"])

    def test_disabled_policy_is_ignored(self):
        p = service.create(self.project, name="x", effect="block", conditions=[])
        service.set_enabled(p, False)
        self.assertTrue(decide(self.project, "deploy", {})["allowed"])

    def test_require_approval_effect(self):
        service.create(self.project, name="Approve prod", effect="require_approval",
                       conditions=[{"fact": "is_production", "op": "eq", "value": True}])
        d = decide(self.project, "deploy", {"is_production": True})
        self.assertTrue(d["allowed"])     # not a hard block
        self.assertEqual(len(d["require_approval"]), 1)

    def test_only_enforced_scope_allowed(self):
        with self.assertRaises(service.PolicyError):
            service.create(self.project, name="x", scope="change", effect="block")

    def test_built_in_guardrails_surface_real_gates(self):
        names = [g["name"] for g in service.built_in_guardrails(self.project)]
        self.assertTrue(any("approval" in n.lower() for n in names))
        self.assertTrue(any("security" in n.lower() for n in names))


class DeployEnforcementTests(TestCase):
    """The policy genuinely stops a real deploy — not advisory."""

    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def _deployment(self, env):
        return deploy.request_deploy(project=self.project, environment=env,
                                     provider="local")

    def test_block_policy_actually_fails_the_deploy(self):
        service.create(self.project, name="Freeze staging", effect="block",
                       conditions=[{"fact": "environment", "op": "eq", "value": "staging"}],
                       message="Staging is frozen.")
        d = self._deployment(DeployEnvironment.STAGING)
        deploy.run(d)
        d.refresh_from_db()
        self.assertEqual(d.status, DeploymentStatus.FAILED)
        self.assertIn("policy", d.log.lower())

    def test_deploy_proceeds_without_a_matching_policy(self):
        # No policy -> the deploy runs its normal course (succeeds via local provider).
        d = self._deployment(DeployEnvironment.STAGING)
        deploy.run(d)
        d.refresh_from_db()
        self.assertEqual(d.status, DeploymentStatus.SUCCEEDED)


class PolicyApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_create_and_list_with_built_ins(self):
        resp = self.client.post(
            reverse("policies:list", args=[self.project.id]),
            {"name": "Freeze prod", "effect": "block",
             "conditions": [{"fact": "is_production", "op": "eq", "value": True}]},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 201)
        listing = self.client.get(
            reverse("policies:list", args=[self.project.id]), **auth(self.owner)).json()
        self.assertEqual(len(listing["policies"]), 1)
        self.assertTrue(listing["built_in"])   # real gates surfaced too

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("policies:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_create(self):
        resp = self.client.post(
            reverse("policies:list", args=[self.project.id]),
            {"name": "x", "effect": "block"}, content_type="application/json",
            **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(Policy.objects.count(), 0)
