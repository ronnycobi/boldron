"""License tracking (spec §12): honest classification (copyleft + unknown flagged
for review), attribution generation, and a report that never declares the project
legally safe."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.licenses import service
from apps.licenses.classifier import classify
from apps.licenses.models import Dependency
from apps.organizations.models import Organization, Role
from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ClassifierTests(TestCase):
    def test_permissive_copyleft_and_unknown(self):
        self.assertEqual(classify("MIT")["category"], "permissive")
        self.assertEqual(classify("Apache-2.0")["flag"], "ok")
        self.assertEqual(classify("GPL-3.0")["category"], "strong_copyleft")
        self.assertEqual(classify("GPLv3")["flag"], "review")
        self.assertEqual(classify("LGPL-2.1")["category"], "weak_copyleft")  # before GPL
        self.assertEqual(classify("")["flag"], "unknown")
        self.assertEqual(classify("Weirdware 1.0")["category"], "unknown")


class ReportTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_import_from_context(self):
        ProjectContext(self.project).set(
            ContextKind.DEPENDENCY, "dependencies", title="Dependencies",
            content="django, requests", data={"dependencies": ["django", "requests"]})
        self.assertEqual(service.import_from_context(self.project), 2)
        self.assertEqual(service.import_from_context(self.project), 0)  # idempotent
        self.assertEqual(Dependency.objects.filter(project=self.project).count(), 2)

    def test_report_flags_copyleft_and_unknown_and_never_claims_safe(self):
        service.record_dependency(self.project, package="a", license="MIT")
        service.record_dependency(self.project, package="b", license="GPL-3.0")
        service.record_dependency(self.project, package="c")  # unknown license
        rep = service.report(self.project)
        self.assertEqual(rep["flags"]["ok"], 1)
        self.assertEqual(rep["flags"]["review"], 1)
        self.assertEqual(rep["flags"]["unknown"], 1)
        self.assertEqual(rep["needs_review"], 2)
        self.assertNotIn("legally safe", rep["note"].replace("not a determination that the project is legally safe", ""))

    def test_attribution_lists_dependencies(self):
        service.record_dependency(self.project, package="django", version="6.0", license="BSD-3-Clause")
        notice = service.attribution(self.project)
        self.assertIn("django 6.0", notice)
        self.assertIn("BSD-3-Clause", notice)


class LicenseApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="ApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_report_and_record(self):
        rec = self.client.post(reverse("licenses:report", args=[self.project.id]),
                               {"action": "record", "package": "django", "license": "BSD"},
                               content_type="application/json", **auth(self.owner))
        self.assertEqual(rec.status_code, 201)
        rep = self.client.get(reverse("licenses:report", args=[self.project.id]),
                              **auth(self.owner)).json()
        self.assertEqual(rep["total"], 1)
        self.assertIn("attribution", rep)

    def test_non_member_blocked(self):
        resp = self.client.get(reverse("licenses:report", args=[self.project.id]),
                               **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))


class LicenseWebTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="w@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_repository_page_shows_licenses_and_imports(self):
        ProjectContext(self.project).set(
            ContextKind.DEPENDENCY, "dependencies", title="Dependencies",
            content="django", data={"dependencies": ["django"]})
        self.client.force_login(self.owner)
        html = self.client.get(
            reverse("dashboard:project_repository", args=[self.project.id])).content.decode()
        self.assertIn("Dependencies &amp; licenses", html)
        self.client.post(reverse("dashboard:project_repository", args=[self.project.id]),
                         {"action": "import_licenses"})
        self.assertTrue(Dependency.objects.filter(project=self.project, package="django").exists())
