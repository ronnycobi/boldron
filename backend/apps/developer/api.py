"""Developer platform API — org-scoped API keys + webhooks (spec §21/§22).

Managing keys/webhooks requires org management rights (has_perm('org.manage')).
Reading is allowed to any member. Secrets (an API key's plaintext, a webhook's
signing secret) are returned exactly once, on creation.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.developer.events import EVENTS, is_known
from apps.developer.models import ApiKey, Webhook
from apps.developer.serializers import (
    ApiKeySerializer,
    WebhookDeliverySerializer,
    WebhookSerializer,
)
from apps.organizations.access import organizations_for
from apps.organizations.permissions import has_perm


def _get_org(user, pk):
    return get_object_or_404(organizations_for(user), pk=pk)


def _require_manage(org, user):
    if not has_perm(user, org, "org.manage"):
        return Response(
            {"detail": "You need owner or admin rights to manage developer settings."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


class ApiKeyListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        org = _get_org(request.user, pk)
        keys = org.api_keys.all()
        return Response(ApiKeySerializer(keys, many=True).data)

    def post(self, request, pk):
        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"name": ["A name is required."]},
                            status=status.HTTP_400_BAD_REQUEST)
        key, plaintext = ApiKey.generate(org, name, created_by=request.user)
        from apps.settings.service import audit_change
        audit_change("developer.api_key_created", actor=request.user,
                     organization=org, summary=f"API key '{name}' created")
        data = ApiKeySerializer(key).data
        data["key"] = plaintext  # shown exactly once
        return Response(data, status=status.HTTP_201_CREATED)


class ApiKeyRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, key_id):
        from django.utils import timezone

        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        key = get_object_or_404(ApiKey, pk=key_id, organization=org)
        if key.is_active:
            key.revoked_at = timezone.now()
            key.save(update_fields=["revoked_at"])
            from apps.settings.service import audit_change
            audit_change("developer.api_key_revoked", actor=request.user,
                         organization=org, summary=f"API key '{key.name}' revoked")
        return Response(ApiKeySerializer(key).data)


class WebhookListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        org = _get_org(request.user, pk)
        return Response({
            "webhooks": WebhookSerializer(org.webhooks.all(), many=True).data,
            "available_events": [{"key": k, "description": v} for k, v in EVENTS.items()],
        })

    def post(self, request, pk):
        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        url = (request.data.get("url") or "").strip()
        if not url.startswith("https://"):
            return Response({"url": ["An https:// URL is required."]},
                            status=status.HTTP_400_BAD_REQUEST)
        events = request.data.get("events") or []
        if not isinstance(events, list) or any(not is_known(e) for e in events):
            return Response({"events": ["Unknown event in the subscription list."]},
                            status=status.HTTP_400_BAD_REQUEST)
        secret = Webhook.new_secret()
        webhook = Webhook.objects.create(
            organization=org, url=url, events=events, secret=secret,
            created_by=request.user,
        )
        from apps.settings.service import audit_change
        audit_change("developer.webhook_created", actor=request.user,
                     organization=org, summary=f"webhook → {url}")
        data = WebhookSerializer(webhook).data
        data["secret"] = secret  # shown exactly once
        return Response(data, status=status.HTTP_201_CREATED)


class WebhookDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, webhook_id):
        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        webhook = get_object_or_404(Webhook, pk=webhook_id, organization=org)
        webhook.delete()
        from apps.settings.service import audit_change
        audit_change("developer.webhook_deleted", actor=request.user,
                     organization=org, summary="webhook deleted")
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get(self, request, pk, webhook_id):
        org = _get_org(request.user, pk)
        webhook = get_object_or_404(Webhook, pk=webhook_id, organization=org)
        deliveries = webhook.deliveries.all()[:25]
        return Response({
            "webhook": WebhookSerializer(webhook).data,
            "deliveries": WebhookDeliverySerializer(deliveries, many=True).data,
        })
