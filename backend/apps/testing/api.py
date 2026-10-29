"""Test-run API (spec §8, §24) — one source of truth web + mobile consume.

Read the project's test-run history + latest status; trigger a new run (owner/admin).
Results are the real outcomes recorded by apps.testing.runner — never fabricated.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.access import project_for_read, require_manageable_project
from apps.testing import runner


def _run_dict(r) -> dict:
    return {
        "id": r.id,
        "trigger": r.trigger,
        "status": r.status,
        "summary": r.summary,
        "ran": r.ran,
        "failures": r.failures,
        "errors": r.errors,
        "note": r.note,
        "change": r.change_id,
        "created_at": r.created_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def _required_tests(project) -> list[str]:
    """The tests the most recent planned change says must pass (from the impact
    analyzer) — what a complete run should cover."""
    from apps.changes.impact import analyze_impact
    change = project.changes.exclude(plan={}).first()
    if change is None:
        return []
    return analyze_impact(change).get("required_tests", [])


class ProjectTestsView(APIView):
    """GET the test-run history + latest status; POST runs the suite now."""

    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        latest = runner.latest_run(project)
        return Response({
            "green": runner.tests_green(project),
            "required_tests": _required_tests(project),
            "latest": _run_dict(latest) if latest else None,
            "runs": [_run_dict(r) for r in project.test_runs.all()[:25]],
        })

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        run = runner.run_project_tests(project, trigger="manual", user=request.user)
        return Response(_run_dict(run), status=201)
