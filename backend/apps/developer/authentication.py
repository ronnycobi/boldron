"""API-key authentication for the platform API.

Additive to the existing JWT + session auth: a request may present an API key via
`Authorization: Api-Key <key>` (or the `X-API-Key` header) instead of a Bearer
token. The key authenticates as the user who created it, so all existing tenant
scoping (which filters by the user's organizations) applies unchanged — the key
can only reach what its creator can. This keeps the mobile/web flows untouched.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.developer.models import ApiKey


class ApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Api-Key"

    def _raw_key(self, request) -> str | None:
        header = authentication.get_authorization_header(request).decode("latin1")
        if header:
            parts = header.split()
            if len(parts) == 2 and parts[0].lower() == self.keyword.lower():
                return parts[1]
        return request.META.get("HTTP_X_API_KEY") or None

    def authenticate(self, request):
        raw = self._raw_key(request)
        if not raw:
            return None  # fall through to the other authenticators

        key = ApiKey.resolve(raw)
        if key is None:
            raise exceptions.AuthenticationFailed("Invalid or revoked API key.")

        user = key.created_by
        if user is None or not user.is_active:
            raise exceptions.AuthenticationFailed(
                "The user behind this API key is no longer active."
            )

        # Best-effort last-used stamp (never block the request on it).
        ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return (user, key)
