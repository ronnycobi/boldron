"""The Application Graph (spec §4) + Dependency Intelligence (spec §5).

The graph is composed from real project data (capabilities, context entries,
mobile plan); edges only connect nodes that exist, so nothing implies a surface
the app doesn't have. It is customer-safe — no internal stack / agent / source.
Dependency Intelligence answers "what breaks if this changes?" over real edges.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.project_context.graph import build_graph, dependency_report
from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ApplicationGraphTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Shopco")
        self.project = Project.objects.create(
            organization=self.org, name="Store",
            capabilities=["users", "auth", "database", "api", "ecommerce",
                          "payments", "email", "analytics", "stripe", "security"],
            mobile_plan={"platforms": ["ios", "android"]},
        )
        self.ctx = ProjectContext(self.project)

    def test_nodes_cover_features_and_mobile_platforms(self):
        graph = build_graph(self.project)
        ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("app", ids)
        self.assertIn("cap:ecommerce", ids)
        self.assertIn("cap:payments", ids)
        self.assertIn("platform:ios", ids)
        self.assertIn("platform:android", ids)
        # typed and labelled honestly
        by_id = {n["id"]: n for n in graph["nodes"]}
        self.assertEqual(by_id["platform:ios"]["label"], "iOS")
        self.assertEqual(by_id["cap:stripe"]["type"], "integration")
        self.assertFalse(by_id["cap:stripe"]["available"])  # Stripe is planned

    def test_architectural_dependency_edges_only_between_present_caps(self):
        graph = build_graph(self.project)
        edges = {(e["source"], e["target"], e["kind"]) for e in graph["edges"]}
        # ecommerce requires database + payments (both present)
        self.assertIn(("cap:ecommerce", "cap:database", "requires"), edges)
        self.assertIn(("cap:ecommerce", "cap:payments", "requires"), edges)
        # ecommerce uses tax/currency — but neither capability is in the app,
        # so no such edge may appear (nothing implied that isn't there).
        targets = {e["target"] for e in graph["edges"]}
        self.assertNotIn("cap:tax", targets)
        self.assertNotIn("cap:currency", targets)

    def test_screen_data_needs_become_api_edges(self):
        self.ctx.set(ContextKind.API, "orders-api", title="Orders API",
                     content="List and create orders.")
        self.ctx.set(ContextKind.SCREEN, "checkout", title="Checkout",
                     content="Pay for the cart.",
                     data={"platform": "web", "data_needs": ["Orders API"]})
        graph = build_graph(self.project)
        edges = {(e["source"], e["target"], e["kind"]) for e in graph["edges"]}
        self.assertIn(("screen:checkout", "api:orders-api", "uses"), edges)

    def test_customer_safe_excludes_internal_kinds_and_source(self):
        self.ctx.set(ContextKind.STACK, "stack", title="Django + Postgres",
                     content="Internal stack", source="agent:architect")
        self.ctx.set(ContextKind.AGENT_DECISION, "d1", title="Chose Celery",
                     content="internal")
        graph = build_graph(self.project)
        blob = str(graph)
        self.assertNotIn("Django", blob)
        self.assertNotIn("Celery", blob)
        self.assertNotIn("Postgres", blob)
        self.assertNotIn("agent:architect", blob)  # provenance never leaks
        # the STACK/AGENT_DECISION entries produce no nodes at all
        self.assertNotIn("stack", {n["id"] for n in graph["nodes"]})

    def test_stats_are_consistent(self):
        graph = build_graph(self.project)
        self.assertEqual(graph["stats"]["nodes"], len(graph["nodes"]))
        self.assertEqual(graph["stats"]["edges"], len(graph["edges"]))


class DependencyIntelligenceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Shopco")
        self.project = Project.objects.create(
            organization=self.org, name="Store",
            capabilities=["users", "auth", "database", "api", "ecommerce",
                          "payments", "subscriptions", "invoicing"],
            mobile_plan={"platforms": ["ios"]},
        )

    def test_dependents_show_what_breaks_if_payment_changes(self):
        report = dependency_report(self.project, "cap:payments")
        dependent_ids = {d["id"] for d in report["dependents"]}
        # ecommerce requires payments; subscriptions requires payments and
        # invoicing; so all three are affected if payments changes.
        self.assertIn("cap:ecommerce", dependent_ids)
        self.assertIn("cap:subscriptions", dependent_ids)
        self.assertIn("cap:invoicing", dependent_ids)
        self.assertEqual(report["impact_count"], len(report["dependents"]))

    def test_depends_on_is_transitive(self):
        report = dependency_report(self.project, "cap:subscriptions")
        dep_ids = {d["id"] for d in report["depends_on"]}
        # subscriptions -> payments -> database (transitive)
        self.assertIn("cap:payments", dep_ids)
        self.assertIn("cap:invoicing", dep_ids)
        self.assertIn("cap:database", dep_ids)

    def test_mobile_platform_runs_on_api(self):
        report = dependency_report(self.project, "cap:api")
        dependent_ids = {d["id"] for d in report["dependents"]}
        self.assertIn("platform:ios", dependent_ids)

    def test_unknown_node_returns_none(self):
        self.assertIsNone(dependency_report(self.project, "cap:nope"))


class ApplicationGraphApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(
            organization=self.org, name="Store",
            capabilities=["database", "api", "ecommerce", "payments"],
        )

    def test_graph_endpoint(self):
        resp = self.client.get(
            reverse("project_context:graph", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("nodes", resp.json())
        self.assertIn("edges", resp.json())

    def test_dependency_query(self):
        resp = self.client.get(
            reverse("project_context:graph", args=[self.project.id]),
            {"node": "cap:payments"}, **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("dependents", resp.json())

    def test_unknown_node_404(self):
        resp = self.client.get(
            reverse("project_context:graph", args=[self.project.id]),
            {"node": "cap:nope"}, **auth(self.owner))
        self.assertEqual(resp.status_code, 404)

    def test_non_member_blocked(self):
        resp = self.client.get(
            reverse("project_context:graph", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
