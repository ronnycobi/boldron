"""Change impact analysis (spec §6, §8, §19): surfaces touched + required tests,
derived honestly from the plan × the project's real capabilities."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.changes.impact import analyze_impact
from apps.changes.models import ChangeRequest
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def _change(project, *, description, plan):
    return ChangeRequest.objects.create(
        project=project, description=description, plan=plan,
        requires_approval=plan.get("requires_approval", False))


class ImpactAnalysisTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="ImpactOrg")
        self.user = User.objects.create_user(email="i@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)

    def _project(self, **kw):
        return Project.objects.create(organization=self.org, name="App", **kw)

    def test_database_and_api_change_requires_isolation_and_migration_tests(self):
        project = self._project(capabilities=["auth", "database", "ecommerce"])
        change = _change(project, description="Add a loyalty points field to customers",
                         plan={"summary": "Add loyalty points",
                               "affected_areas": {"database": ["customer.points"],
                                                  "api": ["GET /points"]},
                               "risk": "medium", "requires_approval": True})
        impact = analyze_impact(change)
        self.assertIn("Database migration test", impact["required_tests"])
        self.assertIn("API contract test", impact["required_tests"])
        self.assertIn("Tenant isolation test", impact["required_tests"])  # multi-tenant app
        self.assertIn("Regression test", impact["required_tests"])
        self.assertEqual(impact["tests_required"], len(impact["required_tests"]))
        self.assertGreater(impact["tests_required"], 0)

    def test_payment_change_on_commerce_app_flags_payments_surface_and_test(self):
        project = self._project(capabilities=["auth", "database", "ecommerce", "payments"])
        change = _change(project, description="Add recurring subscriptions and checkout",
                         plan={"summary": "Recurring billing",
                               "affected_areas": {"backend": ["billing"], "api": ["POST /subscribe"],
                                                  "database": ["subscription"]},
                               "risk": "high", "requires_approval": True})
        impact = analyze_impact(change)
        names = {s["name"] for s in impact["surfaces"]}
        self.assertIn("Payments", names)
        self.assertIn("Commerce", names)
        self.assertIn("Payment flow test", impact["required_tests"])

    def test_mobile_project_change_flags_mobile_surface_and_test(self):
        project = self._project(
            capabilities=["auth", "database", "ecommerce"],
            mobile_plan={"platforms": ["ios", "android", "huawei"], "capabilities": ["screens"]})
        change = _change(project, description="Add an orders endpoint",
                         plan={"summary": "Orders API",
                               "affected_areas": {"api": ["GET /orders"], "backend": ["orders"]},
                               "risk": "medium"})
        impact = analyze_impact(change)
        mobile = next((s for s in impact["surfaces"] if s["name"] == "Mobile apps"), None)
        self.assertIsNotNone(mobile)
        self.assertIn("Huawei AppGallery", mobile["detail"])
        self.assertIn("Mobile API test", impact["required_tests"])

    def test_non_commerce_project_does_not_invent_commerce_surface(self):
        project = self._project(capabilities=["auth", "database"])  # no ecommerce/payments
        change = _change(project, description="Change the homepage copy",
                         plan={"summary": "Copy edit", "affected_areas": {"frontend": ["home"]},
                               "risk": "low"})
        impact = analyze_impact(change)
        names = {s["name"] for s in impact["surfaces"]}
        self.assertNotIn("Commerce", names)
        self.assertNotIn("Payments", names)
        self.assertIn("UI test", impact["required_tests"])

    def test_risk_and_approval_surface(self):
        project = self._project(capabilities=["database"])
        change = _change(project, description="x",
                         plan={"affected_areas": {"database": ["t"]}, "risk": "high",
                               "requires_approval": True})
        impact = analyze_impact(change)
        self.assertEqual(impact["risk_label"], "High")
        self.assertTrue(impact["requires_approval"])
