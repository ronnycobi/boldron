"""Internal staff console — the platform's cross-tenant operations cockpit.

Read-first: every page surfaces real platform state (no fabrication). Unlike the
customer dashboard, this is where the machinery is legitimately visible —
orchestrator activity, model routing, and unit economics — because the audience
is the platform staff, not customers.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.models import User
from apps.changes.models import ChangeRequest
from apps.console.access import staff_required
from apps.credits.models import CreditAccount, UsageRecord
from apps.deployments.models import Deployment
from apps.marketing.models import ContactMessage
from apps.orchestrator.models import TERMINAL_STATUSES, AgentTask, TaskStatus
from apps.organizations.models import Membership, Organization
from apps.projects.models import Project

_MONEY = DecimalField(max_digits=16, decimal_places=4)


def _zero():
    return Coalesce(Sum("cost_usd"), Decimal("0"), output_field=_MONEY)


def _usage_totals(qs=None):
    qs = UsageRecord.objects.all() if qs is None else qs
    agg = qs.aggregate(
        cost=Coalesce(Sum("cost_usd"), Decimal("0"), output_field=_MONEY),
        credits=Coalesce(Sum("credits_charged"), Decimal("0"), output_field=_MONEY),
        tokens=Coalesce(Sum("total_tokens"), 0),
    )
    return agg


def _open_ticket_count() -> int:
    from apps.support.models import OPEN_STATUSES, SupportTicket
    return SupportTicket.objects.filter(status__in=OPEN_STATUSES).count()


@staff_required
def overview(request):
    active_statuses = [s for s in TaskStatus.values if s not in TERMINAL_STATUSES]
    totals = _usage_totals()

    completed = AgentTask.objects.filter(status=TaskStatus.COMPLETED).count()
    failed = AgentTask.objects.filter(status=TaskStatus.FAILED).count()
    finished = completed + failed
    success_rate = round(completed / finished * 100) if finished else None

    stats = {
        "orgs": Organization.objects.count(),
        "users": User.objects.count(),
        "projects": Project.objects.count(),
        "builds": AgentTask.objects.count(),
        "active_tasks": AgentTask.objects.filter(status__in=active_statuses).count(),
        "success_rate": success_rate,
        "deployments": Deployment.objects.count(),
        "cost_usd": totals["cost"],
        "credits_charged": totals["credits"],
        "open_leads": ContactMessage.objects.count(),
        "open_tickets": _open_ticket_count(),
    }

    from apps.console.health import all_ok, system_health
    health = system_health()
    from apps.ai_providers.registry import generation_status
    ai_status = generation_status()

    # Live activity: the real audit trail, newest first.
    from apps.audit.models import AuditEvent
    activity = (
        AuditEvent.objects.select_related("actor", "organization").order_by("-created_at")[:12]
    )
    recent_orgs = Organization.objects.order_by("-created_at")[:6]
    awaiting = AgentTask.objects.filter(status=TaskStatus.WAITING_FOR_APPROVAL).count()
    return render(request, "console/overview.html", {
        "active": "overview", "stats": stats, "ai_status": ai_status,
        "health": health, "health_ok": all_ok(health),
        "activity": activity, "recent_orgs": recent_orgs, "awaiting": awaiting,
    })


@staff_required
def organizations(request):
    rows = (
        Organization.objects.annotate(
            n_members=Count("memberships", distinct=True),
            n_projects=Count("projects", distinct=True),
        )
        .select_related()
        .order_by("-created_at")
    )
    accounts = {a.organization_id: a for a in CreditAccount.objects.all()}
    spend = {
        r["organization"]: r["c"]
        for r in UsageRecord.objects.values("organization").annotate(c=_zero())
    }
    data = [
        {"org": o, "account": accounts.get(o.id), "spend": spend.get(o.id, Decimal("0"))}
        for o in rows
    ]
    return render(request, "console/organizations.html", {"active": "orgs", "rows": data})


@staff_required
def organization_detail(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    from apps.governance import service as gov
    from apps.governance.models import AccountStatus, Appeal
    if request.method == "POST":
        from django.contrib import messages
        from django.shortcuts import redirect
        action = request.POST.get("action")
        try:
            if action == "set_status":
                gov.set_status(org, request.POST.get("status", ""),
                               reason=request.POST.get("reason", ""),
                               policy_section=request.POST.get("policy_section", ""),
                               actor=request.user)
                messages.success(request, "Account status updated.")
            elif action == "decide_appeal":
                appeal = get_object_or_404(Appeal, pk=request.POST.get("appeal", 0), organization=org)
                gov.decide_appeal(appeal, request.POST.get("outcome", ""),
                                  resolution=request.POST.get("resolution", ""),
                                  reviewer=request.user)
                messages.success(request, "Appeal decided.")
        except gov.GovernanceError as exc:
            messages.error(request, str(exc))
        return redirect("console:org", pk=pk)
    members = Membership.objects.filter(organization=org).select_related("user")
    projects = Project.objects.filter(organization=org).order_by("-created_at")
    account = CreditAccount.objects.filter(organization=org).first()
    totals = _usage_totals(UsageRecord.objects.filter(organization=org))
    recent = UsageRecord.objects.filter(organization=org).order_by("-created_at")[:15]
    from apps.credits.services import daily_usd_cap, spent_today
    cap = daily_usd_cap(account) if account else None
    return render(request, "console/organization_detail.html", {
        "active": "orgs", "org": org, "members": members, "projects": projects,
        "account": account, "totals": totals, "recent_usage": recent,
        "spent_today": spent_today(org), "daily_cap": cap,
        "account_status": gov.current_status(org),
        "account_statuses": AccountStatus.choices,
        "account_history": gov.history(org)[:10],
        "appeals": org.appeals.all()[:10],
        "appeal_outcomes": Appeal.Outcome.choices,
    })


@staff_required
def users(request):
    rows = (
        User.objects.annotate(n_orgs=Count("memberships", distinct=True))
        .order_by("-date_joined")
    )
    return render(request, "console/users.html", {
        "active": "users", "rows": rows,
        "staff_count": User.objects.filter(is_staff=True).count(),
    })


@staff_required
def projects(request):
    rows = (
        Project.objects.select_related("organization", "created_by")
        .annotate(
            n_tasks=Count("agent_tasks", distinct=True),
            n_done=Count("agent_tasks", filter=Q(agent_tasks__status=TaskStatus.COMPLETED), distinct=True),
        )
        .order_by("-created_at")
    )
    return render(request, "console/projects.html", {"active": "projects", "rows": rows})


@staff_required
def tasks(request):
    status = request.GET.get("status") or ""
    qs = AgentTask.objects.select_related("project", "project__organization").order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    counts = {
        r["status"]: r["n"]
        for r in AgentTask.objects.values("status").annotate(n=Count("id"))
    }
    statuses = [
        {"value": v, "label": label, "count": counts.get(v, 0)}
        for v, label in TaskStatus.choices
    ]
    return render(request, "console/tasks.html", {
        "active": "tasks", "rows": qs[:200], "statuses": statuses, "current": status,
    })


@staff_required
def economics(request):
    totals = _usage_totals()
    margin = totals["credits"] - totals["cost"]
    by_model = (
        UsageRecord.objects.values("provider", "model")
        .annotate(cost=_zero(), credits=Coalesce(Sum("credits_charged"), Decimal("0"), output_field=_MONEY),
                  tokens=Coalesce(Sum("total_tokens"), 0), n=Count("id"))
        .order_by("-cost")
    )
    by_agent = (
        UsageRecord.objects.values("agent_key")
        .annotate(cost=_zero(), n=Count("id"))
        .order_by("-cost")[:12]
    )
    return render(request, "console/economics.html", {
        "active": "economics", "totals": totals, "margin": margin,
        "by_model": by_model, "by_agent": by_agent,
    })


@staff_required
def deployments(request):
    rows = (
        Deployment.objects.select_related("project", "project__organization")
        .order_by("-created_at")[:200]
    )
    return render(request, "console/deployments.html", {"active": "deployments", "rows": rows})


@staff_required
def leads(request):
    rows = ContactMessage.objects.order_by("-created_at")[:200]
    return render(request, "console/leads.html", {"active": "leads", "rows": rows})


@staff_required
def mobile_releases(request):
    """Admin view of the Mobile Release & App Store Platform (spec §30). Read-only,
    honest: shows store-provider availability, connections, and every release across
    tenants so staff can diagnose failures without exposing internals to customers."""
    from apps.release.models import MobileApplication, Release, ReleaseRejection, StoreConnection
    from apps.release.providers import provider_status
    rejections = (
        ReleaseRejection.objects.select_related(
            "release", "release__mobile_application", "release__mobile_application__project__organization")
        .order_by("-created_at")[:50]
    )
    releases = (
        Release.objects.select_related("mobile_application", "mobile_application__project",
                                        "mobile_application__project__organization")
        .order_by("-created_at")[:200]
    )
    connections = (
        StoreConnection.objects.select_related("organization").order_by("-created_at")[:100]
    )
    apps = (
        MobileApplication.objects.select_related("project", "project__organization")
        .order_by("-created_at")[:100]
    )
    return render(request, "console/mobile_releases.html", {
        "active": "mobile", "providers": provider_status(),
        "releases": releases, "connections": connections, "apps": apps,
        "rejections": rejections,
    })


@staff_required
def hooks(request):
    """Generation hooks (Control Center): the guardrails + their recent runs."""
    from apps.hooks.models import Hook, HookEvent, HookRun
    if request.method == "POST":
        from django.shortcuts import redirect
        name = (request.POST.get("name") or "").strip()
        event = request.POST.get("event")
        action = request.POST.get("action")
        if name and event in HookEvent.values and action in dict(Hook.ACTIONS):
            Hook.objects.create(name=name, event=event, action=action,
                                blocking=bool(request.POST.get("blocking")), scope=Hook.SCOPE_GLOBAL)
        return redirect("console:hooks")
    return render(request, "console/hooks.html", {
        "active": "hooks",
        "hooks": Hook.objects.all(),
        "runs": HookRun.objects.select_related("hook", "project")[:40],
        "events": HookEvent.choices, "actions": Hook.ACTIONS,
    })


@staff_required
def skills(request):
    """Skills library (Control Center). Lists the built-in global playbooks and any
    DB-authored ones; staff can add a global skill."""
    from django.utils.text import slugify
    from apps.skills.builtins import BUILTIN_SKILLS
    from apps.skills.models import Skill
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        kws = [k.strip() for k in (request.POST.get("keywords") or "").split(",") if k.strip()]
        body = (request.POST.get("body") or "").strip()
        if name and body:
            Skill.objects.create(
                name=name, slug=slugify(name)[:64] or "skill", keywords=kws, body=body,
                scope=Skill.SCOPE_GLOBAL, created_by=request.user)
        from django.shortcuts import redirect
        return redirect("console:skills")
    return render(request, "console/skills.html", {
        "active": "skills",
        "builtins": BUILTIN_SKILLS,
        "authored": Skill.objects.select_related("organization", "project"),
    })


@staff_required
def connectors(request):
    """External connectors inventory (spec: MCP-style layer). Honest: shows each
    connector and whether it's configured — never the credential value."""
    from apps.tools.connectors import connector_status
    return render(request, "console/connectors.html", {
        "active": "connectors", "connectors": connector_status(),
    })


