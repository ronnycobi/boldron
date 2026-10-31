"""Localization API (spec §17-18) — one source of truth web + mobile consume.

Read locales, strings, coverage and per-locale bundles; add locales/strings and
set translations (owner/admin). The bundle is the deliverable an app loads for a
language — with missing strings honestly falling back to source and flagged.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.localization import service
from apps.localization.models import ProjectLocale, TranslationString
from apps.projects.access import project_for_read, require_manageable_project


def _overview(project) -> dict:
    default = service.default_code(project)
    return {
        "summary": service.summary(project),
        "locales": [{"id": l.id, "code": l.code, "name": l.name,
                     "is_default": l.is_default, "enabled": l.enabled, "rtl": l.rtl}
                    for l in project.locales.all()],
        "coverage": service.coverage(project),
        "strings": [{"id": s.id, "key": s.key, "source_text": s.source_text,
                     "description": s.description,
                     "translations": {t.locale: t.value for t in s.translations.all()}}
                    for s in project.translation_strings.all()[:500]],
        "default": default,
    }


class LocalizationView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_overview(project))


class LocaleListCreateView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        try:
            service.add_locale(project, code=request.data.get("code", ""),
                               name=request.data.get("name", ""),
                               make_default=bool(request.data.get("default")),
                               user=request.user)
        except service.LocalizationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_overview(project), status=201)


class LocaleView(APIView):
    def _locale(self, request, pk):
        locale = get_object_or_404(ProjectLocale.objects.select_related("project"), pk=pk)
        require_manageable_project(request.user, locale.project_id)
        return locale

    def post(self, request, pk):   # set default / enable-disable
        locale = self._locale(request, pk)
        if request.data.get("default"):
            service.set_default_locale(locale, user=request.user)
        elif "enabled" in request.data:
            locale.enabled = bool(request.data["enabled"])
            locale.save(update_fields=["enabled"])
        return Response(_overview(locale.project))

    def delete(self, request, pk):
        locale = self._locale(request, pk)
        project = locale.project
        try:
            service.remove_locale(locale, user=request.user)
        except service.LocalizationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_overview(project))


class StringListCreateView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        try:
            s = service.add_string(
                project, key=request.data.get("key", ""),
                source_text=request.data.get("source_text", ""),
                description=request.data.get("description", ""), user=request.user)
        except service.LocalizationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"id": s.id, "key": s.key}, status=201)


class TranslateView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        string = get_object_or_404(
            TranslationString, pk=request.data.get("string", 0), project=project)
        try:
            service.set_translation(string, request.data.get("locale", ""),
                                    request.data.get("value", ""), user=request.user)
        except service.LocalizationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_overview(project))


class BundleView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        code = request.query_params.get("locale") or service.default_code(project) or ""
        try:
            return Response(service.bundle(project, code))
        except service.LocalizationError as exc:
            return Response({"detail": str(exc)}, status=400)
