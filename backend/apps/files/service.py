"""File storage service: validate, store, process, authorize.

Everything here operates on real bytes and real permissions. Size and type are
checked before anything is written; a private file's bytes are only ever handed
out through can_access(). Image thumbnails are generated with Pillow and are
best-effort — never a blocker.
"""
from __future__ import annotations

import io

from django.conf import settings
from django.core.files.base import ContentFile

from apps.files.models import StoredFile

# 25 MB default; tune per deployment without a code change.
MAX_BYTES = getattr(settings, "FILE_MAX_BYTES", 25 * 1024 * 1024)
THUMB_MAX = 320  # px, longest edge

# Content types we accept, grouped into a friendly category. Anything else is
# rejected — generated apps and the platform never store arbitrary executables.
_CATEGORY = {
    StoredFile.CAT_IMAGE: {
        "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
    },
    StoredFile.CAT_DOCUMENT: {
        "application/pdf", "text/plain", "text/csv", "text/markdown",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/json",
    },
    StoredFile.CAT_VIDEO: {"video/mp4", "video/webm", "video/quicktime"},
    StoredFile.CAT_AUDIO: {"audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4"},
}
_ALLOWED = {ct for cats in _CATEGORY.values() for ct in cats}


class FileError(ValueError):
    """User-safe validation error."""


def _category_for(content_type: str) -> str:
    for cat, types in _CATEGORY.items():
        if content_type in types:
            return cat
    return StoredFile.CAT_OTHER


def store(fileobj, *, organization, project=None, uploaded_by=None,
          is_public: bool = False) -> StoredFile:
    """Validate and store an uploaded file. Raises FileError on a bad upload."""
    if fileobj is None:
        raise FileError("Choose a file to upload.")
    size = getattr(fileobj, "size", 0) or 0
    if size <= 0:
        raise FileError("That file is empty.")
    if size > MAX_BYTES:
        raise FileError(f"That file is too large (max {MAX_BYTES // (1024 * 1024)} MB).")
    content_type = (getattr(fileobj, "content_type", "") or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED:
        raise FileError("That file type isn't supported.")

    name = (getattr(fileobj, "name", "") or "file")[:255]
    sf = StoredFile(
        organization=organization, project=project, uploaded_by=uploaded_by,
        original_name=name, content_type=content_type,
        category=_category_for(content_type), size=size,
        is_public=bool(is_public), public_key=StoredFile.new_public_key(),
    )
    sf.file.save(name, fileobj, save=False)
    _process_image(sf, fileobj)
    sf.save()
    return sf


def _process_image(sf: StoredFile, fileobj) -> None:
    """Add width/height + a thumbnail for raster images (best-effort)."""
    if sf.category != StoredFile.CAT_IMAGE or sf.content_type == "image/svg+xml":
        return
    try:
        from PIL import Image

        fileobj.seek(0)
        img = Image.open(fileobj)
        sf.width, sf.height = img.width, img.height
        img = img.convert("RGB")
        img.thumbnail((THUMB_MAX, THUMB_MAX))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        sf.thumbnail.save(f"{sf.public_key[:12]}.jpg",
                          ContentFile(buf.getvalue()), save=False)
    except Exception:
        pass  # a thumbnail is a nicety; never fail the upload over it


def can_access(user, sf: StoredFile) -> bool:
    """A public file is readable by anyone; a private file only by a member of
    the owning organization."""
    if sf.is_public:
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return sf.organization.memberships.filter(user=user).exists()


def delete_file(sf: StoredFile) -> None:
    sf.file.delete(save=False)
    if sf.thumbnail:
        sf.thumbnail.delete(save=False)
    sf.delete()


def public_dict(sf: StoredFile, *, request=None) -> dict:
    from django.urls import reverse

    url = reverse("files_api:serve", args=[sf.id])
    public_url = (reverse("files_api:serve-public", args=[sf.public_key])
                  if sf.is_public else None)
    thumb = reverse("files_api:thumb", args=[sf.id]) if sf.thumbnail else None
    if request is not None:
        url = request.build_absolute_uri(url)
        public_url = request.build_absolute_uri(public_url) if public_url else None
        thumb = request.build_absolute_uri(thumb) if thumb else None
    return {
        "id": sf.id,
        "name": sf.original_name,
        "category": sf.category,
        "content_type": sf.content_type,
        "size": sf.size,
        "width": sf.width,
        "height": sf.height,
        "is_public": sf.is_public,
        "url": url,
        "public_url": public_url,
        "thumbnail_url": thumb,
        "created_at": sf.created_at.isoformat(),
    }
