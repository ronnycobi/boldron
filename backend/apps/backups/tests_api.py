"""Tests for the project backups API (mobile client)."""
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.repositories.service import repo_for_project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class BackupApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="member@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_create_list_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BOLDRON_WORKSPACES_ROOT=tmp):
                repo = repo_for_project(self.project)
                repo.init()
                repo.write_files({"a.py": "x = 1\n"})
                repo.commit("v1")

                created = self.client.post(
                    reverse("backups:list", args=[self.project.id]),
                    data={"label": "Before payments"},
                    content_type="application/json",
                    **auth(self.owner),
                )
                self.assertEqual(created.status_code, 201)
                self.assertTrue(created.json()["commit_sha"])
                backup_id = created.json()["id"]

                listed = self.client.get(
                    reverse("backups:list", args=[self.project.id]), **auth(self.member)
                )
                self.assertEqual(len(listed.json()), 1)

                repo.write_files({"b.py": "y = 2\n"})
                repo.commit("v2")
                restore = self.client.post(
                    reverse("backups:restore", args=[backup_id]), **auth(self.owner)
                )
                self.assertEqual(restore.status_code, 200)
                self.assertNotIn("b.py", repo.list_files())  # rolled back for real

    def test_create_without_repo_is_clean_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BOLDRON_WORKSPACES_ROOT=tmp):
                resp = self.client.post(
                    reverse("backups:list", args=[self.project.id]),
                    data={"label": "x"},
                    content_type="application/json",
                    **auth(self.owner),
                )
                self.assertEqual(resp.status_code, 400)

    def test_member_cannot_create(self):
        resp = self.client.post(
            reverse("backups:list", args=[self.project.id]),
            data={"label": "x"},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)
