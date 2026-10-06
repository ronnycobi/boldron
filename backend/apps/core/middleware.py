"""Response hardening for technology confidentiality.

Strips server/technology fingerprint headers from every response so the platform's
implementation (framework, language, runtime version) isn't advertised to clients.
Infrastructure (reverse proxy / WSGI server) should also be configured not to emit
a versioned `Server` header; this middleware is the application-layer backstop.
"""
from __future__ import annotations


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
