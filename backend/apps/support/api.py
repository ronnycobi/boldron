"""Customer support API (mobile/API client).

The tenant-facing help desk over apps.support services — list and open tickets,
read a thread, and reply. Staff-only notes (internal messages) are never exposed,
and the staff desk operations (assign, set status, internal notes) stay on the
staff side. Same tickets and SLA as the web Help & Support.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.access import organizations_for
from apps.support import service
from apps.support.models import SupportTicket


def _ticket_dict(t: SupportTicket, *, thread=False) -> dict:
    data = {
        "id": t.id,
        "number": t.number,
        "subject": t.subject,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "organization": t.organization_id,
        "sla_state": t.sla_state,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }
    if thread:
        # Customer view: public messages only — internal staff notes are hidden.
        data["messages"] = [
            {
                "id": m.id,
                "body": m.body,
                "author": getattr(m.author, "display_name", "") or "Support",
                "from_staff": bool(getattr(m.author, "is_staff", False)),
                "created_at": m.created_at.isoformat(),
            }
            for m in t.messages.filter(internal=False).select_related("author").order_by("created_at")
        ]
    return data


class TicketListCreateView(APIView):
    def get(self, request):
        tickets = SupportTicket.objects.filter(
            organization__in=organizations_for(request.user)
        ).order_by("-updated_at")
        return Response([_ticket_dict(t) for t in tickets])

    def post(self, request):
        org = organizations_for(request.user).filter(
            pk=request.data.get("organization")
        ).first()
        if org is None:
            # Default to the user's first organization if none specified.
            org = organizations_for(request.user).order_by("id").first()
        if org is None:
            return Response(
                {"detail": "Join or create an organization before opening a ticket."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        subject = (request.data.get("subject") or "").strip()
        if not subject:
            return Response({"subject": ["A subject is required."]},
                            status=status.HTTP_400_BAD_REQUEST)
        ticket = service.create_ticket(
            organization=org, user=request.user, subject=subject,
            body=request.data.get("body") or "",
            category=request.data.get("category") or "question",
            priority=request.data.get("priority") or "normal",
        )
        return Response(_ticket_dict(ticket, thread=True), status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    def _ticket(self, request, pk):
        return get_object_or_404(
            SupportTicket.objects.filter(organization__in=organizations_for(request.user)),
            pk=pk,
        )

    def get(self, request, pk):
        return Response(_ticket_dict(self._ticket(request, pk), thread=True))


class TicketReplyView(APIView):
    def post(self, request, pk):
        ticket = get_object_or_404(
            SupportTicket.objects.filter(organization__in=organizations_for(request.user)),
            pk=pk,
        )
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"body": ["A message is required."]},
                            status=status.HTTP_400_BAD_REQUEST)
        # A customer reply is always public and never a staff/internal note.
        service.add_message(ticket, author=request.user, body=body,
                            internal=False, from_staff=False)
        return Response(_ticket_dict(ticket, thread=True))


class SupportMetaView(APIView):
    """Categories and priorities for the compose form."""

    def get(self, request):
        return Response(
            {
                "categories": [{"value": v, "label": lbl} for v, lbl in SupportTicket.CATEGORIES],
                "priorities": [{"value": v, "label": lbl} for v, lbl in SupportTicket.PRIORITIES],
            }
        )
