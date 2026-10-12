from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.access import manageable_organizations_for, organizations_for
from apps.projects.models import Project
from apps.projects.serializers import ProjectSerializer


class ProjectListCreateView(generics.ListCreateAPIView):
    """List projects across the user's organizations; create in a managed org."""

    serializer_class = ProjectSerializer

    def get_queryset(self):
        return (
            Project.objects.filter(
                organization__in=organizations_for(self.request.user)
            )
            .select_related("organization")
            .distinct()
        )

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        # Every project starts with a default working environment.
        project.ensure_default_workspace()


class ProjectDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve or update a project the user can access (membership required)."""

    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.filter(
            organization__in=organizations_for(self.request.user)
        ).select_related("organization")


# --- The build loop ---------------------------------------------------------

def _user_project(user, pk):
    return (
        Project.objects.filter(organization__in=organizations_for(user))
        .select_related("organization")
        .filter(pk=pk)
        .first()
    )


def _can_manage(project, user) -> bool:
    return manageable_organizations_for(user).filter(pk=project.organization_id).exists()


class BuildView(APIView):
    """Start a build from a plain-language brief — the mobile equivalent of the
    web builder's 'What do you want to build?'. Creates the project (name +
    default stack), seeds its requirement, and runs the agent pipeline. The
    build is gated on a verified email, exactly like the web."""

    def post(self, request):
        from apps.ai_providers.registry import build_readiness
        from apps.organizations.access import manageable_organizations_for
        from apps.projects.builds import create_and_start_build

        if not request.user.email_verified:
            return Response(
                {"detail": "Verify your email before starting a build."},
                status=status.HTTP_403_FORBIDDEN,
            )
        brief = (request.data.get("brief") or "").strip()
        if not brief:
            return Response(
                {"brief": ["Describe what you want to build."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org_id = request.data.get("organization")
        manageable = manageable_organizations_for(request.user)
        if org_id:
            org = manageable.filter(pk=org_id).first()
            if org is None:
                return Response(
                    {"organization": ["You can't create a project in that organization."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            org = manageable.order_by("id").first()
            if org is None:
                from apps.organizations.models import Organization, Role

                org = Organization.objects.create(
                    name=f"{request.user.short_name}'s workspace", created_by=request.user
                )
                org.add_member(request.user, role=Role.OWNER)

        project = create_and_start_build(org, brief, request.user)
        readiness = build_readiness()
        return Response(
            {
                "project": ProjectSerializer(project, context={"request": request}).data,
                "demo_mode": not readiness["ready"],
                "readiness": readiness["message"],
            },
            status=status.HTTP_201_CREATED,
        )


class BuildStatusView(APIView):
    """Live build status for a project: overall state, progress %, each step's
    status, the credit snapshot, and whether it fell back to offline demo mode.
    This is what a mobile build screen polls. Customer-friendly language only —
    no agent/model/infrastructure detail is exposed."""

    def get(self, request, pk):
        from apps.projects.builds import (
            credit_summary,
            project_progress,
            project_state,
            ran_on_stub,
        )

        project = _user_project(request.user, pk)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        steps = [
            {
                "key": t.agent_key,
                "status": t.status,
                "detail": (t.messages[-1] if t.messages else (t.error or "")),
            }
            for t in project.agent_tasks.order_by("created_at")
        ]
        credits = credit_summary(project)
        # Decimals aren't JSON-native; render the money/credit fields as strings.
        credits = {
            k: (str(v) if hasattr(v, "quantize") else v) for k, v in credits.items()
        }
        return Response(
            {
                "project_id": project.id,
                "state": project_state(project),
                "progress": project_progress(project),
                "steps": steps,
                "demo_mode": ran_on_stub(project),
                "credits": credits,
            }
        )
