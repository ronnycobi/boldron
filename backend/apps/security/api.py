"""Security-scan API (spec §8, §24) — one source of truth web + mobile consume.

Read a project's scan history + latest findings; run a scan (owner/admin). Results
are the real findings recorded by apps.security.ledger — never fabricated.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.access import project_for_read, require_manageable_project
from apps.security import ledger


def _scan_dict(s, *, findings=False) -> dict:
    data = {
        "id": s.id,
        "trigger": s.trigger,
        "status": s.status,
        "summary": s.summary,
        "high": s.high,
        "medium": s.medium,
        "low": s.low,
        "total": s.total,
        "files_scanned": s.files_scanned,
        "blocks_deploy": s.blocks_deploy,
        "created_at": s.created_at.isoformat(),
    }
    if findings:
        data["findings"] = [{
            "severity": f.severity, "category": f.category, "message": f.message,
            "path": f.path, "line": f.line,
        } for f in s.findings.all()[:200]]
    return data


class ProjectSecurityView(APIView):
    """GET the scan history + latest findings; POST runs a scan now."""

    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        latest = ledger.latest_scan(project)
        return Response({
            "ok": ledger.security_ok(project),
            "latest": _scan_dict(latest, findings=True) if latest else None,
            "scans": [_scan_dict(s) for s in project.security_scans.all()[:25]],
        })

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        scan = ledger.run_scan(project, trigger="manual", user=request.user)
        return Response(_scan_dict(scan, findings=True), status=201)
