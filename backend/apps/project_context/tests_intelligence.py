"""Project Intelligence Engine (spec §14): composes structured knowledge, stays
customer-safe (no internal stack/agents/infra), and is tenant-isolated."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.project_context.intelligence import build_intelligence, intelligence_digest
from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class IntelligenceCompositionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="IntelOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(
            organization=self.org, name="Shop", description="an online store",
            capabilities=["auth", "database", "ecommerce", "subscriptions", "sms"],
            mobile_plan={"platforms": ["ios", "android", "huawei"],
                         "capabilities": ["screens", "camera"]})
        ctx = ProjectContext(self.project)
        ctx.set(ContextKind.REQUIREMENT, "r1", title="Sell products", content="Customers buy goods")
        ctx.set(ContextKind.SCHEMA, "s1", title="Product", content="name, price, stock")
        ctx.set(ContextKind.API, "a1", title="Orders API", content="create/list orders")
        ctx.set(ContextKind.SCREEN, "ui1", title="Home", content="landing", data={"platform": "web"})
        ctx.set(ContextKind.SCREEN, "m1", title="Cart", content="mobile cart", data={"platform": "mobile"})
        ctx.set(ContextKind.SECURITY, "sec1", title="Tenant isolation", content="scope to org")

    def test_areas_are_composed_from_context(self):
        intel = build_intelligence(self.project)
        by_key = {a["key"]: a for a in intel["areas"]}
        self.assertEqual(by_key["requirements"]["count"], 1)
        self.assertEqual(by_key["database"]["count"], 1)
        self.assertEqual(by_key["apis"]["count"], 1)
        self.assertEqual(by_key["security_rules"]["count"], 1)
        # UI vs Mobile split by platform.
        self.assertEqual(by_key["ui"]["count"], 1)
        self.assertEqual(by_key["mobile"]["count"], 1)
        self.assertEqual(by_key["mobile"]["platforms"],
                         ["iOS", "Android", "Huawei AppGallery"])

    def test_capability_split_is_honest(self):
        caps = build_intelligence(self.project)["capabilities"]
        self.assertIn("E-commerce", caps["built"])
        self.assertIn("SMS", caps["coming"])        # planned, not faked as built

    def test_permissions_reflect_membership(self):
        intel = build_intelligence(self.project)
        self.assertEqual(intel["permissions"]["members"], 1)
        self.assertEqual(intel["permissions"]["by_role"].get("owner"), 1)

    def test_internal_kinds_are_never_exposed(self):
        # Stack / infrastructure / agent decisions / review findings are internal.
        ctx = ProjectContext(self.project)
        ctx.set(ContextKind.STACK, "stk", title="Django + Postgres", content="python stack")
        ctx.set(ContextKind.AGENT_DECISION, "ad", title="Mobile Agent chose X", content="internal")
        ctx.set(ContextKind.INFRASTRUCTURE, "inf", title="k8s cluster", content="internal infra")
        intel = build_intelligence(self.project)
        blob = str(intel)
        self.assertNotIn("Django", blob)
        self.assertNotIn("Mobile Agent", blob)
        self.assertNotIn("k8s", blob)
        # And no 'source' field leaks (which holds "agent:…#task:…").
        for area in intel["areas"]:
            for item in area["items"]:
                self.assertNotIn("source", item)

    def test_digest_is_text_and_customer_safe(self):
        d = intelligence_digest(self.project)
        self.assertIn("Shop", d)
        self.assertIn("E-commerce", d)
        self.assertNotIn("agent:", d)


class IntelligenceApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o2@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="out@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="IntelApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(
            organization=self.org, name="App", description="a saas app",
            capabilities=["auth", "database"])

    def test_endpoint_returns_intelligence(self):
        resp = self.client.get(
            reverse("project_context:intelligence", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["project"]["name"], "App")
        self.assertIn("areas", resp.json())
        self.assertIn("capabilities", resp.json())

    def test_endpoint_is_tenant_isolated(self):
        resp = self.client.get(
            reverse("project_context:intelligence", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))   # never another org's intelligence

    def test_endpoint_requires_auth(self):
        resp = self.client.get(
            reverse("project_context:intelligence", args=[self.project.id]))
        self.assertEqual(resp.status_code, 401)
