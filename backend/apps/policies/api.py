"""Policies API (spec §44) — one source of truth web + mobile consume.

Read custom policies + the platform's built-in guardrails; create, edit, enable
and disable (owner/admin). Policies govern real actions — a deploy block policy
genuinely stops the deploy.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.policies import service
from apps.policies.models import Policy, PolicyEffect, PolicyScope
from apps.projects.access import project_for_read, require_manageable_project


def _policy_dict(p: Policy) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "scope": p.scope, "effect": p.effect,
        "effect_label": p.get_effect_display(),
        "conditions": p.conditions or [], "message": p.message,
        "enabled": p.enabled,
    }


def _payload(project) -> dict:
    return {
        "summary": service.summary(project),
        "policies": [_policy_dict(p) for p in project.policies.all()],
        "built_in": service.built_in_guardrails(project),
        "scopes": [{"key": s.value, "label": s.label}
                   for s in PolicyScope if s in service.ENFORCED_SCOPES],
        "effects": [{"key": e.value, "label": e.label} for e in PolicyEffect],
    }


class PolicyListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_payload(project))

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        d = request.data
        try:
            policy = service.create(
                project, name=d.get("name", ""), scope=d.get("scope", "deploy"),
                effect=d.get("effect", "block"), description=d.get("description", ""),
                conditions=d.get("conditions", []), message=d.get("message", ""),
                user=request.user)
        except service.PolicyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_policy_dict(policy), status=201)


class PolicyDetailView(APIView):
    def _policy(self, request, pk, *, manage=False):
        policy = get_object_or_404(Policy.objects.select_related("project"), pk=pk)
        if manage:
            require_manageable_project(request.user, policy.project_id)
        else:
            project_for_read(request.user, policy.project_id)
        return policy

    def patch(self, request, pk):
        policy = self._policy(request, pk, manage=True)
        try:
            service.update(policy, user=request.user, **request.data)
        except service.PolicyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_policy_dict(policy))


class PolicyToggleView(PolicyDetailView):
    def post(self, request, pk):
        policy = self._policy(request, pk, manage=True)
        service.set_enabled(policy, bool(request.data.get("enabled")), user=request.user)
        return Response(_policy_dict(policy))
