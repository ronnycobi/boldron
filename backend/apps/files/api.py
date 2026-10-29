"""Files API — upload, list, delete, and serve with real authorization.

Private files are served only to members of the owning organization; a missing
or unauthorized file answers 404 (no existence leak). Public files are served by
their unguessable key with no auth. Uploads are size/type validated by the
service before anything is written.
"""
from __future__ import annotations

import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.files import service
from apps.files.models import StoredFile
from apps.organizations.access import organizations_for


def _org_for(user, org_id):
    return get_object_or_404(organizations_for(user), pk=org_id)


class FileListCreateView(APIView):
    """List the caller's files (optionally for one org/project) or upload one."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StoredFile.objects.filter(
            organization__in=organizations_for(request.user)
        ).select_related("organization")
        org_id = request.query_params.get("organization")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        project_id = request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return Response([service.public_dict(f, request=request) for f in qs[:200]])

    def post(self, request):
        from apps.projects.models import Project

        org = _org_for(request.user, request.data.get("organization"))
        project = None
        if request.data.get("project"):
            project = get_object_or_404(
                Project.objects.filter(organization=org), pk=request.data["project"])
        try:
            sf = service.store(
                request.FILES.get("file"),
                organization=org, project=project, uploaded_by=request.user,
                is_public=str(request.data.get("is_public", "")).lower() in ("1", "true", "on", "yes"),
            )
        except service.FileError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(service.public_dict(sf, request=request),
                        status=status.HTTP_201_CREATED)


class FileDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        sf = get_object_or_404(
            StoredFile.objects.filter(organization__in=organizations_for(request.user)),
            pk=pk)
        service.delete_file(sf)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _serve(sf: StoredFile, *, thumb=False):
    field = sf.thumbnail if thumb else sf.file
    if not field:
        raise Http404
    try:
        field.open("rb")
    except Exception as exc:  # file missing on disk
        raise Http404 from exc
    ctype = ("image/jpeg" if thumb
             else sf.content_type or mimetypes.guess_type(sf.original_name)[0]
             or "application/octet-stream")
    resp = FileResponse(field, content_type=ctype)
    if not thumb:
        resp["Content-Disposition"] = f'inline; filename="{sf.original_name}"'
    return resp


class FileServeView(APIView):
    """Serve a file's bytes — private files only to authorized members."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        sf = get_object_or_404(StoredFile, pk=pk)
        if not service.can_access(request.user, sf):
            raise Http404  # no existence leak for files you can't see
        return _serve(sf)


class FileThumbView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        sf = get_object_or_404(StoredFile, pk=pk)
        if not service.can_access(request.user, sf):
            raise Http404
        return _serve(sf, thumb=True)


class PublicFileServeView(APIView):
    """Serve a public file by its unguessable key — no authentication."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, key):
        sf = get_object_or_404(StoredFile, public_key=key, is_public=True)
        return _serve(sf)