@staff_required
def websites(request):
    """Admin view of the Website Publishing platform (spec §43). Read-only, honest:
    host availability, every website, and its publish versions across tenants."""
    from apps.publishing.hosting import host_status
    from apps.publishing.models import CustomDomain, PublishVersion, Website
    sites = (
        Website.objects.select_related("project", "project__organization").order_by("-created_at")[:100]
    )
    versions = (
        PublishVersion.objects.select_related("website", "website__project__organization")
        .order_by("-created_at")[:200]
    )
    domains = (
        CustomDomain.objects.select_related("website", "website__project__organization")
        .order_by("-created_at")[:100]
    )
    return render(request, "console/websites.html", {
        "active": "websites", "hosts": host_status(), "sites": sites,
        "versions": versions, "domains": domains,
    })


@staff_required
def audit(request):
    from apps.audit.models import AuditEvent
    action = request.GET.get("action") or ""
    qs = AuditEvent.objects.select_related("actor", "organization").order_by("-created_at")
    if action:
        qs = qs.filter(action=action)
    actions = sorted(
        AuditEvent.objects.values_list("action", flat=True).distinct()
    )
    return render(request, "console/audit.html", {
        "active": "audit", "rows": qs[:300], "actions": actions, "current": action,
    })


@staff_required
def legal(request):
    """Legal & Compliance admin (spec §48-52): author, review, approve, publish and
    archive legal documents, and see acceptance coverage. Staff-only; publishing a
    version freezes it immutably."""
    from django.contrib import messages
    from django.shortcuts import redirect

    from apps.legal import service
    from apps.legal.models import DocumentStatus, LegalAcceptance, LegalDocument
    from apps.legal.registry import DOCUMENT_TYPES, JURISDICTIONS

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create":
                service.create_draft(
                    document_type=request.POST.get("document_type", ""),
                    title=request.POST.get("title", ""),
                    version=request.POST.get("version", ""),
                    content=request.POST.get("content", ""),
                    jurisdiction=request.POST.get("jurisdiction", "global"),
                    requires_acceptance=bool(request.POST.get("requires_acceptance")),
                    change_summary=request.POST.get("change_summary", ""),
                    user=request.user)
                messages.success(request, "Draft created.")
            elif action == "jurisdiction":
                service.set_jurisdiction_config(
                    request.POST.get("jurisdiction", ""), user=request.user,
                    consent_required=bool(request.POST.get("consent_required")),
                    cookie_consent_required=bool(request.POST.get("cookie_consent_required")),
                    additional_notices=request.POST.get("additional_notices", ""))
                messages.success(request, "Jurisdiction requirements saved.")
            elif action == "law_request":
                service.log_law_request(
                    authority=request.POST.get("authority", ""),
                    jurisdiction=request.POST.get("jurisdiction", ""),
                    request_type=request.POST.get("request_type", ""),
                    data_requested=request.POST.get("data_requested", ""),
                    user=request.user)
                messages.success(request, "Request logged — pending review (no data disclosed).")
            else:
                doc = get_object_or_404(LegalDocument, pk=request.POST.get("document", 0))
                fn = {"submit": service.submit_for_review, "approve": service.approve,
                      "publish": service.publish, "archive": service.archive}.get(action)
                if action == "edit":
                    service.update_draft(doc, user=request.user,
                                         content=request.POST.get("content"),
                                         change_summary=request.POST.get("change_summary"))
                    messages.success(request, "Draft updated.")
                elif fn:
                    fn(doc, user=request.user)
                    messages.success(request, f"Document {action}d.")
        except (service.LegalError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("console:legal")

    docs = list(LegalDocument.objects.all())
    by_status = {}
    for d in docs:
        by_status[d.status] = by_status.get(d.status, 0) + 1
    summary = {
        "published": by_status.get(DocumentStatus.PUBLISHED, 0),
        "draft": by_status.get(DocumentStatus.DRAFT, 0),
        "under_review": by_status.get(DocumentStatus.UNDER_REVIEW, 0),
        "acceptances": LegalAcceptance.objects.count(),
    }
    from apps.legal.models import JurisdictionConfig, LawEnforcementRequest
    return render(request, "console/legal.html", {
        "active": "legal", "documents": docs, "summary": summary,
        "document_types": [{"code": c, "label": l} for c, l in DOCUMENT_TYPES.items()],
        "jurisdictions": [{"code": c, "label": l} for c, l in JURISDICTIONS.items()],
        "jurisdiction_configs": JurisdictionConfig.objects.all(),
        "law_requests": LawEnforcementRequest.objects.all()[:50],
    })


@staff_required
def privacy(request):
    """Privacy-request queue (spec §17, §75): the staff workflow for data-subject
    requests. Staff-only — these records never appear on tenant APIs."""
    from django.contrib import messages
    from django.shortcuts import redirect

    from apps.privacy import service
    from apps.privacy.models import PrivacyRequest, RequestStatus

    if request.method == "POST":
        req = get_object_or_404(PrivacyRequest, pk=request.POST.get("request", 0))
        action = request.POST.get("action")
        try:
            if action == "transition":
                service.transition(req, request.POST.get("status", ""),
                                   note=request.POST.get("note", ""), actor=request.user)
            elif action == "resolve":
                service.resolve(req, resolution=request.POST.get("resolution", ""),
                               status=request.POST.get("status", RequestStatus.COMPLETED),
                               actor=request.user)
            messages.success(request, "Request updated.")
        except service.PrivacyError as exc:
            messages.error(request, str(exc))
        return redirect("console:privacy")

    return render(request, "console/privacy.html", {
        "active": "privacy", "summary": service.summary(),
        "requests": PrivacyRequest.objects.select_related("user", "organization")[:200],
        "statuses": RequestStatus.choices,
    })


@staff_required
def trust(request):
    """Trust & security admin (spec §26, §29): maintain the subprocessor register
    and triage private vulnerability reports. Staff-only; reports are never public."""
    from django.contrib import messages
    from django.shortcuts import redirect

    from apps.trust import service
    from apps.trust.models import Subprocessor, VulnerabilityReport

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "subprocessor":
                service.register_subprocessor(
                    name=request.POST.get("name", ""),
                    category=request.POST.get("category", "other"),
                    service=request.POST.get("service", ""),
                    purpose=request.POST.get("purpose", ""),
                    location=request.POST.get("location", ""), user=request.user)
                messages.success(request, "Subprocessor added.")
            elif action == "report":
                report = get_object_or_404(VulnerabilityReport, pk=request.POST.get("report", 0))
                service.set_report_status(report, request.POST.get("status", ""),
                                          user=request.user)
                messages.success(request, "Report updated.")
        except service.TrustError as exc:
            messages.error(request, str(exc))
        return redirect("console:trust")

    return render(request, "console/trust.html", {
        "active": "trust",
        "subprocessors": Subprocessor.objects.all(),
        "reports": VulnerabilityReport.objects.all()[:100],
        "categories": Subprocessor.Category.choices,
        "report_statuses": VulnerabilityReport.Status.choices,
    })
