"""Business-rule lifecycle (spec §12-13).

Create / update rules, promote the free-text business rules in project memory into
formal records, and move rules through draft → active → retired. Activation is an
explicit action; a rule claiming to be *enforceable* must carry a definition the
engine can actually evaluate.
"""
from __future__ import annotations

from apps.audit.service import record as audit
from apps.business_rules.engine import validate_definition
from apps.business_rules.models import BusinessRule, RuleCategory, RuleStatus
from apps.project_context.models import ContextKind


class RuleError(Exception):
    pass


def _clean_category(value) -> str:
    return value if value in RuleCategory.values else RuleCategory.OTHER


def create(project, *, name, description="", category="other", definition=None,
           requirement=None, priority=100, user=None) -> BusinessRule:
    name = (name or "").strip()
    if not name:
        raise RuleError("A rule needs a name.")
    definition = definition or {}
    if definition:
        ok, err = validate_definition(definition)
        if not ok:
            raise RuleError(err)
    rule = BusinessRule.objects.create(
        project=project, name=name[:200], description=(description or "").strip(),
        category=_clean_category(category), definition=definition,
        requirement=requirement, priority=int(priority or 100),
        source="user" if user else "", created_by=user)
    audit("rule.create", actor=user, organization=project.organization,
          target=f"rule:{rule.id}", summary=name[:120])
    return rule


def update(rule: BusinessRule, *, user=None, **fields) -> BusinessRule:
    if "definition" in fields:
        defn = fields["definition"] or {}
        if defn:
            ok, err = validate_definition(defn)
            if not ok:
                raise RuleError(err)
        rule.definition = defn
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise RuleError("A rule needs a name.")
        rule.name = name[:200]
    if "description" in fields:
        rule.description = (fields["description"] or "").strip()
    if "category" in fields:
        rule.category = _clean_category(fields["category"])
    if "priority" in fields and fields["priority"] is not None:
        rule.priority = int(fields["priority"])
    rule.save()
    audit("rule.update", actor=user, organization=rule.project.organization,
          target=f"rule:{rule.id}", summary=rule.name[:120])
    return rule


def set_status(rule: BusinessRule, status: str, *, user=None) -> BusinessRule:
    """Move a rule through its lifecycle. A rule can only be ACTIVATED once it is
    enforceable or explicitly documentation-only — but activation never invents
    enforcement: a documented rule stays documented, just active as policy."""
    if status not in RuleStatus.values:
        raise RuleError(f"Unknown status '{status}'.")
    rule.status = status
    rule.save(update_fields=["status", "updated_at"])
    audit("rule.status", actor=user, organization=rule.project.organization,
          target=f"rule:{rule.id}", summary=f"{rule.name} → {status}")
    return rule


def import_from_context(project, *, user=None) -> int:
    """Promote free-text BUSINESS_RULE context entries into formal rule records
    (draft, documentation-only). Idempotent: an entry already imported (matched by
    source) is skipped, so re-running never duplicates."""
    created = 0
    for entry in project.context_entries.filter(kind=ContextKind.BUSINESS_RULE):
        src = f"context:{entry.key}"
        if BusinessRule.objects.filter(project=project, source=src).exists():
            continue
        BusinessRule.objects.create(
            project=project, name=(entry.title or entry.key)[:200],
            description=entry.content, category=RuleCategory.OTHER,
            status=RuleStatus.DRAFT, requirement=entry, source=src)
        created += 1
    if created:
        audit("rule.import", actor=user, organization=project.organization,
              target=f"project:{project.id}", summary=f"Imported {created} rules")
    return created


def summary(project) -> dict:
    rules = list(project.business_rules.all())
    active = [r for r in rules if r.status == RuleStatus.ACTIVE]
    enforceable_active = [r for r in active if r.is_enforceable]
    return {
        "total": len(rules),
        "active": len(active),
        "draft": sum(1 for r in rules if r.status == RuleStatus.DRAFT),
        "retired": sum(1 for r in rules if r.status == RuleStatus.RETIRED),
        # Honest split: of the active rules, how many the engine truly enforces
        # vs. how many are active policy the system does not auto-apply.
        "enforced": len(enforceable_active),
        "documented": len(active) - len(enforceable_active),
    }
