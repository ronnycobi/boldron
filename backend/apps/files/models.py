"""File & media storage (spec §17) — a real, reusable platform capability.

Files are tenant-scoped (to an organization, optionally a project) and are
either private (served only to members of the owning organization) or public
(served to anyone who has the unguessable link). Only metadata and the stored
bytes are kept — nothing is faked, and a private file is never served without
authorization (enforced in the serving views, not by hiding a link).

Images get width/height metadata and a small thumbnail, generated with Pillow at
upload time (best-effort; a non-image or a decode failure simply has none).
"""
from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.organizations.models import Organization


def _upload_to(instance, filename):
    # MEDIA_ROOT/files/<org>/<random>/<original name>. The random segment avoids
    # collisions and guessing; the name is kept for a friendly download.
    return f"files/{instance.organization_id}/{secrets.token_hex(8)}/{filename}"


def _thumb_to(instance, filename):
    return f"files/{instance.organization_id}/thumbs/{secrets.token_hex(8)}.jpg"


class StoredFile(models.Model):
    CAT_IMAGE, CAT_DOCUMENT, CAT_VIDEO, CAT_AUDIO, CAT_OTHER = (
        "image", "document", "video", "audio", "other")

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="stored_files")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, null=True, blank=True,
        related_name="stored_files")
    file = models.FileField(upload_to=_upload_to, max_length=500)
    thumbnail = models.ImageField(upload_to=_thumb_to, max_length=500, null=True, blank=True)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True)
    category = models.CharField(max_length=12, default=CAT_OTHER)
    size = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    is_public = models.BooleanField(default=False)
    # Unguessable key for public links (so a public file isn't enumerable by id).
    public_key = models.CharField(max_length=43, unique=True, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_files")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def __str__(self):
        return f"{self.original_name} ({self.organization_id})"

    @staticmethod
    def new_public_key() -> str:
        return secrets.token_urlsafe(32)

    @property
    def is_image(self) -> bool:
        return self.category == self.CAT_IMAGE
