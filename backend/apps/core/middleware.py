"""Response hardening for technology confidentiality.

Strips server/technology fingerprint headers from every response so the platform's
implementation (framework, language, runtime version) isn't advertised to clients.
Infrastructure (reverse proxy / WSGI server) should also be configured not to emit
a versioned `Server` header; this middleware is the application-layer backstop.
"""
from __future__ import annotations


class UserLocaleMiddleware:
    """Activate each signed-in user's preferred language and timezone (their
    account preferences). Blank preferences fall back to the platform defaults.
    Must run after AuthenticationMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.utils import timezone as tz
        from django.utils import translation

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            lang = getattr(user, "language", "")
            if lang:
                translation.activate(lang)
                request.LANGUAGE_CODE = lang
            tzname = getattr(user, "timezone", "")
            if tzname:
                try:
                    import zoneinfo
                    tz.activate(zoneinfo.ZoneInfo(tzname))
                except Exception:
                    tz.deactivate()
        try:
            return self.get_response(request)
        finally:
            translation.deactivate()


class DevCorsMiddleware:
    """Development-only CORS for local clients (e.g. the Flutter web build on
    another localhost port calling this API). ACTIVE ONLY WHEN settings.DEBUG is
    True and the Origin is a localhost/127.0.0.1 origin — it never relaxes CORS
    in production or for any non-local origin. Reflects the specific allowed
    origin (never '*' with credentials) and answers preflight requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _allowed(origin: str) -> bool:
        if not origin:
            return False
        from urllib.parse import urlparse

        host = urlparse(origin).hostname or ""
        return host in {"localhost", "127.0.0.1", "::1"}

    def __call__(self, request):
        from django.conf import settings

        origin = request.META.get("HTTP_ORIGIN", "")
        allow = settings.DEBUG and self._allowed(origin)

        # Short-circuit the CORS preflight so the browser proceeds.
        if allow and request.method == "OPTIONS" and "HTTP_ACCESS_CONTROL_REQUEST_METHOD" in request.META:
            from django.http import HttpResponse

            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if allow:
            response["Access-Control-Allow-Origin"] = origin
            response["Vary"] = "Origin"
            response["Access-Control-Allow-Credentials"] = "true"
            response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = (
                request.META.get("HTTP_ACCESS_CONTROL_REQUEST_HEADERS")
                or "Authorization, Content-Type, X-Request-Id"
            )
            response["Access-Control-Max-Age"] = "600"
        return response


class TechnologyConfidentialityMiddleware:
    # Headers that reveal the implementation stack. Removed if anything set them.
    FINGERPRINT_HEADERS = ("X-Powered-By", "X-Runtime", "X-AspNet-Version", "Via")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        for header in self.FINGERPRINT_HEADERS:
            if header in response:
                del response[header]
        # Neutralize a versioned Server header if present (e.g. "WSGIServer/.. Python/..").
        if response.get("Server"):
            response["Server"] = "server"
        return response
