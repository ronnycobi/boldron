"""Explain-my-application (spec §29): a plain-language explanation composed from
real project knowledge, customer-safe, never inventing capabilities."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.explain.explain import explain_application, explain_part, explain_text
from apps.organizations.models import Organization, Role
from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ExplainTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Shopco")
        self.project = Project.objects.create(
            organization=self.org, name="Store", description="an online store",
            capabilities=["users", "auth", "database", "api", "ecommerce",
                          "payments", "sms"],
            mobile_plan={"platforms": ["ios"]})
        ProjectContext(self.project).add(
            ContextKind.REQUIREMENT, title="Guest checkout", content="...")

    def test_overview_describes_built_features_and_platforms(self):
        data = explain_application(self.project)
        self.assertIn("Store", data["summary"])
        self.assertIn("E-commerce", data["does"])
        self.assertIn("Web", data["platforms"])
        self.assertIn("iOS", data["platforms"])

    def test_planned_capability_named_as_coming_not_built(self):
        data = explain_application(self.project)
        # SMS is planned on the platform -> it must appear under coming, not does.
        self.assertIn("SMS", data["coming"])
        self.assertNotIn("SMS", data["does"])

    def test_requirements_surface(self):
        data = explain_application(self.project)
        self.assertIn("Guest checkout", data["requirements"])

    def test_customer_safe_no_stack_or_agent(self):
        # seed internal context that must never surface
        ProjectContext(self.project).set(
            ContextKind.STACK, "stack", title="Django + Postgres", content="internal")
        blob = str(explain_application(self.project)) + explain_text(self.project)
        self.assertNotIn("Django", blob)
        self.assertNotIn("Postgres", blob)

    def test_explain_part_traces_dependencies(self):
        part = explain_part(self.project, "cap:ecommerce")
        self.assertIsNotNone(part)
        self.assertIn("relies on", part["explanation"])
        dep_labels = {d["label"] for d in part["depends_on"]}
        self.assertIn("Payments", dep_labels)   # ecommerce requires payments

    def test_explain_unknown_part_is_none(self):
        self.assertIsNone(explain_part(self.project, "cap:nope"))

    def test_text_is_bounded(self):
        self.assertLessEqual(len(explain_text(self.project, max_chars=200)), 200)


class ExplainApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(
            organization=self.org, name="Store",
            capabilities=["database", "api", "ecommerce", "payments"])

    def test_endpoint(self):
        resp = self.client.get(
            reverse("explain:explain", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("summary", resp.json())
        self.assertIn("parts", resp.json())

    def test_explain_part_endpoint(self):
        resp = self.client.get(
            reverse("explain:explain", args=[self.project.id]),
            {"node": "cap:payments"}, **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("explanation", resp.json())

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("explain:explain", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
