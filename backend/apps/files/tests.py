import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Organization, Role

User = get_user_model()
_TMP = tempfile.mkdtemp()


def _png_bytes(w=40, h=30):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 130, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _upload(name="pic.png", content=None, ctype="image/png"):
    return SimpleUploadedFile(name, content if content is not None else _png_bytes(),
                              content_type=ctype)


def auth(user):
    from apps.accounts.api import issue_tokens
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


@override_settings(MEDIA_ROOT=_TMP)
class FileServiceTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.org = Organization.objects.create(name="FilesOrg")
        self.user = User.objects.create_user(email="f@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_rejects_oversize(self):
        from apps.files import service

        big = SimpleUploadedFile("big.png", b"x" * 10, content_type="image/png")
        big.size = service.MAX_BYTES + 1
        with self.assertRaises(service.FileError):
            service.store(big, organization=self.org)

    def test_rejects_unsupported_type(self):
        from apps.files import service

        bad = SimpleUploadedFile("run.sh", b"#!/bin/sh", content_type="application/x-sh")
        with self.assertRaises(service.FileError):
            service.store(bad, organization=self.org)

    def test_stores_image_with_metadata_and_thumbnail(self):
        from apps.files import service

        sf = service.store(_upload(), organization=self.org, uploaded_by=self.user)
        self.assertEqual(sf.category, "image")
        self.assertEqual((sf.width, sf.height), (40, 30))
        self.assertTrue(sf.thumbnail)  # generated

    def test_access_rules(self):
        from apps.files import service

        member = self.user
        other = User.objects.create_user(email="o@x.com", password="pw12345!")
        private = service.store(_upload(), organization=self.org)
        public = service.store(_upload(), organization=self.org, is_public=True)
        self.assertTrue(service.can_access(member, private))
        self.assertFalse(service.can_access(other, private))   # not a member
        self.assertFalse(service.can_access(None, private))    # anonymous
        self.assertTrue(service.can_access(other, public))     # public: anyone
        self.assertTrue(service.can_access(None, public))


@override_settings(MEDIA_ROOT=_TMP)
class FileApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.org = Organization.objects.create(name="ApiOrg")
        self.member = User.objects.create_user(email="m@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org.add_member(self.member, role=Role.OWNER)

    def test_upload_list_delete(self):
        up = self.client.post(reverse("files_api:list"),
                              {"organization": self.org.id, "file": _upload()},
                              **auth(self.member))
        self.assertEqual(up.status_code, 201)
        fid = up.json()["id"]
        listed = self.client.get(reverse("files_api:list"), **auth(self.member)).json()
        self.assertEqual(len(listed), 1)
        rm = self.client.delete(reverse("files_api:detail", args=[fid]), **auth(self.member))
        self.assertEqual(rm.status_code, 204)

    def test_private_file_denied_to_non_member(self):
        from apps.files import service

        sf = service.store(_upload(), organization=self.org)
        # Member can fetch the bytes...
        ok = self.client.get(reverse("files_api:serve", args=[sf.id]), **auth(self.member))
        self.assertEqual(ok.status_code, 200)
        # ...an outsider gets 404 (no existence leak), never the bytes.
        denied = self.client.get(reverse("files_api:serve", args=[sf.id]), **auth(self.outsider))
        self.assertEqual(denied.status_code, 404)

    def test_public_file_served_by_key_without_auth(self):
        from apps.files import service

        sf = service.store(_upload(), organization=self.org, is_public=True)
        resp = self.client.get(reverse("files_api:serve-public", args=[sf.public_key]))
        self.assertEqual(resp.status_code, 200)
        # A wrong/guessed key is a 404.
        self.assertEqual(
            self.client.get(reverse("files_api:serve-public", args=["nope"])).status_code, 404)

    def test_private_file_has_no_public_url(self):
        from apps.files import service

        sf = service.store(_upload(), organization=self.org)
        self.assertIsNone(service.public_dict(sf)["public_url"])

    def test_upload_rejects_bad_type_via_api(self):
        bad = SimpleUploadedFile("x.sh", b"#!/bin/sh", content_type="application/x-sh")
        resp = self.client.post(reverse("files_api:list"),
                                {"organization": self.org.id, "file": bad},
                                **auth(self.member))
        self.assertEqual(resp.status_code, 400)


@override_settings(MEDIA_ROOT=_TMP)
class FilesCapabilityTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)
        super().tearDownClass()

    def test_files_capability_now_available(self):
        from apps.capabilities.registry import get

        self.assertTrue(get("files").is_available)


@override_settings(MEDIA_ROOT=_TMP)
class FilesWebPageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        from apps.projects.models import Project
        self.org = Organization.objects.create(name="WebFilesOrg")
        self.user = User.objects.create_user(email="wf@x.com", password="pw12345678")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App")
        self.client.force_login(self.user)

    def test_upload_and_list_and_delete_via_page(self):
        from apps.files.models import StoredFile
        up = self.client.post(reverse("dashboard:files", args=[self.project.id]),
                              {"action": "upload", "file": _upload()})
        self.assertEqual(up.status_code, 302)
        self.assertEqual(StoredFile.objects.filter(project=self.project).count(), 1)
        sf = StoredFile.objects.get(project=self.project)
        self.client.post(reverse("dashboard:files", args=[self.project.id]),
                         {"action": "delete", "file": sf.id})
        self.assertFalse(StoredFile.objects.filter(id=sf.id).exists())

    def test_page_renders(self):
        html = self.client.get(reverse("dashboard:files", args=[self.project.id])).content.decode()
        self.assertIn("Files &amp; media", html)
