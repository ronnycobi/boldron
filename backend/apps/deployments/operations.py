"""Production Operations Center (spec §10).

A single, CUSTOMER-SAFE health view of a project's live application, composed from
the real runtime signals the platform already records — monitoring (uptime/latency),
analytics (traffic), deployments, background jobs, storage, the test & security
gates, and restore points. It invents nothing: every number comes from a real
record, and a signal with no data is reported as "unknown"/None, never a green fake.

Customer-safe (spec §10, §30): this exposes only application-level health — status,
uptime %, response time, traffic, deploy outcome, job counts, storage used. It never
exposes server names, container names, internal paths, stack traces, queues or any
infrastructure detail.
"""
from __future__ import annotations


def _website(project):
    return getattr(project, "website", None)


def _bytes_display(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _uptime(project):
    website = _website(project)
    if website is None:
        return None
    from apps.publishing import monitor
    s = monitor.uptime_summary(website)
    if not s.get("checks"):
        return None
    return {
        "current": s.get("current", "unknown"),
        "uptime_pct": s.get("uptime_pct"),
        "avg_response_ms": s.get("avg_response_ms"),
        "incidents": s.get("incidents", 0),
        "checks": s.get("checks", 0),
    }


def _traffic(project):
    website = _website(project)
    if website is None:
        return None
    from apps.publishing import analytics
    s = analytics.summary(website, days=30)
    return {"pageviews": s.get("pageviews", 0), "visitors": s.get("visitors", 0),
            "days": s.get("days", 30)}


def _deployments(project):
    latest = project.deployments.order_by("-created_at").first()
    return {
        "total": project.deployments.count(),
        "latest_status": latest.status if latest else None,
        "last_deployed_at": latest.created_at.isoformat() if latest else None,
        "environment": latest.environment if latest else None,
    }


def _jobs(project):
    from apps.jobs.models import Job
    counts = {Job.RUNNING: 0, Job.QUEUED: 0, Job.FAILED: 0, Job.COMPLETED: 0}
    for row in project.jobs.values("status"):
        s = row["status"]
        if s in counts:
            counts[s] += 1
    return {"running": counts[Job.RUNNING], "queued": counts[Job.QUEUED],
            "failed": counts[Job.FAILED], "completed": counts[Job.COMPLETED]}


def _storage(project):
    total = sum(f.size for f in project.stored_files.only("size"))
    return {"bytes": total, "display": _bytes_display(total)}


def _quality(project):
    from apps.security.ledger import latest_scan
    from apps.testing.runner import latest_run
    t = latest_run(project)
    sc = latest_scan(project)
    return {
        "tests": t.status if t else "not run",
        "security": sc.status if sc else "not scanned",
        "security_blocks": bool(sc and sc.blocks_deploy),
    }


def _status(uptime, deployments, jobs, quality) -> tuple[str, str]:
    """Overall production status — honest, derived from the real signals."""
    # Down: monitoring says the served snapshot is down right now.
    if uptime and uptime["current"] == "down":
        return "down", "Down"
    degraded = (
        (deployments["latest_status"] == "failed")
        or jobs["failed"] > 0
        or quality["security_blocks"]
        or quality["tests"] == "failed"
    )
    if degraded:
        return "degraded", "Needs attention"
    # Healthy only when we actually have a positive signal (monitoring up, or a
    # successful deploy). Otherwise we honestly don't know yet.
    if (uptime and uptime["current"] == "up") or deployments["latest_status"] == "succeeded":
        return "healthy", "Healthy"
    return "unknown", "Not deployed yet"


def operations_overview(project) -> dict:
    """The composed, customer-safe operations view for a project (spec §10)."""
    uptime = _uptime(project)
    deployments = _deployments(project)
    jobs = _jobs(project)
    quality = _quality(project)
    status, label = _status(uptime, deployments, jobs, quality)
    return {
        "project": {"id": project.id, "name": project.name},
        "status": status,
        "status_label": label,
        "uptime": uptime,
        "traffic": _traffic(project),
        "deployments": deployments,
        "jobs": jobs,
        "storage": _storage(project),
        "quality": quality,
        "rollback": {
            "restore_points": project.backups.count(),
            "available": project.backups.exists(),
        },
    }
