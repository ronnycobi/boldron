"""Performance lifecycle (spec §41): record real samples, set budgets, and
compose an honest report from the measurements."""
from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone

from apps.audit.service import record as audit
from apps.performance.analysis import stats_for
from apps.performance.models import PerformanceBudget, PerformanceSample

# Cap how many samples one call can submit, and the analysis window.
MAX_BATCH = 1000
WINDOW_DAYS = 7
# Per-label cap when computing stats, so a hot endpoint can't dominate memory.
PER_LABEL_CAP = 2000


class PerformanceError(Exception):
    pass


def record_samples(project, samples, *, user=None) -> int:
    """Store real timing samples. Each: {label, duration_ms, kind?}. Returns how
    many were recorded; invalid rows are skipped, not faked."""
    if not isinstance(samples, list):
        raise PerformanceError("'samples' must be a list.")
    if len(samples) > MAX_BATCH:
        raise PerformanceError(f"Too many samples (max {MAX_BATCH}).")
    valid_kinds = set(PerformanceSample.Kind.values)
    rows = []
    for s in samples:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label", "")).strip()
        try:
            duration = int(s.get("duration_ms"))
        except (TypeError, ValueError):
            continue
        if not label or duration < 0:
            continue
        kind = s.get("kind", "api")
        if kind not in valid_kinds:
            kind = "other"
        rows.append(PerformanceSample(
            project=project, label=label[:200], kind=kind, duration_ms=duration))
    if rows:
        PerformanceSample.objects.bulk_create(rows)
    return len(rows)


def set_budget(project, *, label, threshold_ms, user=None) -> PerformanceBudget:
    label = (label or "").strip() or "*"
    try:
        threshold = int(threshold_ms)
    except (TypeError, ValueError):
        raise PerformanceError("Budget must be a whole number of milliseconds.")
    if threshold <= 0:
        raise PerformanceError("Budget must be greater than zero.")
    try:
        budget, _ = PerformanceBudget.objects.update_or_create(
            project=project, label=label[:200],
            defaults={"threshold_ms": threshold})
    except IntegrityError:
        raise PerformanceError("Could not save that budget.")
    audit("perf.budget", actor=user, organization=project.organization,
          target=f"project:{project.id}", summary=f"{label} <= {threshold}ms")
    return budget


def _budgets(project) -> dict:
    return {b.label: b.threshold_ms for b in project.perf_budgets.all()}


def report(project) -> dict:
    """Per-label stats over the recent window, with budget flags. Honest: computed
    only from recorded samples; empty when nothing has been measured."""
    since = timezone.now() - timedelta(days=WINDOW_DAYS)
    rows = (project.perf_samples.filter(recorded_at__gte=since)
            .values_list("label", "kind", "duration_ms"))
    by_label: dict[str, dict] = {}
    for label, kind, duration in rows:
        entry = by_label.setdefault(label, {"kind": kind, "durations": []})
        if len(entry["durations"]) < PER_LABEL_CAP:
            entry["durations"].append(duration)

    budgets = _budgets(project)
    default_budget = budgets.get("*")
    labels = []
    for label, entry in by_label.items():
        st = stats_for(entry["durations"])
        budget = budgets.get(label, default_budget)
        over = (budget is not None and st["p95"] is not None and st["p95"] > budget)
        labels.append({"label": label, "kind": entry["kind"], **st,
                       "budget": budget, "over_budget": over})
    labels.sort(key=lambda r: (r["p95"] or 0), reverse=True)

    all_durations = [d for e in by_label.values() for d in e["durations"]]
    return {
        "window_days": WINDOW_DAYS,
        "overall": stats_for(all_durations),
        "labels": labels,
        "slowest": labels[0]["label"] if labels else None,
        "over_budget": [r["label"] for r in labels if r["over_budget"]],
    }


def summary(project) -> dict:
    rep = report(project)
    return {
        "samples": project.perf_samples.count(),
        "labels": len(rep["labels"]),
        "p95": rep["overall"]["p95"],
        "over_budget": len(rep["over_budget"]),
    }
