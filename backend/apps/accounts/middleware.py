"""Keep UserSession.last_active fresh without a write on every request.

Updates at most once every two minutes per session (gated by a session marker),
so the Security Center shows a real "last active" time cheaply. Best-effort —
never interferes with the response.
"""
from __future__ import annotations

import time


class SessionActivityMiddleware:
    INTERVAL = 120  # seconds

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            user = getattr(request, "user", None)
            key = getattr(request.session, "session_key", None)
            if user is not None and user.is_authenticated and key:
                now = time.time()
                if now - request.session.get("_last_touch", 0) > self.INTERVAL:
                    request.session["_last_touch"] = now
                    from apps.accounts.security import touch

                    touch(key)
        except Exception:
            pass
        return response
