"""Activity / notifications API (mobile/API client).

A read-only feed of real activity across the user's organizations, built over the
audit event stream (apps.audit) — build and deployment outcomes, changes,
publishes, orders, approvals, team and billing events. Customer-friendly: each
event is given a plain-language title, and no internal agent/model/infrastructure
detail is exposed.

Push delivery is intentionally NOT implemented here: it needs a push provider
(FCM/APNs) that isn't configured, and this platform never fabricates a channel it
can't actually deliver on. A mobile client polls this feed today; real push can
be layered on once a provider is connected.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.organizations.access import organizations_for

# Plain-language titles for the event actions a customer cares about. Anything
# not listed falls back to a humanized version of the action code.
_TITLES = {
    "build.completed": "Build finished",
    "build.failed": "Build failed",
    "change.approved": "Change approved",
    "change.implemented": "Change applied",
    "website.publish": "Website published",
    "website.publish_failed": "Publish didn’t go through",
    "website.rollback": "Website rolled back",
    "deployment.succeeded": "Deployment succeeded",
    "deployment.failed": "Deployment failed",
    "shop.product": "Product saved",
    "shop.order": "New order",
    "shop.refund": "Order refunded",
    "member.role_changed": "A teammate’s role changed",
    "member.removed": "A teammate was removed",
    "member.left": "A teammate left",
    "support.ticket": "Support ticket opened",
    "support.reply": "Support replied",
    "security.lockout": "Security: sign-in locked",
}

# Noise a customer shouldn't see in their activity feed.
_HIDDEN_PREFIXES = ("internal.",)


def _title(action: str) -> str:
    if action in _TITLES:
        return _TITLES[action]
    return action.replace(".", " ").replace("_", " ").strip().capitalize()


class NotificationFeedView(APIView):
    """Recent real activity across the user's organizations, newest first.
    Optional ?org=<id> to scope to one org, ?limit=N (default 50, max 200)."""

    def get(self, request):
        orgs = organizations_for(request.user)
        events = AuditEvent.objects.filter(organization__in=orgs).select_related(
            "actor", "organization"
        )
        org_id = request.query_params.get("org")
        if org_id:
            events = events.filter(organization_id=org_id)
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", 50))))
        except (TypeError, ValueError):
            limit = 50

        items = []
        for e in events.order_by("-created_at")[: limit * 2]:
            if any(e.action.startswith(p) for p in _HIDDEN_PREFIXES):
                continue
            items.append(
                {
                    "id": e.id,
                    "title": _title(e.action),
                    "detail": e.summary,
                    "organization": e.organization_id,
                    "organization_name": e.organization.name if e.organization else "",
                    "actor": getattr(e.actor, "display_name", "") or "System",
                    "created_at": e.created_at.isoformat(),
                }
            )
            if len(items) >= limit:
                break
        return Response({"notifications": items, "push_available": False})


class ProjectAlertsView(APIView):
    """Operational alert history for a project + the org's email-alert preference
    (spec §21). Owner/admin may toggle the preference."""

    def get(self, request, project_pk):
        from apps.projects.access import project_for_read
        from apps.notifications.alerts import recent
        from apps.notifications.models import AlertPreference
        project = project_for_read(request.user, project_pk)
        pref = AlertPreference.objects.filter(organization=project.organization).first()
        return Response({
            "email_enabled": pref.email_enabled if pref else True,
            "alerts": [{
                "id": a.id, "kind": a.kind, "severity": a.severity,
                "message": a.message, "emailed": a.emailed,
                "created_at": a.created_at.isoformat(),
            } for a in recent(project)],
        })

    def post(self, request, project_pk):
        from apps.projects.access import require_manageable_project
        from apps.notifications.alerts import set_email_enabled
        project = require_manageable_project(request.user, project_pk)
        set_email_enabled(project.organization, bool(request.data.get("email_enabled", True)))
        return Response({"email_enabled": bool(request.data.get("email_enabled", True))})


class SmsStatusView(APIView):
    """Honest SMS readiness: which gateways are connected (env-gated). In an
    environment with no SMS credentials every provider reads not-available — the
    truth, never a fake 'SMS enabled'."""

    def get(self, request):
        from apps.notifications import sms
        return Response({
            "configured": sms.is_configured(),
            "providers": sms.provider_status(),
        })


class SmsSendView(APIView):
    """Send one SMS through a connected gateway. Refuses with 503 when none is
    configured — it never reports a message as sent that was not dispatched."""

    def post(self, request):
        from apps.notifications import sms
        org_id = request.data.get("organization")
        organization = None
        if org_id:
            organization = organizations_for(request.user).filter(pk=org_id).first()
            if organization is None:
                return Response({"detail": "Unknown organization."}, status=400)
        try:
            log = sms.send_sms(to=request.data.get("to", ""),
                               text=request.data.get("text", ""),
                               organization=organization)
        except sms.SmsError as exc:
            # No provider connected / provider rejected — honest failure, not a fake send.
            code = 503 if not sms.is_configured() else 400
            return Response({"detail": str(exc)}, status=code)
        return Response({"id": log.id, "status": log.status, "provider": log.provider},
                        status=201)
