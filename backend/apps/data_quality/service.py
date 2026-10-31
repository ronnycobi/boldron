"""Data-quality lifecycle (spec §9): datasets, rules, and real check runs."""
from __future__ import annotations

from django.db import IntegrityError

from apps.audit.service import record as audit
from apps.data_quality.engine import evaluate, validate_rule
from apps.data_quality.models import Dataset, DataQualityRule, DataQualityRun


class DataQualityError(Exception):
    pass


def add_dataset(project, *, key, name="", description="", user=None) -> Dataset:
    key = (key or "").strip().lower()
    if not key:
        raise DataQualityError("A dataset needs a key.")
    try:
        ds = Dataset.objects.create(
            project=project, key=key[:100], name=name.strip()[:200],
            description=(description or "").strip())
    except IntegrityError:
        raise DataQualityError(f"A dataset '{key}' already exists.")
    audit("dq.dataset.add", actor=user, organization=project.organization,
          target=f"dataset:{ds.id}", summary=key)
    return ds


def add_rule(dataset, *, field, check, params=None, severity="error", user=None) -> DataQualityRule:
    field = (field or "").strip()
    if not field:
        raise DataQualityError("A rule needs a field.")
    params = params or {}
    ok, err = validate_rule(check, params)
    if not ok:
        raise DataQualityError(err)
    if severity not in DataQualityRule.Severity.values:
        severity = "error"
    rule = DataQualityRule.objects.create(
        dataset=dataset, field=field[:120], check_type=check, params=params,
        severity=severity)
    audit("dq.rule.add", actor=user, organization=dataset.project.organization,
          target=f"dataset:{dataset.id}", summary=f"{field}:{check}")
    return rule


def _rule_specs(dataset):
    return [{"field": r.field, "check": r.check_type, "params": r.params,
             "severity": r.severity}
            for r in dataset.rules.filter(enabled=True)]


def check(dataset, rows, *, user=None) -> DataQualityRun:
    """Run the dataset's enabled rules against real rows and record the outcome."""
    if not isinstance(rows, list):
        raise DataQualityError("'rows' must be a list of records.")
    result = evaluate(_rule_specs(dataset), rows)
    run = DataQualityRun.objects.create(
        dataset=dataset, rows=result["rows"], score=result["score"],
        failing=result["failing"], results=result["rules"], created_by=user)
    return run


def summary(project) -> dict:
    datasets = list(project.datasets.all())
    rules = DataQualityRule.objects.filter(dataset__project=project).count()
    # latest score per dataset, where a check has been run
    scores = []
    for ds in datasets:
        last = ds.runs.first()
        if last and last.score is not None:
            scores.append(last.score)
    return {
        "datasets": len(datasets),
        "rules": rules,
        "checked": len(scores),
        "avg_score": round(sum(scores) / len(scores)) if scores else None,
    }
