"""Project Health Score (spec §30).

One composed, honest signal of how healthy a project is, built READ-ONLY from the
platform's real ledgers — security scans, test runs, incidents, acceptance
criteria and deployments. It invents nothing: each pillar reflects the latest
recorded fact, and a pillar with no evidence yet is `unknown` (never scored as
good). The overall score is the mean of the pillars that actually have a signal;
when nothing is measurable the score is None — "not enough signal yet" — rather
than a fabricated 100.

Customer-safe (spec §30): details are the customer's own posture in plain terms
(counts, pass/fail) — never file paths, stack, tools or internal infrastructure.
"""
from __future__ import annotations


def _pillar(key, label, status, score, detail):
    return {"key": key, "label": label, "status": status,
            "score": score, "detail": detail}


def _security_pillar(project) -> dict:
    from apps.security.ledger import latest_scan
    from apps.security.models import SecurityScanStatus
    scan = latest_scan(project)
    if scan is None:
        return _pillar("security", "Security", "unknown", None, "No security scan yet.")
    if scan.status == SecurityScanStatus.ERROR:
        return _pillar("security", "Security", "unknown", None,
                       "The last scan could not complete.")
    if scan.status == SecurityScanStatus.SKIPPED:
        return _pillar("security", "Security", "unknown", None, "No code to scan yet.")
    if scan.high:
        return _pillar("security", "Security", "poor", 0,
                       f"{scan.high} high-severity finding(s) to fix.")
    if scan.medium or scan.low:
        return _pillar("security", "Security", "fair", 70,
                       f"{scan.medium} medium · {scan.low} low finding(s).")
    return _pillar("security", "Security", "good", 100, "No security findings.")


def _tests_pillar(project) -> dict:
    from apps.testing.models import TestRunStatus
    from apps.testing.runner import latest_run
    run = latest_run(project)
    if run is None:
        return _pillar("tests", "Tests", "unknown", None, "No test run yet.")
    if run.status == TestRunStatus.PASSED:
        return _pillar("tests", "Tests", "good", 100, "Latest tests passed.")
    if run.status in (TestRunStatus.FAILED, TestRunStatus.ERROR):
        n = run.failures + run.errors
        detail = f"{n} failing." if n else "Latest run did not pass."
        return _pillar("tests", "Tests", "poor", 0, detail)
    return _pillar("tests", "Tests", "unknown", None, "Nothing runnable to test yet.")


def _incidents_pillar(project) -> dict:
    from apps.incidents.service import summary
    s = summary(project)
    if s["critical_open"]:
        return _pillar("incidents", "Incidents", "poor", 20,
                       f"{s['critical_open']} critical incident(s) open.")
    if s["open"]:
        return _pillar("incidents", "Incidents", "fair", 60,
                       f"{s['open']} incident(s) open.")
    return _pillar("incidents", "Incidents", "good", 100, "No open incidents.")


def _acceptance_pillar(project) -> dict:
    from apps.acceptance.service import summary
    s = summary(project)
    if s["total"] == 0:
        return _pillar("acceptance", "Acceptance", "unknown", None,
                       "No acceptance criteria yet.")
    if s["accepted"]:
        return _pillar("acceptance", "Acceptance", "good", 100, "All criteria met.")
    if s["failed"]:
        return _pillar("acceptance", "Acceptance", "poor", 30,
                       f"{s['failed']} criteria not met.")
    pct = s["met_pct"] or 0
    status = "fair" if pct >= 50 else "poor"
    return _pillar("acceptance", "Acceptance", status, pct,
                   f"{s['met']} of {s['total']} criteria met.")


def _deployment_pillar(project) -> dict:
    from apps.deployments.models import DeploymentStatus
    dep = project.deployments.order_by("-created_at").first()
    if dep is None:
        return _pillar("deployment", "Deployment", "unknown", None, "Not deployed yet.")
    env = dep.get_environment_display()
    if dep.status == DeploymentStatus.SUCCEEDED:
        return _pillar("deployment", "Deployment", "good", 100,
                       f"Last deploy to {env} succeeded.")
    if dep.status in (DeploymentStatus.FAILED, DeploymentStatus.CANCELLED):
        return _pillar("deployment", "Deployment", "poor", 0,
                       f"Last deploy to {env} {dep.get_status_display().lower()}.")
    return _pillar("deployment", "Deployment", "unknown", None,
                   f"A deploy to {env} is {dep.get_status_display().lower()}.")


_PILLARS = [_security_pillar, _tests_pillar, _incidents_pillar,
            _acceptance_pillar, _deployment_pillar]


def _band(score) -> str:
    if score is None:
        return "unknown"
    if score >= 80:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


def health_score(project) -> dict:
    """The project's composed health: an overall score (or None when nothing is
    measurable yet) plus the per-pillar breakdown it was derived from."""
    pillars = [fn(project) for fn in _PILLARS]
    scored = [p["score"] for p in pillars if p["score"] is not None]
    overall = round(sum(scored) / len(scored)) if scored else None
    band = _band(overall)
    if overall is None:
        headline = "Not enough signal yet — add a scan, tests or acceptance criteria."
    else:
        headline = {"good": "Healthy.", "fair": "Some attention needed.",
                    "poor": "Needs attention."}[band]
    return {
        "project": {"id": project.id, "name": project.name},
        "score": overall,
        "band": band,
        "headline": headline,
        "measured": len(scored),
        "pillars": pillars,
        # The pillars actively dragging health down, worst first — the "what to
        # fix" list, composed from real state only.
        "attention": [p for p in pillars if p["status"] in ("poor", "fair")],
    }


def health_band(project) -> str:
    """Reusable compact signal: good / fair / poor / unknown."""
    return health_score(project)["band"]
