"""Data quality (spec §9): deterministic checks over REAL rows — violation counts
and scores are true, never estimated; an unparseable rule is rejected up front."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.data_quality import service
from apps.data_quality.engine import evaluate
from apps.data_quality.models import Dataset
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class EngineTests(TestCase):
    def test_not_null_counts_real_violations(self):
        rules = [{"field": "email", "check": "not_null", "params": {}, "severity": "error"}]
        rows = [{"email": "a@x.com"}, {"email": ""}, {"email": None}, {}]
        res = evaluate(rules, rows)
        r = res["rules"][0]
        self.assertEqual(r["checked"], 4)
        self.assertEqual(r["violations"], 3)
        self.assertFalse(r["passed"])

    def test_unique_detects_duplicates(self):
        rules = [{"field": "id", "check": "unique", "params": {}, "severity": "error"}]
        rows = [{"id": 1}, {"id": 2}, {"id": 1}, {"id": 3}, {"id": 2}]
        r = evaluate(rules, rows)["rules"][0]
        self.assertEqual(r["violations"], 2)   # the 2nd "1" and 2nd "2"

    def test_regex_and_range_and_allowed(self):
        rules = [
            {"field": "email", "check": "regex", "params": {"pattern": r"^[^@]+@[^@]+$"}, "severity": "error"},
            {"field": "age", "check": "range", "params": {"min": 0, "max": 120}, "severity": "warning"},
            {"field": "status", "check": "allowed_values", "params": {"values": ["a", "b"]}, "severity": "error"},
        ]
        rows = [{"email": "bad", "age": 200, "status": "c"},
                {"email": "ok@x.com", "age": 30, "status": "a"}]
        res = {r["field"]: r for r in evaluate(rules, rows)["rules"]}
        self.assertEqual(res["email"]["violations"], 1)
        self.assertEqual(res["age"]["violations"], 1)
        self.assertEqual(res["status"]["violations"], 1)

    def test_score_is_real_and_weighted(self):
        rules = [{"field": "a", "check": "not_null", "params": {}, "severity": "error"}]
        clean = evaluate(rules, [{"a": 1}, {"a": 2}])
        self.assertEqual(clean["score"], 100)
        dirty = evaluate(rules, [{"a": 1}, {"a": None}])
        self.assertEqual(dirty["score"], 50)

    def test_empty_values_skip_shape_checks(self):
        # a blank value only fails not_null, not regex/range (presence vs shape)
        rules = [{"field": "x", "check": "regex", "params": {"pattern": "^\\d+$"}, "severity": "error"}]
        res = evaluate(rules, [{"x": ""}, {"x": "123"}])
        self.assertEqual(res["rules"][0]["violations"], 0)


class ServiceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_invalid_rule_rejected(self):
        ds = service.add_dataset(self.project, key="customers")
        with self.assertRaises(service.DataQualityError):
            service.add_rule(ds, field="x", check="not_a_check")
        with self.assertRaises(service.DataQualityError):
            service.add_rule(ds, field="x", check="regex", params={"pattern": "["})

    def test_check_records_a_real_run(self):
        ds = service.add_dataset(self.project, key="customers")
        service.add_rule(ds, field="email", check="not_null")
        run = service.check(ds, [{"email": "a@x.com"}, {"email": ""}])
        self.assertEqual(run.rows, 2)
        self.assertEqual(run.score, 50)
        self.assertEqual(run.failing, 1)
        self.assertEqual(ds.runs.count(), 1)

    def test_duplicate_dataset_rejected(self):
        service.add_dataset(self.project, key="customers")
        with self.assertRaises(service.DataQualityError):
            service.add_dataset(self.project, key="customers")


class DataQualityApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_create_dataset_rule_and_check(self):
        self.client.post(reverse("data_quality:datasets", args=[self.project.id]),
                         {"key": "customers"}, content_type="application/json",
                         **auth(self.owner))
        ds = Dataset.objects.get(project=self.project, key="customers")
        self.client.post(reverse("data_quality:rules", args=[ds.id]),
                         {"field": "email", "check": "not_null"},
                         content_type="application/json", **auth(self.owner))
        resp = self.client.post(
            reverse("data_quality:check", args=[ds.id]),
            {"rows": [{"email": "a@x.com"}, {"email": None}]},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["score"], 50)

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("data_quality:overview", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_create_dataset(self):
        resp = self.client.post(
            reverse("data_quality:datasets", args=[self.project.id]), {"key": "x"},
            content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(Dataset.objects.count(), 0)
