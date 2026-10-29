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


class EnvVarListCreateView(APIView):
    """List a project's environment variables (members) or set one (managers).

    Secret values are never returned — reads mask them. Setting a key that
    already exists updates it (idempotent upsert)."""

    def get(self, request, pk):
        from apps.projects.access import project_for_read
        from apps.projects.env import EnvVarError, environments, list_vars, public_dict

        project = project_for_read(request.user, pk)
        env = request.query_params.get("environment")
        try:
            vars_ = list_vars(project, environment=env)
        except EnvVarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "environments": environments(),
            "variables": [public_dict(v) for v in vars_],
        })

    def post(self, request, pk):
        from apps.projects.access import require_manageable_project
        from apps.projects.env import EnvVarError, public_dict, set_var

        project = require_manageable_project(request.user, pk)
        try:
            var = set_var(
                project,
                request.data.get("key", ""),
                request.data.get("value", ""),
                is_secret=bool(request.data.get("is_secret", False)),
                environment=request.data.get("environment", "development"),
            )
        except EnvVarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from apps.settings.service import audit_change
        audit_change("project.env_set", actor=request.user,
                     organization=project.organization,
                     summary=f"{project.name}: set {var.key} ({var.environment})")
        return Response(public_dict(var), status=status.HTTP_201_CREATED)


class ProjectAiView(APIView):
    """Per-project AI preference (overrides the org's for this project's builds).
    Read open to members; change requires org management rights."""

    def get(self, request, pk):
        from apps.ai_providers.registry import generation_status
        from apps.projects import ai_settings as pai
        from apps.projects.access import project_for_read

        project = project_for_read(request.user, pk)
        return Response({
            "own": pai.own_preferences(project),
            "effective": pai.preferences_for(project),
            "options": pai.available_options(),
            "generation": generation_status(),
        })

    def patch(self, request, pk):
        from apps.projects import ai_settings as pai
        from apps.projects.access import require_manageable_project

        project = require_manageable_project(request.user, pk)
        try:
            pai.set_preferences(
                project,
                preferred_provider=request.data.get("preferred_provider", "") or "",
                preferred_model=request.data.get("preferred_model", "") or "",
                actor=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"own": pai.own_preferences(project)})


class ProjectCapabilitiesView(APIView):
    """The project's capability map (what the app composes), grouped with an
    honest built/coming split. Read-only; mobile reads the same data as web."""

    def get(self, request, pk):
        from apps.capabilities.analysis import capability_ids, summary
        from apps.projects.access import project_for_read

        project = project_for_read(request.user, pk)
        ids = project.capabilities or capability_ids(project.description or project.name)
        return Response(summary(ids))


class AnalyzeView(APIView):
    """Pre-build requirements analysis for a brief (spec §30)."""

    def post(self, request):
        from apps.capabilities.analysis import analyze

        return Response(analyze(request.data.get("brief", "") or ""))


class ProjectAnalyticsView(APIView):
    """Real analytics for a project (spec §22): traffic (visitors, page views,
    sources, conversions) and, for stores, revenue & orders. Figures come from
    real page-view and order records — never fabricated."""

    def get(self, request, pk):
        from apps.projects.access import project_for_read
        from apps.publishing import analytics as an

        project = project_for_read(request.user, pk)
        website = getattr(project, "website", None)
        try:
            days = max(7, min(90, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30
        if website is None:
            return Response({"has_site": False, "traffic": None, "commerce": None})
        return Response({
            "has_site": True,
            "days": days,
            "traffic": an.summary(website, days=days),
            "commerce": an.commerce_summary(website, days=days),
        })


class ProjectPaymentsView(APIView):
    """Payments surface for a project (spec §24): connected providers (honest),
    transaction history and a money summary. Same data as web."""

    def get(self, request, pk):
        from apps.projects.access import project_for_read
        from apps.publishing.ecommerce_service import payment_overview

        project = project_for_read(request.user, pk)
        return Response(payment_overview(project))


class ProjectRepositoryView(APIView):
    """Real local git state for the project (read-only)."""

    def get(self, request, pk):
        import os

        from apps.projects.access import project_for_read
        from apps.repositories.service import GitError, repo_for_project

        project = project_for_read(request.user, pk)
        repo = repo_for_project(project)
        info = {"initialized": repo.is_initialized, "files": 0, "branch": None,
                "remote_configured": bool(os.environ.get("GIT_REMOTE_TOKEN"))}
        if repo.is_initialized:
            try:
                info["files"] = len(repo.list_files())
                info["branch"] = repo.current_branch()
            except GitError:
                pass
        return Response(info)


class EnvVarDetailView(APIView):
    """Delete one environment variable (managers)."""

    def delete(self, request, pk, var_id):
        from apps.projects.access import require_manageable_project
        from apps.projects.env import delete_var

        project = require_manageable_project(request.user, pk)
        if not delete_var(project, var_id):
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
