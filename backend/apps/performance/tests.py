"""Performance intelligence (spec §41): percentiles and budget flags computed
from REAL recorded samples only — never synthetic; empty until measured."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.performance import service
from apps.performance.analysis import percentile, stats_for
from apps.performance.models import PerformanceSample
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class AnalysisTests(TestCase):
    def test_percentiles_are_nearest_rank(self):
        values = list(range(1, 101))   # 1..100
        self.assertEqual(percentile(values, 50), 50)
        self.assertEqual(percentile(values, 95), 95)
        self.assertEqual(percentile(values, 100), 100)
        self.assertIsNone(percentile([], 95))

    def test_stats_over_real_durations(self):
        st = stats_for([10, 20, 30, 40])
        self.assertEqual(st["count"], 4)
        self.assertEqual(st["avg"], 25)
        self.assertEqual(st["max"], 40)

    def test_empty_is_none_not_zero(self):
        st = stats_for([])
        self.assertEqual(st["count"], 0)
        self.assertIsNone(st["p95"])


class ServiceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_record_skips_invalid_rows(self):
        n = service.record_samples(self.project, [
            {"label": "GET /a", "duration_ms": 100},
            {"label": "", "duration_ms": 50},         # no label -> skipped
            {"label": "GET /b", "duration_ms": "oops"},  # bad duration -> skipped
            {"label": "GET /c", "duration_ms": 200, "kind": "page"},
        ])
        self.assertEqual(n, 2)
        self.assertEqual(PerformanceSample.objects.count(), 2)

    def test_report_is_empty_until_measured(self):
        rep = service.report(self.project)
        self.assertEqual(rep["labels"], [])
        self.assertIsNone(rep["overall"]["p95"])
        self.assertIsNone(rep["slowest"])

    def test_report_ranks_slowest_and_flags_budget(self):
        service.record_samples(self.project,
            [{"label": "GET /fast", "duration_ms": 20} for _ in range(10)])
        service.record_samples(self.project,
            [{"label": "GET /slow", "duration_ms": 900} for _ in range(10)])
        service.set_budget(self.project, label="GET /slow", threshold_ms=500)
        rep = service.report(self.project)
        self.assertEqual(rep["slowest"], "GET /slow")
        self.assertIn("GET /slow", rep["over_budget"])
        slow = next(r for r in rep["labels"] if r["label"] == "GET /slow")
        self.assertTrue(slow["over_budget"])
        self.assertEqual(slow["p95"], 900)   # real measurement

    def test_default_budget_applies_to_all_labels(self):
        service.record_samples(self.project,
            [{"label": "GET /x", "duration_ms": 800} for _ in range(5)])
        service.set_budget(self.project, label="*", threshold_ms=300)
        rep = service.report(self.project)
        self.assertIn("GET /x", rep["over_budget"])

    def test_budget_validation(self):
        with self.assertRaises(service.PerformanceError):
            service.set_budget(self.project, label="*", threshold_ms=0)


class PerformanceApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_record_then_report(self):
        self.client.post(
            reverse("performance:samples", args=[self.project.id]),
            {"samples": [{"label": "GET /a", "duration_ms": 120}]},
            content_type="application/json", **auth(self.owner))
        rep = self.client.get(
            reverse("performance:overview", args=[self.project.id]), **auth(self.owner)).json()
        self.assertEqual(rep["summary"]["samples"], 1)
        self.assertEqual(rep["report"]["labels"][0]["label"], "GET /a")

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("performance:overview", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_set_budget(self):
        resp = self.client.post(
            reverse("performance:budgets", args=[self.project.id]),
            {"label": "*", "threshold_ms": 300}, content_type="application/json",
            **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
