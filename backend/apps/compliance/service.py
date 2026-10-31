"""Compliance lifecycle (spec §16): seed a framework's controls, auto-evidence
the ones the platform really provides, and let a person attest the rest."""
from __future__ import annotations

from django.utils import timezone

from apps.audit.service import record as audit
from apps.compliance.catalog import CATALOG
from apps.compliance.models import ComplianceControl, ControlStatus, Framework


class ComplianceError(Exception):
    pass


def seed_framework(project, framework: str, *, user=None) -> int:
    """Create any missing controls for a framework. Auto controls are evaluated
    from real facts immediately; the rest start pending. Idempotent."""
    if framework not in Framework.values:
        raise ComplianceError(f"Unknown framework '{framework}'.")
    created = 0
    for code, title, description, evaluator in CATALOG[framework]:
        if ComplianceControl.objects.filter(
                project=project, framework=framework, code=code).exists():
            continue
        status, evidence, auto = ControlStatus.PENDING, "", False
        if evaluator is not None:
            status, evidence = evaluator(project)
            auto = True
        ComplianceControl.objects.create(
            project=project, framework=framework, code=code, title=title,
            description=description, status=status, evidence=evidence, auto=auto)
        created += 1
    if created:
        audit("compliance.seed", actor=user, organization=project.organization,
              target=f"project:{project.id}", summary=f"{framework}: +{created}")
    return created


def refresh_auto(project) -> int:
    """Re-evaluate the platform-provided controls from current facts."""
    changed = 0
    by_code = {}
    for fw, items in CATALOG.items():
        for code, _t, _d, evaluator in items:
            if evaluator is not None:
                by_code[(fw, code)] = evaluator
    for ctrl in project.compliance_controls.filter(auto=True):
        evaluator = by_code.get((ctrl.framework, ctrl.code))
        if not evaluator:
            continue
        status, evidence = evaluator(project)
        if ctrl.status != status or ctrl.evidence != evidence:
            ctrl.status, ctrl.evidence = status, evidence
            ctrl.save(update_fields=["status", "evidence", "updated_at"])
            changed += 1
    return changed


def attest(control: ComplianceControl, status: str, *, evidence="", user=None) -> ComplianceControl:
    """A person records a control's status with evidence. This is a manual
    attestation, so it clears the auto flag — the record reflects a real decision."""
    if status not in ControlStatus.values:
        raise ComplianceError(f"Unknown status '{status}'.")
    if status in (ControlStatus.MET, ControlStatus.PARTIAL) and not (evidence or control.evidence).strip():
        raise ComplianceError("Evidence is required to mark a control met or partial.")
    control.status = status
    control.auto = False
    if evidence:
        control.evidence = evidence[:4000]
    control.attested_by = user
    control.attested_at = timezone.now()
    control.save()
    audit("compliance.attest", actor=user, organization=control.project.organization,
          target=f"control:{control.id}", summary=f"{control.code} -> {status}")
    return control


def _framework_score(controls) -> dict:
    applicable = [c for c in controls if c.status != ControlStatus.NOT_APPLICABLE]
    met = sum(1 for c in applicable if c.status == ControlStatus.MET)
    total = len(applicable)
    return {
        "total": len(controls), "applicable": total, "met": met,
        "partial": sum(1 for c in applicable if c.status == ControlStatus.PARTIAL),
        "pending": sum(1 for c in applicable if c.status == ControlStatus.PENDING),
        "not_met": sum(1 for c in applicable if c.status == ControlStatus.NOT_MET),
        "percent": round(met / total * 100) if total else None,
    }


def score(project) -> dict:
    controls = list(project.compliance_controls.all())
    by_fw = {}
    for c in controls:
        by_fw.setdefault(c.framework, []).append(c)
    frameworks = []
    all_applicable = all_met = 0
    for fw, items in by_fw.items():
        s = _framework_score(items)
        s["framework"] = fw
        s["label"] = Framework(fw).label
        frameworks.append(s)
        all_applicable += s["applicable"]
        all_met += s["met"]
    frameworks.sort(key=lambda f: f["framework"])
    return {
        "frameworks": frameworks,
        "overall_percent": round(all_met / all_applicable * 100) if all_applicable else None,
        "controls": len(controls),
    }
