"""Mobile capability registry + planner: honest status, real inference, honest plan.

The planner must never present a gated step (build / sign / submit) as if the engine
performs it today, and the registry's statuses must stay honest.
"""
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.mobile import capabilities as caps
from apps.mobile import planner

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class RegistryTests(SimpleTestCase):
    def test_every_capability_has_an_honest_status(self):
        for c in caps.all_capabilities():
            self.assertIn(c.status, (caps.GENERATED, caps.GATED, caps.PLANNED), c.id)

    def test_groups_cover_the_spec_areas(self):
        groups = {g for g, _ in caps.by_group()}
        self.assertLessEqual(
            {"UI", "Auth", "Data", "Device", "Communication", "Commerce",
             "Analytics", "Release"}, groups)

    def test_store_and_signing_are_gated_not_generated(self):
        # The honesty guardrail: builds/signing/submission need real credentials.
        for cid in ("signing", "store_submission", "push", "biometric"):
            self.assertEqual(caps.get(cid).status, caps.GATED, cid)

    def test_core_app_shell_is_generated(self):
        for cid in ("screens", "navigation", "auth", "api", "commerce"):
            self.assertEqual(caps.get(cid).status, caps.GENERATED, cid)

    def test_capabilities_declare_their_permissions(self):
        self.assertIn("camera", caps.get("camera").permissions)
        self.assertIn("location", caps.get("location").permissions)
        self.assertIn("notifications", caps.get("push").permissions)

    def test_push_has_per_platform_notes_including_huawei(self):
        notes = caps.get("push").platform_notes
        self.assertIn("huawei", notes)
        self.assertIn("HMS", notes["huawei"])  # not FCM on Huawei


class PlannerTests(SimpleTestCase):
    def _ids(self, brief):
        return set(planner.capability_ids(brief))

    def test_baseline_shell_always_present(self):
        ids = self._ids("a simple app")
        self.assertLessEqual(
            {"screens", "navigation", "auth", "api", "database", "local_storage"}, ids)

    def test_construction_field_app_infers_the_right_capabilities(self):
        # The spec's worked example (§5/§48).
        ids = self._ids(
            "A mobile app for a construction company where employees log jobs, "
            "upload photos, capture GPS coordinates, record materials used, and "
            "managers see job progress and costs on a dashboard.")
        for expected in ("forms", "camera", "gallery", "location", "offline",
                         "dashboards", "charts"):
            self.assertIn(expected, ids, expected)

    def test_commerce_brief_pulls_in_payments_and_invoicing(self):
        ids = self._ids("an e-commerce app with products, cart and checkout")
        self.assertIn("commerce", ids)
        self.assertIn("payments", ids)
        self.assertIn("invoicing", ids)

    def test_plan_lists_device_permissions_with_rationale(self):
        p = planner.plan("an app that takes photos and tracks delivery location")
        perm_ids = {perm["id"] for perm in p["permissions"]}
        self.assertIn("camera", perm_ids)
        self.assertIn("location", perm_ids)
        for perm in p["permissions"]:
            self.assertTrue(perm["rationale"])   # every permission explains itself

    def test_plan_targets_all_three_platforms_by_default(self):
        p = planner.plan("a booking app")
        ids = {pl["id"] for pl in p["platforms"]}
        self.assertEqual(ids, {"ios", "android", "huawei"})

    def test_plan_platforms_can_be_narrowed(self):
        p = planner.plan("a booking app", platforms=["ios"])
        self.assertEqual([pl["id"] for pl in p["platforms"]], ["ios"])

    def test_plan_is_honest_about_gated_steps(self):
        p = planner.plan("publish my store app to the app store")
        # Submission + signing appear, but as gated — never as generated.
        self.assertIn("Store submission", p["summary"]["gated_names"])
        self.assertIn("App signing", p["summary"]["gated_names"])
        self.assertIn("connected developer accounts", p["disclosure"])
        self.assertEqual(
            p["summary"]["total"],
            p["summary"]["generated_count"] + p["summary"]["gated_count"]
            + p["summary"]["planned_count"])


class MobileApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="m@x.com", password="pw12345!")

    def test_capabilities_endpoint(self):
        resp = self.client.get(reverse("mobile_api:capabilities"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        groups = {g["group"] for g in resp.json()["groups"]}
        self.assertIn("Device", groups)
        self.assertIn("Release", groups)

    def test_plan_endpoint_get(self):
        resp = self.client.get(
            reverse("mobile_api:plan"),
            {"brief": "a field-service app with photos, GPS and offline mode"},
            **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        self.assertGreater(d["summary"]["generated_count"], 0)
        perm_ids = {p["id"] for p in d["permissions"]}
        self.assertIn("camera", perm_ids)
        self.assertIn("location", perm_ids)

    def test_plan_endpoint_post_with_platforms(self):
        resp = self.client.post(
            reverse("mobile_api:plan"),
            data={"brief": "a store app", "platforms": ["android", "huawei"]},
            content_type="application/json", **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([p["id"] for p in resp.json()["platforms"]],
                         ["android", "huawei"])

    def test_plan_requires_auth(self):
        resp = self.client.get(reverse("mobile_api:plan"), {"brief": "x"})
        self.assertEqual(resp.status_code, 401)
