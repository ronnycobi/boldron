"""Experiment lifecycle, deterministic assignment, and real-count results (§20)."""
from __future__ import annotations

import hashlib

from django.db import IntegrityError
from django.utils import timezone

from apps.audit.service import record as audit
from apps.experiments import stats
from apps.experiments.models import Assignment, Experiment, ExperimentStatus


class ExperimentError(Exception):
    pass


def _normalize_variants(variants) -> list[dict]:
    if not isinstance(variants, list) or len(variants) < 2:
        raise ExperimentError("An experiment needs at least two variants.")
    out, seen = [], set()
    for v in variants:
        if not isinstance(v, dict):
            raise ExperimentError("Each variant must be an object.")
        key = str(v.get("key", "")).strip()
        if not key:
            raise ExperimentError("Each variant needs a key.")
        if key in seen:
            raise ExperimentError(f"Duplicate variant key '{key}'.")
        seen.add(key)
        try:
            weight = float(v.get("weight", 1))
        except (TypeError, ValueError):
            raise ExperimentError(f"Variant '{key}' has an invalid weight.")
        if weight <= 0:
            raise ExperimentError(f"Variant '{key}' weight must be > 0.")
        out.append({"key": key[:100], "name": str(v.get("name", key))[:120],
                    "weight": weight})
    return out


def create(project, *, key, variants, name="", description="", metric="conversion",
           user=None) -> Experiment:
    key = (key or "").strip().lower()
    if not key:
        raise ExperimentError("An experiment needs a key.")
    variants = _normalize_variants(variants)
    try:
        exp = Experiment.objects.create(
            project=project, key=key[:100], name=name.strip()[:200],
            description=(description or "").strip(), variants=variants,
            metric=(metric or "conversion").strip()[:120], created_by=user)
    except IntegrityError:
        raise ExperimentError(f"An experiment with key '{key}' already exists.")
    audit("experiment.create", actor=user, organization=project.organization,
          target=f"experiment:{exp.id}", summary=key)
    return exp


def set_status(exp: Experiment, status: str, *, user=None) -> Experiment:
    if status not in ExperimentStatus.values:
        raise ExperimentError(f"Unknown status '{status}'.")
    exp.status = status
    exp.save(update_fields=["status", "updated_at"])
    audit("experiment.status", actor=user, organization=exp.project.organization,
          target=f"experiment:{exp.id}", summary=f"{exp.key} -> {status}")
    return exp


def _pick_variant(exp: Experiment, subject: str) -> str:
    """Stable weighted assignment: the same subject always lands in the same
    variant for the same experiment."""
    variants = exp.variants
    total = sum(v["weight"] for v in variants)
    digest = hashlib.md5(f"{exp.key}:{subject}".encode()).hexdigest()
    point = (int(digest[:8], 16) / 0xFFFFFFFF) * total
    cumulative = 0.0
    for v in variants:
        cumulative += v["weight"]
        if point <= cumulative:
            return v["key"]
    return variants[-1]["key"]


def assign(exp: Experiment, subject: str) -> str | None:
    """Assign a subject to a variant (idempotent). Only a RUNNING experiment
    assigns; otherwise returns None (honest — no assignment happened)."""
    subject = (subject or "").strip()
    if not subject or not exp.is_running:
        return None
    existing = Assignment.objects.filter(experiment=exp, subject=subject).first()
    if existing:
        return existing.variant
    variant = _pick_variant(exp, subject)
    try:
        Assignment.objects.create(experiment=exp, subject=subject, variant=variant)
    except IntegrityError:          # a race — fetch the winner's assignment
        return Assignment.objects.get(experiment=exp, subject=subject).variant
    return variant


def convert(exp: Experiment, subject: str) -> bool:
    """Mark a subject as converted (once). Returns whether a conversion was newly
    recorded. A subject that was never assigned does not convert."""
    subject = (subject or "").strip()
    a = Assignment.objects.filter(experiment=exp, subject=subject).first()
    if a is None or a.converted:
        return False
    a.converted = True
    a.converted_at = timezone.now()
    a.save(update_fields=["converted", "converted_at"])
    return True


def results(exp: Experiment) -> dict:
    """Per-variant real counts + an honest significance assessment."""
    counts = {v["key"]: {"exposures": 0, "conversions": 0} for v in exp.variants}
    for a in exp.assignments.all():
        c = counts.setdefault(a.variant, {"exposures": 0, "conversions": 0})
        c["exposures"] += 1
        if a.converted:
            c["conversions"] += 1
    variants = []
    for v in exp.variants:
        c = counts[v["key"]]
        rate = (c["conversions"] / c["exposures"]) if c["exposures"] else 0.0
        variants.append({
            "key": v["key"], "name": v["name"],
            "exposures": c["exposures"], "conversions": c["conversions"],
            "rate": rate, "rate_pct": round(rate * 100, 1)})
    return {"metric": exp.metric, "variants": variants,
            "assessment": stats.assess(variants)}


def summary(project) -> dict:
    exps = list(project.experiments.all())
    return {
        "total": len(exps),
        "running": sum(1 for e in exps if e.status == ExperimentStatus.RUNNING),
        "draft": sum(1 for e in exps if e.status == ExperimentStatus.DRAFT),
        "stopped": sum(1 for e in exps if e.status == ExperimentStatus.STOPPED),
    }
