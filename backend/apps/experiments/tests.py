"""A/B testing (spec §20): deterministic assignment, REAL exposure/conversion
counts, and an honest significance verdict — no fabricated winner."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.experiments import service
from apps.experiments.models import Experiment, ExperimentStatus
from apps.experiments.stats import assess, two_proportion_p
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


def _running(project):
    exp = service.create(project, key="cta", variants=[
        {"key": "control", "weight": 1}, {"key": "b", "weight": 1}])
    service.set_status(exp, ExperimentStatus.RUNNING)
    return exp


class AssignmentTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_needs_two_variants(self):
        with self.assertRaises(service.ExperimentError):
            service.create(self.project, key="x", variants=[{"key": "only"}])

    def test_assignment_is_stable_and_idempotent(self):
        exp = _running(self.project)
        v1 = service.assign(exp, "user-1")
        v2 = service.assign(exp, "user-1")
        self.assertEqual(v1, v2)
        self.assertEqual(exp.assignments.filter(subject="user-1").count(), 1)

    def test_only_running_experiment_assigns(self):
        exp = service.create(self.project, key="x",
                             variants=[{"key": "a"}, {"key": "b"}])  # draft
        self.assertIsNone(service.assign(exp, "user-1"))
        self.assertEqual(exp.assignments.count(), 0)

    def test_conversion_requires_assignment_and_is_once(self):
        exp = _running(self.project)
        self.assertFalse(service.convert(exp, "ghost"))   # never assigned
        service.assign(exp, "user-1")
        self.assertTrue(service.convert(exp, "user-1"))
        self.assertFalse(service.convert(exp, "user-1"))  # already converted

    def test_weighting_is_roughly_respected(self):
        exp = service.create(self.project, key="w", variants=[
            {"key": "a", "weight": 3}, {"key": "b", "weight": 1}])
        service.set_status(exp, ExperimentStatus.RUNNING)
        for i in range(1000):
            service.assign(exp, f"u{i}")
        a = exp.assignments.filter(variant="a").count()
        self.assertTrue(650 <= a <= 850)   # ~75% to the weight-3 variant

    def test_results_are_real_counts(self):
        exp = _running(self.project)
        for i in range(10):
            v = service.assign(exp, f"u{i}")
            if i < 3:
                service.convert(exp, f"u{i}")
        res = service.results(exp)
        total_exp = sum(v["exposures"] for v in res["variants"])
        total_conv = sum(v["conversions"] for v in res["variants"])
        self.assertEqual(total_exp, 10)
        self.assertEqual(total_conv, 3)


class SignificanceTests(TestCase):
    def test_small_sample_is_not_called(self):
        v = [{"key": "a", "exposures": 10, "conversions": 5, "rate": 0.5},
             {"key": "b", "exposures": 10, "conversions": 2, "rate": 0.2}]
        self.assertEqual(assess(v)["status"], "collecting")
        self.assertIsNone(assess(v)["leader"])

    def test_clear_difference_is_significant(self):
        v = [{"key": "a", "exposures": 1000, "conversions": 300, "rate": 0.30},
             {"key": "b", "exposures": 1000, "conversions": 150, "rate": 0.15}]
        out = assess(v)
        self.assertEqual(out["status"], "significant")
        self.assertEqual(out["leader"], "a")

    def test_equal_rates_are_inconclusive(self):
        v = [{"key": "a", "exposures": 1000, "conversions": 200, "rate": 0.20},
             {"key": "b", "exposures": 1000, "conversions": 200, "rate": 0.20}]
        self.assertEqual(assess(v)["status"], "inconclusive")

    def test_p_value_bounds(self):
        p = two_proportion_p(300, 1000, 150, 1000)
        self.assertTrue(0 <= p < 0.05)


class ExperimentApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_create_run_assign_convert(self):
        resp = self.client.post(
            reverse("experiments:list", args=[self.project.id]),
            {"key": "cta", "variants": [{"key": "control"}, {"key": "b"}]},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 201)
        eid = resp.json()["id"]
        self.client.post(reverse("experiments:status", args=[eid]),
                         {"status": "running"}, content_type="application/json",
                         **auth(self.owner))
        a = self.client.post(reverse("experiments:assign", args=[eid]),
                             {"subject": "u1"}, content_type="application/json",
                             **auth(self.owner))
        self.assertIn(a.json()["variant"], ("control", "b"))
        c = self.client.post(reverse("experiments:convert", args=[eid]),
                             {"subject": "u1"}, content_type="application/json",
                             **auth(self.owner))
        self.assertTrue(c.json()["recorded"])

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("experiments:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_create(self):
        resp = self.client.post(
            reverse("experiments:list", args=[self.project.id]),
            {"key": "x", "variants": [{"key": "a"}, {"key": "b"}]},
            content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(Experiment.objects.count(), 0)
