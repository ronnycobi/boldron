"""Feature flags (spec §19): deterministic, honest evaluation — off unless
enabled, stable percentage rollout, and condition targeting via the shared
business-rules engine."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.flags import service
from apps.flags.models import FeatureFlag
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class EvaluationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_disabled_flag_is_off(self):
        f = service.create(self.project, key="new-ui", enabled=False)
        self.assertFalse(service.evaluate(f))
        self.assertFalse(service.is_enabled(self.project, "new-ui"))

    def test_enabled_full_rollout_is_on(self):
        service.create(self.project, key="new-ui", enabled=True)
        self.assertTrue(service.is_enabled(self.project, "new-ui"))

    def test_conditions_gate_the_flag(self):
        service.create(self.project, key="beta", enabled=True,
                       conditions=[{"fact": "plan", "op": "eq", "value": "pro"}])
        self.assertTrue(service.is_enabled(self.project, "beta", {"plan": "pro"}))
        self.assertFalse(service.is_enabled(self.project, "beta", {"plan": "free"}))
        # missing fact -> condition fails -> off (honest, never defaults on)
        self.assertFalse(service.is_enabled(self.project, "beta", {}))

    def test_rollout_is_stable_per_subject(self):
        f = service.create(self.project, key="exp", enabled=True, rollout=50)
        a = service.evaluate(f, {"subject": "user-1"})
        b = service.evaluate(f, {"subject": "user-1"})
        self.assertEqual(a, b)   # same subject always gets the same answer

    def test_rollout_zero_is_off_and_hundred_is_on(self):
        off = service.create(self.project, key="z", enabled=True, rollout=0)
        on = service.create(self.project, key="h", enabled=True, rollout=100)
        self.assertFalse(service.evaluate(off, {"subject": "x"}))
        self.assertTrue(service.evaluate(on, {"subject": "x"}))

    def test_rollout_distribution_is_roughly_proportional(self):
        f = service.create(self.project, key="r", enabled=True, rollout=30)
        on = sum(1 for i in range(1000)
                 if service.evaluate(f, {"subject": f"u{i}"}))
        self.assertTrue(200 <= on <= 400)   # ~30% of 1000, deterministic hash

    def test_archived_flag_is_off_and_hidden(self):
        f = service.create(self.project, key="old", enabled=True)
        service.update(f, archived=True)
        self.assertFalse(service.is_enabled(self.project, "old"))
        self.assertNotIn("old", service.evaluate_all(self.project))

    def test_duplicate_key_rejected(self):
        service.create(self.project, key="dup")
        with self.assertRaises(service.FlagError):
            service.create(self.project, key="dup")

    def test_rollout_out_of_range_rejected(self):
        with self.assertRaises(service.FlagError):
            service.create(self.project, key="bad", rollout=150)


class FlagApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_create_toggle_and_evaluate(self):
        resp = self.client.post(
            reverse("flags:list", args=[self.project.id]),
            {"key": "new-ui", "enabled": False}, content_type="application/json",
            **auth(self.owner))
        self.assertEqual(resp.status_code, 201)
        fid = resp.json()["id"]
        ev = self.client.post(
            reverse("flags:evaluate", args=[self.project.id]),
            {"context": {}}, content_type="application/json", **auth(self.owner))
        self.assertFalse(ev.json()["flags"]["new-ui"])
        self.client.post(reverse("flags:toggle", args=[fid]), {"enabled": True},
                         content_type="application/json", **auth(self.owner))
        ev2 = self.client.post(
            reverse("flags:evaluate", args=[self.project.id]),
            {"context": {}}, content_type="application/json", **auth(self.owner))
        self.assertTrue(ev2.json()["flags"]["new-ui"])

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("flags:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_create(self):
        resp = self.client.post(
            reverse("flags:list", args=[self.project.id]), {"key": "x"},
            content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(FeatureFlag.objects.count(), 0)
