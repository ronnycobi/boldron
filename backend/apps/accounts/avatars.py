"""Avatar image handling, shared by the web account page and the mobile API.

Uploaded images are re-encoded to a small square JPEG, which normalizes the
dimensions and strips any metadata or embedded payload from the original file.
"""
from __future__ import annotations

MAX_BYTES = 3 * 1024 * 1024  # 3 MB


class AvatarError(ValueError):
    """Raised with a user-safe message when an upload can't be used."""


def save_avatar(user, fileobj) -> None:
    """Validate, re-encode and store ``fileobj`` as ``user.avatar``.

    Raises AvatarError (a ValueError) with a friendly message if the file is
    missing, too large, or not a readable image.
    """
    if fileobj is None:
        raise AvatarError("Choose an image to upload.")
    if getattr(fileobj, "size", 0) > MAX_BYTES:
        raise AvatarError("That image is too large (max 3 MB).")

    import io

    from django.core.files.base import ContentFile

    try:
        from PIL import Image, ImageOps

        img = ImageOps.exif_transpose(Image.open(fileobj)).convert("RGB")
        img = ImageOps.fit(img, (256, 256))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    except Exception as exc:  # unreadable/corrupt/non-image
        raise AvatarError("That file doesn't look like a valid image.") from exc

    if user.avatar:
        user.avatar.delete(save=False)
    user.avatar.save(f"user_{user.pk}.jpg", ContentFile(buf.getvalue()), save=True)
