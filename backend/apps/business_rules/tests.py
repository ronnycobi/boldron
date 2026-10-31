"""Formal business rules (spec §12-13): a deterministic engine, an HONEST split
between rules the engine truly enforces and rules that are documented-only, and
an explicit draft → active → retired lifecycle."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.business_rules import service
from apps.business_rules.engine import evaluate, evaluate_rule, validate_definition
from apps.business_rules.models import BusinessRule, RuleStatus
from apps.organizations.models import Organization, Role
from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class EngineTests(TestCase):
    def test_validate_definition(self):
        ok, _ = validate_definition(
            {"when": [{"fact": "total", "op": "gte", "value": 1000}],
             "then": {"outcome": "free_shipping"}})
        self.assertTrue(ok)
        bad_op, err = validate_definition(
            {"when": [{"fact": "total", "op": "superior", "value": 1}],
             "then": {"outcome": "x"}})
        self.assertFalse(bad_op)
        no_outcome, _ = validate_definition({"when": [], "then": {}})
        self.assertFalse(no_outcome)

    def test_rule_fires_only_when_conditions_hold(self):
        defn = {"when": [{"fact": "total", "op": "gte", "value": 1000}],
                "then": {"outcome": "free_shipping"}}
        fired, then = evaluate_rule(defn, {"total": 1500})
        self.assertTrue(fired)
        self.assertEqual(then["outcome"], "free_shipping")
        self.assertFalse(evaluate_rule(defn, {"total": 500})[0])

    def test_missing_fact_does_not_fire(self):
        defn = {"when": [{"fact": "total", "op": "gte", "value": 1000}],
                "then": {"outcome": "x"}}
        # The caller didn't supply 'total' — the rule must not fire on absent data.
        self.assertFalse(evaluate_rule(defn, {"other": 1})[0])

    def test_non_numeric_ordered_comparison_is_false_not_error(self):
        defn = {"when": [{"fact": "total", "op": "gte", "value": 1000}],
                "then": {"outcome": "x"}}
        self.assertFalse(evaluate_rule(defn, {"total": "abc"})[0])

    def test_empty_when_always_fires(self):
        defn = {"when": [], "then": {"outcome": "vat", "rate": 0.15}}
        fired, then = evaluate_rule(defn, {})
        self.assertTrue(fired)
        self.assertEqual(then["rate"], 0.15)


class LifecycleAndHonestyTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Shop")
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="Store")

    def test_enforceable_only_with_valid_definition(self):
        enf = service.create(
            self.project, name="Free shipping", category="shipping",
            definition={"when": [{"fact": "total", "op": "gte", "value": 1000}],
                        "then": {"outcome": "free_shipping"}}, user=self.user)
        doc = service.create(self.project, name="Be nice to customers",
                             description="Policy only.", user=self.user)
        self.assertTrue(enf.is_enforceable)
        self.assertFalse(doc.is_enforceable)

    def test_invalid_definition_rejected(self):
        with self.assertRaises(service.RuleError):
            service.create(self.project, name="Bad",
                           definition={"when": [{"fact": "", "op": "eq", "value": 1}],
                                       "then": {"outcome": "x"}}, user=self.user)

    def test_summary_splits_enforced_vs_documented(self):
        enf = service.create(
            self.project, name="Free shipping", category="shipping",
            definition={"when": [{"fact": "total", "op": "gte", "value": 1000}],
                        "then": {"outcome": "free_shipping"}}, user=self.user)
        doc = service.create(self.project, name="Policy", user=self.user)
        service.set_status(enf, RuleStatus.ACTIVE, user=self.user)
        service.set_status(doc, RuleStatus.ACTIVE, user=self.user)
        s = service.summary(self.project)
        self.assertEqual(s["active"], 2)
        self.assertEqual(s["enforced"], 1)     # only the one the engine can decide
        self.assertEqual(s["documented"], 1)

    def test_only_active_enforceable_rules_evaluate(self):
        # Draft enforceable rule must not fire until activated.
        rule = service.create(
            self.project, name="Free shipping", category="shipping",
            definition={"when": [{"fact": "total", "op": "gte", "value": 1000}],
                        "then": {"outcome": "free_shipping"}}, user=self.user)
        self.assertEqual(evaluate(self.project, {"total": 2000})["fired_count"], 0)
        service.set_status(rule, RuleStatus.ACTIVE, user=self.user)
        result = evaluate(self.project, {"total": 2000})
        self.assertEqual(result["fired_count"], 1)
        self.assertEqual(result["outcomes"], ["free_shipping"])

    def test_import_from_context_is_idempotent_and_documentation_only(self):
        ProjectContext(self.project).add(
            ContextKind.BUSINESS_RULE, title="Free shipping over R1000",
            content="Orders above R1000 ship free.")
        self.assertEqual(service.import_from_context(self.project), 1)
        self.assertEqual(service.import_from_context(self.project), 0)
        rule = self.project.business_rules.first()
        self.assertEqual(rule.status, RuleStatus.DRAFT)
        self.assertFalse(rule.is_enforceable)   # free text => documented, not enforced


class RuleApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="Store")

    def test_create_activate_and_evaluate(self):
        resp = self.client.post(
            reverse("business_rules:list", args=[self.project.id]),
            {"name": "Free shipping", "category": "shipping",
             "definition": {"when": [{"fact": "total", "op": "gte", "value": 1000}],
                            "then": {"outcome": "free_shipping"}}},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["enforceable"])
        rule_id = resp.json()["id"]
        self.client.post(reverse("business_rules:status", args=[rule_id]),
                         {"status": "active"},
                         content_type="application/json", **auth(self.owner))
        ev = self.client.post(
            reverse("business_rules:evaluate", args=[self.project.id]),
            {"facts": {"total": 1500}},
            content_type="application/json", **auth(self.owner))
        self.assertEqual(ev.status_code, 200)
        self.assertEqual(ev.json()["outcomes"], ["free_shipping"])

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("business_rules:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_outsider_cannot_create(self):
        resp = self.client.post(
            reverse("business_rules:list", args=[self.project.id]),
            {"name": "x"}, content_type="application/json", **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(BusinessRule.objects.count(), 0)
