"""Consent API (spec §21, §60).

Cookie consent works before login (anonymous id) and after; marketing consent is
per authenticated user. Declining optional cookies is a first-class POST — the
same effort as accepting (no dark patterns).
"""
from __future__ import annotations

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.consent import service


def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")


def _subject(request):
    user = request.user if request.user.is_authenticated else None
    anon = "" if user else (request.query_params.get("anon_id")
                            or request.data.get("anon_id", "") if request.method == "POST"
                            else request.query_params.get("anon_id", ""))
    return user, (anon or "")


class CookieConsentView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        anon = request.query_params.get("anon_id", "")
        return Response(service.cookie_state(user=user, anon_id=anon))

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        anon = request.data.get("anon_id", "")
        cats = request.data.get("categories") or {}
        if not isinstance(cats, dict):
            return Response({"detail": "'categories' must be an object."}, status=400)
        try:
            service.record_cookie_consent(
                user=user, anon_id=anon, categories=cats,
                policy_version=request.data.get("policy_version", ""),
                method=request.data.get("method", "banner"),
                jurisdiction=request.data.get("jurisdiction", ""),
                ip_address=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""))
        except service.ConsentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(service.cookie_state(user=user, anon_id=anon), status=201)


class MarketingConsentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"opted_in": service.marketing_opted_in(request.user)})

    def post(self, request):
        service.set_marketing_consent(
            request.user, bool(request.data.get("opted_in")),
            source=request.data.get("source", "api"))
        return Response({"opted_in": service.marketing_opted_in(request.user)})
