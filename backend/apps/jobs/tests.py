from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import Organization, Role

User = get_user_model()


def auth(user):
    from apps.accounts.api import issue_tokens
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class JobRunnerTests(TestCase):
    """Jobs run off-request and report honest status — never a faked completion."""

    def setUp(self):
        self.org = Organization.objects.create(name="JobsOrg")
        self.user = User.objects.create_user(email="j@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_registered_handler_runs_and_completes_with_result(self):
        from apps.jobs import service

        @service.register("_t_ok", "Test OK")
        def _ok(job):
            job.set_progress(50)
            return {"answer": 42}

        job = service.enqueue("_t_ok", organization=self.org, created_by=self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.result, {"answer": 42})
        self.assertIsNotNone(job.finished_at)

    def test_handler_exception_fails_honestly(self):
        from apps.jobs import service

        @service.register("_t_boom", "Test boom")
        def _boom(job):
            raise RuntimeError("kaboom")

        job = service.enqueue("_t_boom", organization=self.org, created_by=self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")   # never "completed"
        self.assertIn("kaboom", job.error)
        self.assertEqual(job.result, {})

    def test_unknown_kind_rejected(self):
        from apps.jobs import service

        with self.assertRaises(service.JobError):
            service.enqueue("not-a-real-job", organization=self.org)

    def test_real_project_report_handler(self):
        from apps.jobs import service
        from apps.projects.models import Project

        project = Project.objects.create(
            organization=self.org, name="Shop",
            capabilities=["auth", "database", "ecommerce"])
        job = service.enqueue("project_report", organization=self.org,
                              project=project, created_by=self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.result["project"], "Shop")
        self.assertIn("E-commerce", job.result["capabilities"]["built"])

    def test_capability_available(self):
        from apps.capabilities.registry import get
        self.assertTrue(get("jobs").is_available)


class JobApiTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="JobApiOrg")
        self.user = User.objects.create_user(email="ja@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_enqueue_poll_and_result(self):
        from apps.projects.models import Project
        project = Project.objects.create(organization=self.org, name="App")
        create = self.client.post(
            reverse("jobs_api:list"),
            data={"kind": "account_export", "organization": self.org.id, "project": project.id},
            content_type="application/json", **auth(self.user))
        self.assertEqual(create.status_code, 201)
        jid = create.json()["id"]
        detail = self.client.get(reverse("jobs_api:detail", args=[jid]), **auth(self.user)).json()
        self.assertEqual(detail["status"], "completed")
        self.assertIn("result", detail)  # completed jobs expose the result
        self.assertEqual(detail["result"]["account"]["email"], "ja@x.com")

    def test_unknown_kind_is_400(self):
        resp = self.client.post(
            reverse("jobs_api:list"),
            data={"kind": "nope", "organization": self.org.id},
            content_type="application/json", **auth(self.user))
        self.assertEqual(resp.status_code, 400)

    def test_tenant_isolation(self):
        from apps.jobs.service import enqueue
        other = User.objects.create_user(email="jo@x.com", password="pw12345!")
        job = enqueue("account_export", organization=self.org, created_by=self.user)
        resp = self.client.get(reverse("jobs_api:detail", args=[job.id]), **auth(other))
        self.assertEqual(resp.status_code, 404)
