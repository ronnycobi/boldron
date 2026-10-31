"""Business-rules API (spec §12-13) — one source of truth web + mobile consume.

Read rules + their honest enforced/documented status; create, update, change
status, import from project memory, and evaluate active rules against supplied
facts (a real deterministic run). Writes require owner/admin.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.business_rules import service
from apps.business_rules.engine import OPERATORS, evaluate
from apps.business_rules.models import BusinessRule
from apps.projects.access import project_for_read, require_manageable_project


def _rule_dict(r: BusinessRule) -> dict:
    return {
        "id": r.id, "name": r.name, "category": r.category,
        "category_label": r.get_category_display(),
        "description": r.description, "status": r.status,
        "status_label": r.get_status_display(),
        "definition": r.definition or {},
        "enforceable": r.is_enforceable,
        "requirement": r.requirement_id,
        "priority": r.priority,
    }


def _payload(project) -> dict:
    return {
        "summary": service.summary(project),
        "operators": list(OPERATORS),
        "rules": [_rule_dict(r) for r in project.business_rules.all()],
    }


class RuleListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_payload(project))

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        d = request.data
        requirement = None
        if d.get("requirement"):
            requirement = get_object_or_404(project.context_entries, pk=d["requirement"])
        try:
            rule = service.create(
                project, name=d.get("name", ""), description=d.get("description", ""),
                category=d.get("category", "other"), definition=d.get("definition") or {},
                requirement=requirement, priority=d.get("priority", 100),
                user=request.user)
        except service.RuleError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_rule_dict(rule), status=201)


class RuleDetailView(APIView):
    def _rule(self, request, pk, *, manage=False):
        rule = get_object_or_404(BusinessRule.objects.select_related("project"), pk=pk)
        if manage:
            require_manageable_project(request.user, rule.project_id)
        else:
            project_for_read(request.user, rule.project_id)
        return rule

    def get(self, request, pk):
        return Response(_rule_dict(self._rule(request, pk)))

    def patch(self, request, pk):
        rule = self._rule(request, pk, manage=True)
        try:
            service.update(rule, user=request.user, **request.data)
        except service.RuleError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_rule_dict(rule))


class RuleStatusView(RuleDetailView):
    def post(self, request, pk):
        rule = self._rule(request, pk, manage=True)
        try:
            service.set_status(rule, request.data.get("status", ""), user=request.user)
        except service.RuleError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_rule_dict(rule))


class RuleImportView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        created = service.import_from_context(project, user=request.user)
        return Response({**_payload(project), "imported": created})


class RuleEvaluateView(APIView):
    """Run the project's active enforceable rules against supplied facts — a real
    deterministic evaluation, useful to test what a rule set would decide."""

    def post(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        facts = request.data.get("facts")
        if not isinstance(facts, dict):
            return Response({"detail": "'facts' must be an object."}, status=400)
        return Response(evaluate(project, facts))
