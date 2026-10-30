"""Browser & device compatibility analysis (spec §9): real static risks, honest
gating — never a fabricated 'passes on X'."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.testing import compatibility as compat

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


def _report_for(files):
    with mock.patch("apps.testing.compatibility._read_files", return_value=files):
        # project arg is unused once _read_files is patched.
        return compat.compatibility_report(project=object())


class CompatibilityAnalysisTests(TestCase):
    def test_google_services_flag_huawei(self):
        r = _report_for({
            "app/build.gradle": "implementation 'com.google.firebase:firebase-messaging'",
            "lib/map.dart": "import 'package:google_maps_flutter/google_maps_flutter.dart';",
        })
        huawei = next(p for p in r["platforms"] if p["id"] == "huawei")
        self.assertEqual(huawei["status"], "risk")
        joined = " ".join(huawei["risks"])
        self.assertIn("HMS Push Kit", joined)
        self.assertIn("Map Kit", joined)
        # iOS/Android are not flagged by Google-service deps.
        ios = next(p for p in r["platforms"] if p["id"] == "ios")
        self.assertEqual(ios["status"], "unverified")

    def test_browser_only_api_flags_safari_and_firefox(self):
        r = _report_for({"src/scan.js": "const d = new BarcodeDetector();"})
        safari = next(b for b in r["browsers"] if b["id"] == "safari")
        firefox = next(b for b in r["browsers"] if b["id"] == "firefox")
        chrome = next(b for b in r["browsers"] if b["id"] == "chrome")
        self.assertEqual(safari["status"], "risk")
        self.assertEqual(firefox["status"], "risk")
        self.assertEqual(chrome["status"], "unverified")   # Chromium supports it

    def test_missing_viewport_flags_mobile(self):
        r = _report_for({"index.html": "<html><head><title>x</title></head></html>"})
        for pid in ("ios", "android", "huawei"):
            p = next(x for x in r["platforms"] if x["id"] == pid)
            self.assertEqual(p["status"], "risk")
            self.assertTrue(any("viewport" in m for m in p["risks"]))

    def test_viewport_present_is_not_flagged(self):
        r = _report_for({
            "index.html": '<html><head><meta name="viewport" content="width=device-width"></head></html>'})
        huawei = next(p for p in r["platforms"] if p["id"] == "huawei")
        self.assertFalse(any("viewport" in m for m in huawei["risks"]))

    def test_no_target_is_ever_marked_passed(self):
        # The honesty guardrail: there is no 'ok'/'pass' status anywhere.
        r = _report_for({"a.js": "const x = 1;"})
        statuses = {t["status"] for t in r["browsers"] + r["platforms"]}
        self.assertTrue(statuses <= {"risk", "unverified"})
        self.assertNotIn("ok", statuses)
        self.assertNotIn("pass", statuses)

    def test_live_testing_is_honestly_not_connected(self):
        r = _report_for({"a.js": "x"})
        self.assertFalse(r["live_testing"]["connected"])

    def test_no_code_is_not_analysed(self):
        r = _report_for({})
        self.assertFalse(r["analysed"])
        self.assertEqual(r["risk_count"], 0)


class CompatibilityApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="co@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="cx@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="CompatOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_report_endpoint(self):
        with mock.patch("apps.testing.compatibility._read_files",
                        return_value={"m.dart": "FirebaseMessaging.instance"}):
            resp = self.client.get(
                reverse("testing_api:compatibility", args=[self.project.id]),
                **auth(self.owner))
        self.assertEqual(resp.status_code, 200)
        huawei = next(p for p in resp.json()["platforms"] if p["id"] == "huawei")
        self.assertEqual(huawei["status"], "risk")

    def test_tenant_isolation(self):
        resp = self.client.get(
            reverse("testing_api:compatibility", args=[self.project.id]),
            **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))
