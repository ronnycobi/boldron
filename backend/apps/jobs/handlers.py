"""Real background-job handlers.

Each does genuine work and returns a real result dict (stored on the Job). They
reuse existing services rather than reinventing them — a report reads real
analytics, an export reads real records.
"""
from __future__ import annotations

from apps.jobs.service import register


@register("project_report", "Project report")
def project_report(job) -> dict:
    """Compile a real report for a project: its capability map and (if it has a
    published site) traffic + commerce analytics over the requested window."""
    from apps.capabilities.analysis import capability_ids, summary as cap_summary
    from apps.publishing import analytics as an

    project = job.project
    if project is None:
        raise ValueError("This report needs a project.")
    days = int((job.params or {}).get("days", 30))

    job.set_progress(25)
    caps = cap_summary(project.capabilities or capability_ids(project.description or project.name))

    job.set_progress(60)
    website = getattr(project, "website", None)
    traffic = an.summary(website, days=days) if website else None
    commerce = an.commerce_summary(website, days=days) if website else None

    job.set_progress(90)
    return {
        "project": project.name,
        "generated_days": days,
        "capabilities": {
            "built": caps["available_names"],
            "coming": caps["planned_names"],
        },
        "traffic": {
            "visitors": traffic["sessions"] if traffic else 0,
            "page_views": traffic["pageviews"] if traffic else 0,
        } if traffic else None,
        "commerce": {
            "paid_orders": commerce["paid_orders"],
            "revenue_cents": commerce["revenue_cents"],
            "currency": commerce["currency"],
        } if commerce else None,
    }


@register("account_export", "Account data export")
def account_export(job) -> dict:
    """Export the requesting user's own account data (no secrets). Real records,
    not a placeholder."""
    from apps.settings.data_export import export_account

    user = job.created_by
    if user is None:
        raise ValueError("This export needs a signed-in user.")
    job.set_progress(50)
    return export_account(user)
