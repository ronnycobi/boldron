"""Settings API — the single backend both web and mobile consume.

P0 exposes the control-center overview (status + alerts + the section map).
Later phases add the per-section read/write endpoints under /api/v1/settings/.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.settings import service


def _public_sections() -> dict:
    """The section map without web-only route names (mobile navigates by key)."""
    catalog = service.sections_catalog()
    cleaned: dict[str, list[dict]] = {}
    for scope, sections in catalog.items():
        cleaned[scope] = [
            {k: v for k, v in s.items() if k != "route"} for s in sections
        ]
    return cleaned


class SettingsOverviewView(APIView):
    """GET the signed-in user's settings overview: real alerts, account + org
    status, and the full section map with availability flags."""

    def get(self, request):
        data = service.overview(request.user)
        # Strip web route names from alerts/sections for API consumers.
        alerts = [
            {k: v for k, v in a.items() if k != "route"} for a in data["alerts"]
        ]
        return Response({
            "alerts": alerts,
            "account": data["account"],
            "organizations": data["organizations"],
            "sections": _public_sections(),
        })


class IntegrationStatusView(APIView):
    """The honest inventory of external integrations (connectors, payment gateways,
    SMS gateways) and their REAL env-gated connection state. Never the secret value."""

    def get(self, request):
        from apps.settings.connections import integration_status
        return Response(integration_status())


class SettingsSearchView(APIView):
    """Search settings sections across all scopes (?q=). Web route names are
    stripped — mobile navigates by scope+key."""

    def get(self, request):
        q = request.query_params.get("q", "")
        results = [
            {k: v for k, v in r.items() if k != "route"}
            for r in service.search(q)
        ]
        return Response({"query": q, "results": results})


class SecurityView(APIView):
    """Account Security Center (spec §9/§12/§13): status + active sessions +
    recent login history. Read-only; sensitive values are never returned."""

    def get(self, request):
        from apps.accounts import security

        user = request.user
        current = getattr(getattr(request, "session", None), "session_key", "") or ""
        sessions = security.active_sessions(user)
        history = [security.event_dict(e) for e in user.login_events.all()[:25]]
        return Response({
            "status": security.security_status(user),
            "sessions": [security.session_dict(s, current_key=current) for s in sessions],
            "history": history,
        })


class SessionRevokeView(APIView):
    """Revoke one of the user's own web sessions by its id."""

    def post(self, request, session_id):
        from apps.accounts import security

        ok = security.revoke_session_by_id(request.user, session_id, request=request)
        if not ok:
            return Response(
                {"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MfaEnrollView(APIView):
    """Begin MFA enrolment: returns the secret (for manual entry), the otpauth
    URI, and a QR as inline SVG. Enrolment isn't active until confirmed."""

    def post(self, request):
        from apps.accounts import mfa

        return Response(mfa.begin_enrollment(request.user))


class MfaConfirmView(APIView):
    """Confirm enrolment with a live code. On success MFA becomes enabled and the
    one-time recovery codes are returned (the only time they are ever shown)."""

    def post(self, request):
        from apps.accounts import mfa

        codes = mfa.confirm_enrollment(request.user, request.data.get("code") or "")
        if codes is None:
            return Response(
                {"detail": "That code isn't valid. Try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        service.audit_change("mfa.enabled", actor=request.user, summary="MFA enabled")
        return Response({"enabled": True, "recovery_codes": codes})


class MfaDisableView(APIView):
    """Turn MFA off. High-risk, so the current password must be re-entered."""

    def post(self, request):
        from apps.accounts import mfa

        if not request.user.check_password(request.data.get("password") or ""):
            return Response(
                {"detail": "Your current password is required to disable MFA."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not mfa.disable(request.user):
            return Response(
                {"detail": "MFA isn't enabled."}, status=status.HTTP_400_BAD_REQUEST
            )
        service.audit_change("mfa.disabled", actor=request.user, summary="MFA disabled")
        return Response({"enabled": False})


class MfaRecoveryCodesView(APIView):
    """Regenerate recovery codes (invalidates the old set). Re-auth required."""

    def post(self, request):
        from apps.accounts import mfa

        if not mfa.is_enabled(request.user):
            return Response(
                {"detail": "Enable MFA first."}, status=status.HTTP_400_BAD_REQUEST
            )
        if not request.user.check_password(request.data.get("password") or ""):
            return Response(
                {"detail": "Your current password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        codes = mfa.generate_recovery_codes(request.user)
        service.audit_change(
            "mfa.recovery_regenerated", actor=request.user,
            summary="Recovery codes regenerated",
        )
        return Response({"recovery_codes": codes})
