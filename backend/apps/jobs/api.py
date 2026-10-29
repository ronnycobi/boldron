"""Jobs API — enqueue work, poll status, read the result (spec §20)."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs import service
from apps.jobs.models import Job
from apps.organizations.access import organizations_for


class JobListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Job.objects.filter(organization__in=organizations_for(request.user))
        if request.query_params.get("project"):
            qs = qs.filter(project_id=request.query_params["project"])
        return Response([service.public_dict(j) for j in qs[:100]])

    def post(self, request):
        from apps.projects.models import Project

        org = get_object_or_404(organizations_for(request.user),
                                pk=request.data.get("organization"))
        project = None
        if request.data.get("project"):
            project = get_object_or_404(
                Project.objects.filter(organization=org), pk=request.data["project"])
        try:
            job = service.enqueue(
                request.data.get("kind", ""), organization=org, project=project,
                created_by=request.user, params=request.data.get("params") or {})
        except service.JobError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(service.public_dict(job), status=status.HTTP_201_CREATED)


class JobDetailView(APIView):
    """Poll one job's status, or read its result when complete."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        job = get_object_or_404(
            Job.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
        data = service.public_dict(job)
        if job.status == Job.COMPLETED:
            data["result"] = job.result
        return Response(data)
