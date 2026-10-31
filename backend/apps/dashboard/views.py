"""Server-rendered Django UI for the platform (the customer control plane).

Session-authenticated, tenant-scoped through org membership. Dark developer-
platform experience. This is the platform's own operator UI — distinct from the
software the platform generates for customers. UI layer only: it reads the same
models/services as the API and never bypasses tenant scoping.

Pages backed by real data are implemented; areas without a backend yet render an
honest "coming soon" shell rather than fabricated metrics.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy

from apps.agents.definitions import registry as agent_registry
from apps.changes import service as changes_service
from apps.changes.models import ChangeRequest
from apps.credits.models import CreditAccount, Invoice, UsageRecord
from apps.credits.services import plans
from apps.deployments.models import Deployment, DeploymentStatus
from apps.organizations.access import (
    manageable_organizations_for,
    organizations_for,
)
from apps.organizations import invitations as invites
from apps.organizations import members as members_svc
from apps.organizations.models import (
    Invitation,
    InvitationStatus,
    Membership,
    Organization,
    Role,
    Team,
)
from apps.orchestrator.models import TERMINAL_STATUSES, AgentTask
from apps.orchestrator.service import Orchestrator
from apps.project_context.models import ContextEntry, ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project
from apps.workspaces.models import Workspace
from apps.technology.registry import ROLES
from apps.technology.registry import registry as tech_registry

def _manageable_ids(user):
    return set(manageable_organizations_for(user).values_list("id", flat=True))


# Build orchestration lives in the shared service so web + mobile behave
# identically; these module-level aliases keep the existing view code readable.
from apps.projects.builds import PIPELINE as _PIPELINE  # noqa: E402
from apps.projects.builds import project_progress as _project_progress  # noqa: E402
from apps.projects.builds import project_state as _project_state  # noqa: E402
from apps.projects.builds import name_from_brief as _name_from_brief  # noqa: E402
from apps.projects.builds import default_stack as _default_stack  # noqa: E402
from apps.projects.builds import start_build as _start_build  # noqa: E402
from apps.projects.builds import create_and_start_build  # noqa: E402


# --- Home: the builder ("What do you want to build?") -----------------------

_STARTERS = [
    ("CRM", "Build a CRM with contacts, companies, leads, deals, activities and a sales dashboard."),
    ("Website", "Build a professional website for my business with home, services, about and contact pages."),
    ("SaaS", "Build a SaaS platform where teams sign up, manage members and pay a monthly subscription."),
    ("E-commerce", "Build an online store with a product catalog, cart, checkout and orders."),
    ("Customer Portal", "Build a customer portal where clients log in, submit requests and track their status."),
    ("Internal Tool", "Build an internal tool for my team to manage tasks, approvals and reports."),
    ("Mobile App", "Build a mobile-friendly app for booking appointments with reminders."),
    ("API", "Build a REST API for managing customers, orders and invoices."),
]
_PLACEHOLDERS = [
    "Build a CRM for my sales team with customers, leads, deals, tasks and a dashboard…",
    "Build an e-commerce website for my clothing business…",
    "Create a booking system for my salon…",
    "Build a construction project management app…",
    "Create a website for my engineering company…",
    "Build a mobile-friendly invoicing system…",
    "Create a SaaS platform for managing employees and leave…",
]
class BoldronLoginView(auth_views.LoginView):
    """After login, platform staff land on the Control Center; customers land on the
    builder. An explicit ?next= is always honored (so deep links still work)."""
    template_name = "dashboard/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        explicit = self.get_redirect_url()   # a validated ?next=, or ""
        if explicit:
            return explicit
        if self.request.user.is_staff:
            return reverse("console:overview")
        return reverse("dashboard:home")

    def post(self, request, *args, **kwargs):
        from apps.core import throttle
        self._email = (request.POST.get("username") or "").strip().lower()
        self._ip = throttle.client_ip(request)
        retry = throttle.login_retry_after(self._email, self._ip)
        if retry:
            # Locked out — don't even attempt authentication.
            return self.render_to_response(self.get_context_data(
                form=self.get_form(), lockout=throttle.too_many_message(retry)))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        from apps.core import throttle
        throttle.login_reset(getattr(self, "_email", ""), getattr(self, "_ip", ""))
        user = form.get_user()
        from apps.accounts import mfa
        if mfa.is_enabled(user):
            # Password checks out, but a second factor is still required. Hold the
            # login: stash the pending user + intent in the (still anonymous)
            # session and divert to the code challenge. No session login happens
            # until the code is verified.
            self.request.session["mfa_pending_uid"] = user.pk
            self.request.session["mfa_remember"] = bool(self.request.POST.get("remember"))
            self.request.session["mfa_next"] = self.get_success_url()
            return redirect("dashboard:mfa_challenge")
        # "Keep me signed in": otherwise the session ends when the browser closes.
        if not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)
        response = super().form_valid(form)  # logs in + establishes the session
        from apps.accounts import security
        security.record_login(self.request.user, self.request)
        return response

    def form_invalid(self, form):
        from apps.core import throttle
        from apps.accounts import security
        throttle.login_record_failure(getattr(self, "_email", ""), getattr(self, "_ip", ""))
        security.record_failed(getattr(self, "_email", ""), self.request)
        return super().form_invalid(form)


class BoldronLogoutView(auth_views.LogoutView):
    """Record the logout and drop this session's UserSession before signing out."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            from apps.accounts import security
            from apps.accounts.models import LoginEvent, UserSession
            security.record_event(request.user, request, LoginEvent.LOGOUT)
            key = request.session.session_key
            if key:
                UserSession.objects.filter(session_key=key).delete()
        return super().dispatch(request, *args, **kwargs)


def mfa_challenge(request):
    """Second step of web login: verify a TOTP or recovery code for the user whose
    password already checked out, then complete the session login. Guarded by a
    pending-uid stashed in the (still anonymous) session; brute-force throttled."""
    from django.contrib.auth import login as auth_login
    from apps.accounts import mfa, security
    from apps.accounts.models import User
    from apps.core import throttle

    uid = request.session.get("mfa_pending_uid")
    user = User.objects.filter(pk=uid).first() if uid else None
    if user is None:
        return redirect("dashboard:login")

    if request.method == "POST":
        ip = throttle.client_ip(request)
        retry = throttle.login_retry_after(user.email, ip)
        if retry:
            return render(request, "dashboard/mfa_challenge.html",
                          {"lockout": throttle.too_many_message(retry)})
        if mfa.verify_any(user, request.POST.get("code") or ""):
            throttle.login_reset(user.email, ip)
            remember = request.session.get("mfa_remember", False)
            next_url = request.session.get("mfa_next") or reverse("dashboard:home")
            for key in ("mfa_pending_uid", "mfa_remember", "mfa_next"):
                request.session.pop(key, None)
            auth_login(request, user)
            if not remember:
                request.session.set_expiry(0)
            security.record_login(user, request)
            return redirect(next_url)
        throttle.login_record_failure(user.email, ip)
        security.record_failed(user.email, request)
        messages.error(request, "That code isn't valid.")

    return render(request, "dashboard/mfa_challenge.html", {})


class BoldronPasswordResetView(auth_views.PasswordResetView):
    """Forgot-password: emails a signed, single-use reset link (branded, via the
    configured EMAIL_BACKEND). Always redirects to the same 'done' page whether or
    not the address has an account, so it never reveals which emails are registered."""
    template_name = "dashboard/password_reset_form.html"
    email_template_name = "dashboard/password_reset_email.txt"
    html_email_template_name = "dashboard/password_reset_email.html"
    subject_template_name = "dashboard/password_reset_subject.txt"
    success_url = reverse_lazy("dashboard:password_reset_done")

    @property
    def extra_email_context(self):
        # The email templates render outside a request context, so pass the brand.
        return {"app_name": settings.APP_NAME}

    def post(self, request, *args, **kwargs):
        from apps.core import throttle
        ip = throttle.client_ip(request)
        email = (request.POST.get("email") or "").strip().lower()
        retry = throttle.reset_retry_after(email, ip)
        if retry:
            return self.render_to_response(self.get_context_data(
                form=self.get_form(), lockout=throttle.too_many_message(retry)))
        throttle.reset_record(email, ip)
        return super().post(request, *args, **kwargs)


class BoldronPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """Validates the link token and lets the user set a new password."""
    template_name = "dashboard/password_reset_confirm.html"
    success_url = reverse_lazy("dashboard:password_reset_complete")


@login_required
def overview(request):
    user = request.user
    orgs = list(organizations_for(user))
    manageable = _manageable_ids(user)

    if request.method == "POST" and request.POST.get("action") == "check_models":
        from apps.ai_providers.registry import build_readiness
        r = build_readiness(force=True)
        if r["state"] == "ready":
            messages.success(request, r["message"])
        elif r["state"] == "none":
            messages.info(request, r["message"])
        else:
            messages.warning(request, r["message"])
        return redirect("dashboard:home")

    if request.method == "POST" and request.POST.get("action") == "build":
        if not request.user.email_verified:
            messages.warning(request, "Please verify your email to start building — "
                                      "check your inbox, or use Resend in the banner above.")
            return redirect("dashboard:home")
        brief = (request.POST.get("brief") or "").strip()
        if not brief:
            messages.error(request, f"Tell {settings.APP_NAME} what you want to build.")
            return redirect("dashboard:home")
        org = next((o for o in orgs if o.id in manageable), None)
        if org is None:
            org = Organization.objects.create(
                name=f"{user.short_name}'s workspace", created_by=user)
            org.add_member(user, role=Role.OWNER)
        project = create_and_start_build(org, brief, user)
        messages.success(request, f"{settings.APP_NAME} is building your app — follow the progress below.")
        # Real balance check: probe a connected model (cached) rather than just
        # checking that a key is set, so the demo-mode warning is accurate.
        from apps.ai_providers.registry import build_readiness
        r = build_readiness()
        if not r["ready"]:
            messages.warning(request, f"Heads up: {r['message']} Generated output will be a "
                                      "placeholder until a model can serve the build.")
        return redirect("dashboard:project", pk=project.id)

    projects = Project.objects.filter(
        organization__in=orgs).select_related("organization").order_by("-updated_at")
    cards = [
        {"project": p, "state": _project_state(p), "progress": _project_progress(p)}
        for p in projects[:12]
    ]

    # Active builds — projects still in progress (reuses the real build state).
    _ACTIVE = {"planning", "building", "running", "analyzing", "deploying", "implementing"}
    active_builds = [c for c in cards if (c["state"] or "").lower() in _ACTIVE][:4]

    # Usage overview + actionable alerts (reuse the settings service — one source).
    from apps.settings import service as _settings
    usage = _settings.organization_status(user)
    alerts = _settings.alerts_for(user)
    # Enrich each org row with storage + project meters (spec §17) for a prominent
    # usage panel. Real figures only — no fabricated limits.
    from apps.credits.usage import usage_overview
    _orgs_by_id = {o.id: o for o in orgs}
    for row in usage:
        org = _orgs_by_id.get(row["id"])
        if org is not None:
            ov = usage_overview(org)
            row["storage"] = ov["storage"]["display"]
            row["projects"] = ov["projects"]

    # Recent activity across the user's organizations (real audit events).
    from apps.audit.models import AuditEvent
    from apps.audit.service import event_dict
    activity = [event_dict(e) for e in (
        AuditEvent.objects.filter(organization__in=orgs)
        .select_related("actor")[:8]
    )]

    # Time-of-day greeting in the user's timezone.
    from django.utils import timezone as _tz
    hour = _tz.localtime().hour
    greeting = ("Good morning" if hour < 12 else
                "Good afternoon" if hour < 18 else "Good evening")

    from apps.ai_providers.registry import build_readiness
    return render(request, "dashboard/home.html", {
        "active": "overview", "cards": cards,
        "greeting": greeting,
        "active_builds": active_builds,
        "usage": usage,
        "home_alerts": alerts,
        "activity": activity,
        "starters": _STARTERS, "placeholders": _PLACEHOLDERS,
        "prefill": request.session.pop("build_idea", ""),  # carried from marketing signup
        "readiness": build_readiness(probe=False),  # cached-only: keeps the page instant
    })


# --- projects ---------------------------------------------------------------

@login_required
def projects(request):
    orgs = list(organizations_for(request.user))
    manageable = _manageable_ids(request.user)
    if request.method == "POST" and request.POST.get("action") == "create_project":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0))
        name = (request.POST.get("name") or "").strip()
        if org.id in manageable and name:
            p = Project.objects.create(organization=org, name=name, created_by=request.user)
            p.ensure_default_workspace()
            messages.success(request, f"Created project “{p.name}”.")
            return redirect("dashboard:project", pk=p.id)
        messages.error(request, "Need a name and owner/admin rights in that org.")
        return redirect("dashboard:projects")

    rows = [
        {"project": p, "state": _project_state(p), "progress": _project_progress(p)}
        for p in Project.objects.filter(organization__in=orgs).select_related("organization")
    ]
    return render(request, "dashboard/projects.html", {
        "active": "projects", "rows": rows,
        "manageable_orgs": [o for o in orgs if o.id in manageable],
    })


@login_required
def project(request, pk):
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin required for this action.")
            return redirect("dashboard:project", pk=pk)
        if request.POST.get("action") == "create_change":
            desc = (request.POST.get("description") or "").strip()
            if desc:
                change = changes_service.create_change(proj, desc, request.user)
                changes_service.build_plan(change)
                return redirect("dashboard:change", pk=change.id)
            messages.error(request, "Describe the change you want.")
            return redirect("dashboard:project", pk=pk)
        _handle_project_action(request, proj)
        return redirect("dashboard:project", pk=pk)

    entries = ContextEntry.objects.filter(project=proj)
    pipeline = [
        {"kind": k, "label": ContextKind(k).label, "entries": [e for e in entries if e.kind == k]}
        for k in _PIPELINE
    ]
    stack_roles = [
        {"role": r, "chosen": (proj.technology or {}).get(r), "options": tech_registry.options_for_role(r)}
        for r in ROLES
    ]
    twin = {
        "components": sum(1 for e in entries if e.kind == ContextKind.ARCHITECTURE),
        "apis": sum(1 for e in entries if e.kind == ContextKind.API),
        "models": sum(1 for e in entries if e.kind == ContextKind.SCHEMA),
        "screens": sum(1 for e in entries if e.kind == ContextKind.SCREEN),
    }
    from apps.capabilities.analysis import capability_ids, summary
    # Use the project's persisted capability map; fall back to inferring from the
    # brief for projects built before the map existed.
    cap_ids = proj.capabilities or capability_ids(proj.description or proj.name)
    return render(request, "dashboard/project.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "state": _project_state(proj), "progress": _project_progress(proj),
        "pipeline": pipeline, "tasks": proj.agent_tasks.all(),
        "stack_roles": stack_roles,
        "capability_map": summary(cap_ids),
        "twin": twin, "changes": proj.changes.all()[:8],
        "backups": proj.backups.all()[:10],
        "credits": _project_credit_summary(proj),
        # True when any build step ran on the offline fallback — i.e. no live AI
        # model was reachable, so the output is a placeholder, not real code.
        "ran_on_stub": proj.agent_tasks.filter(model__istartswith="stub").exists(),
    })


# Credit snapshot for the build screen lives in the shared build service.
from apps.projects.builds import credit_summary as _project_credit_summary  # noqa: E402


@login_required
def release_center(request, pk):
    """Mobile Release Center (spec §19): one page to prepare and release a mobile
    app to Google Play, App Store and AppGallery. Every store shows its REAL state
    — not connected here, because live publishing needs the customer's own store
    credentials — and readiness is computed from actual records. Nothing is faked.
    """
    from apps.release import service as rel
    from apps.release.models import MobileApplication
    from apps.release.providers import all_providers, get_provider

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    app = MobileApplication.objects.filter(project=proj).order_by("created_at").first()

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin required for this action.")
            return redirect("dashboard:release_center", pk=pk)
        action = request.POST.get("action")
        if action == "create_app":
            # Idempotent: reuse an existing app rather than creating a duplicate.
            if app is None:
                slug = (proj.slug or proj.name).lower().replace("-", "").replace(" ", "")
                prefix = settings.APP_BUNDLE_ID_PREFIX
                pkg = (f"{prefix}.{slug}"[:250] if slug else f"{prefix}.app")
                app = rel.create_mobile_application(
                    project=proj, name=proj.name, package_identifier=pkg, bundle_identifier=pkg,
                )
            from apps.release.models import StoreMetadata
            for prov in all_providers():
                store_app = rel.ensure_store_application(app, prov.key)
                if not StoreMetadata.objects.filter(store_application=store_app).exists():
                    rel.set_metadata(store_app, app_name=app.name)
            messages.success(request, "Mobile application ready. Connect your store accounts to publish.")
        elif action == "generate_listing" and app:
            store_app = app.store_apps.filter(provider=request.POST.get("provider")).first()
            if store_app:
                rel.generate_store_listing(store_app, user=request.user)
                messages.success(request, "Drafted an AI store listing from your app's "
                                          "features — review and approve it below.")
        elif action == "save_listing" and app:
            store_app = app.store_apps.filter(provider=request.POST.get("provider")).first()
            if store_app:
                rel.set_metadata(
                    store_app, ai_generated=False, approved=False,
                    app_name=(request.POST.get("app_name") or "")[:255],
                    short_description=(request.POST.get("short_description") or "")[:255],
                    full_description=request.POST.get("full_description") or "",
                    privacy_url=request.POST.get("privacy_url") or "",
                )
                messages.success(request, "Listing saved.")
        elif action == "approve_listing" and app:
            store_app = app.store_apps.filter(provider=request.POST.get("provider")).first()
            if store_app:
                rel.approve_metadata(store_app, user=request.user)
                messages.success(request, "Listing approved.")
        elif action == "generate_screenshots" and app:
            store_app = app.store_apps.filter(provider=request.POST.get("provider")).first()
            if store_app:
                shots = rel.generate_store_screenshots(store_app, user=request.user)
                if shots:
                    messages.success(request, f"Generated {len(shots)} layout preview(s) from "
                                              "your app's screens — review and approve them.")
                else:
                    messages.warning(request, "No screens detected yet to generate previews from.")
        elif action == "approve_screenshots" and app:
            store_app = app.store_apps.filter(provider=request.POST.get("provider")).first()
            if store_app:
                n = rel.approve_screenshots(store_app, user=request.user)
                messages.success(request, f"Approved {n} screenshot(s).")
        elif action == "report_rejection" and app:
            release = app.releases.filter(provider=request.POST.get("provider")).first()
            text = (request.POST.get("rejection_text") or "").strip()
            if release and text:
                record = rel.record_rejection(release, text=text, source="manual", user=request.user)
                messages.success(request, f"Analysed the rejection — “{record.label}”. "
                                          "Review the suggested fix below.")
            else:
                messages.error(request, "Prepare a release first, then paste the store's message.")
        elif action == "plan_fix" and app:
            from apps.release.models import ReleaseRejection
            rejection = ReleaseRejection.objects.filter(
                pk=request.POST.get("rejection", 0),
                release__mobile_application__project=proj).first()
            if rejection and not rejection.change:
                change = rel.plan_fix(rejection, user=request.user)
                return redirect("dashboard:change", pk=change.id)
        elif action == "resubmit" and app:
            release = app.releases.filter(pk=request.POST.get("release", 0)).first()
            if release:
                new_release = rel.prepare_resubmission(release, user=request.user)
                messages.success(request, f"Prepared v{new_release.version}+{new_release.build_number} "
                                          "for resubmission.")
        elif action == "prepare_release" and app:
            provider_key = request.POST.get("provider")
            if get_provider(provider_key):
                release = rel.request_release(app=app, provider_key=provider_key, user=request.user)
                messages.success(
                    request, f"Prepared a release for {get_provider(provider_key).name} "
                             f"({release.readiness}% ready)."
                )
            else:
                messages.error(request, "Unknown store.")
        elif action == "approve_release" and app:
            release = app.releases.filter(pk=request.POST.get("release", 0)).first()
            if release:
                rel.approve_release(release, user=request.user)
                messages.success(request, "Release approved for submission.")
        elif action == "submit_release" and app:
            release = app.releases.filter(pk=request.POST.get("release", 0)).first()
            if release:
                release = rel.submit_release(release, user=request.user)
                if release.state == "submitted":
                    messages.success(request, "Submitted to the store.")
                else:
                    last = release.events.first()
                    messages.warning(request, last.message if last else "Store not connected.")
        return redirect("dashboard:release_center", pk=pk)

    stores = []
    for prov in all_providers():
        conn = proj.organization.store_connections.filter(provider=prov.key).first()
        store_app = app.store_apps.filter(provider=prov.key).first() if app else None
        release = (app.releases.filter(provider=prov.key).first() if app else None)
        shots = list(store_app.assets.filter(kind="screenshot")) if store_app else []
        rejections = list(release.rejections.filter(resolved=False)) if release else []
        stores.append({
            "provider": prov, "connection": conn, "store_app": store_app, "release": release,
            "connected": bool(conn and conn.status == "connected"),
            "screenshots": shots,
            "screenshots_approved": bool(shots) and all(s.approved for s in shots),
            "rejections": rejections,
        })
    return render(request, "dashboard/release_center.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "app": app, "stores": stores,
    })


@login_required
def publish_center(request, pk):
    """Website Release Center (spec §41): Publish → Live URL, with an honest publish
    checklist, versioned publishes served by the platform, health, and rollback. Public
    custom domains + SSL are a Phase-2 gated path, shown as not-yet-available."""
    from apps.publishing import readiness as pub_readiness
    from apps.publishing import service as pub
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    website = getattr(proj, "website", None)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin required for this action.")
            return redirect("dashboard:publish_center", pk=pk)
        action = request.POST.get("action")
        if action == "enable_website":
            website = pub.get_or_create_website(proj)
            messages.success(request, "Website publishing enabled.")
        elif action == "publish" and website:
            version = pub.publish(website, user=request.user)
            if version.state == "live":
                messages.success(request, f"Published {version.version} — your site is live.")
            elif version.state == "needs_attention":
                messages.warning(request, f"Published {version.version}, but the health check "
                                          f"flagged an issue: {version.health_detail}")
            else:
                messages.error(request, version.log or "Publish failed.")
        elif action == "rollback" and website:
            try:
                target = pub.rollback(website, user=request.user)
                messages.success(request, f"Rolled back to {target.version}.")
            except pub.PublishError as exc:
                messages.error(request, str(exc))
        elif action == "health_check" and website and website.current:
            pub.health_check(website.current)
        elif action == "connect_domain" and website:
            from apps.publishing import domain_service as dom
            try:
                dom.connect_domain(website, hostname=request.POST.get("hostname", ""),
                                   user=request.user)
                messages.success(request, "Domain added — set the DNS records shown, then verify.")
            except dom.DomainServiceError as exc:
                messages.error(request, str(exc))
        elif action == "verify_domain" and website:
            from apps.publishing import domain_service as dom
            domain = website.domains.filter(pk=request.POST.get("domain", 0)).first()
            if domain:
                dom.verify_domain(domain, user=request.user)
                if domain.is_verified:
                    messages.success(request, f"{domain.hostname} ownership verified.")
                else:
                    messages.warning(request, domain.detail)
        elif action == "request_ssl" and website:
            from apps.publishing import domain_service as dom
            domain = website.domains.filter(pk=request.POST.get("domain", 0)).first()
            if domain:
                try:
                    dom.request_ssl(domain, user=request.user)
                    messages.info(request, domain.detail)
                except dom.DomainServiceError as exc:
                    messages.error(request, str(exc))
        elif action == "remove_domain" and website:
            from apps.publishing import domain_service as dom
            domain = website.domains.filter(pk=request.POST.get("domain", 0)).first()
            if domain:
                dom.remove_domain(domain, user=request.user)
                messages.success(request, "Domain removed.")
        elif action == "seo_generate" and website:
            from apps.publishing import seo_service as seo
            drafts = seo.generate_drafts(website, user=request.user)
            messages.success(request, f"Drafted SEO for {len(drafts)} page(s) — review and apply.")
        elif action == "seo_approve_all" and website:
            from apps.publishing import seo_service as seo
            config = seo.ensure_config(website)
            n = config.pages.update(approved=True)
            messages.success(request, f"Approved SEO for {n} page(s).")
        elif action == "add_form" and website:
            from apps.publishing import forms_service as forms
            forms.create_form(website, kind=request.POST.get("kind", "contact"), user=request.user)
            messages.success(request, "Form added — copy its embed snippet into your site.")
        elif action == "remove_form" and website:
            form = website.forms.filter(pk=request.POST.get("form", 0)).first()
            if form:
                form.delete()
                messages.success(request, "Form removed.")
        elif action == "seo_apply" and website:
            from apps.publishing import seo_service as seo
            try:
                result = seo.apply_seo(website, user=request.user)
                messages.success(request, f"Applied SEO to {result['pages']} page(s) "
                                          "plus sitemap.xml and robots.txt.")
            except seo.SeoServiceError as exc:
                messages.error(request, str(exc))
        return redirect("dashboard:publish_center", pk=pk)

    checks = pub.evaluate(website) if website else []
    current = website.current if website else None
    return render(request, "dashboard/publish_center.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "website": website, "current": current, "checks": checks,
        "score": pub_readiness.score(checks) if checks else 0,
        "versions": website.versions.all()[:10] if website else [],
        "can_publish": pub_readiness.can_publish(checks) if checks else False,
        "domains": website.domains.all() if website else [],
        "seo": _seo_context(website) if website else None,
        "forms": _forms_context(website, request) if website else None,
        "lead_count": website.leads.count() if website else 0,
    })


def _forms_context(website, request):
    from apps.publishing.forms_service import embed_html
    base = f"{request.scheme}://{request.get_host()}"
    return [{"form": f, "embed": embed_html(f, action_base=base),
             "submissions": f.submissions.filter(is_spam=False).count()}
            for f in website.forms.all()]


def _seo_context(website):
    from apps.publishing import seo
    audits = seo.audit_pages(website)
    config = getattr(website, "seo", None)
    return {
        "audits": audits,
        "score": seo.audit_score(audits),
        "pages": list(config.pages.all()) if config else [],
        "applied_at": config.applied_at if config else None,
    }


@login_required
def site_operations(request, pk):
    """AI operations advisor (spec §37): inspect real signals → explain → recommend →
    fix (via the approval-gated change loop). BUILD → OPERATE → IMPROVE."""
    from apps.publishing import operations as ops
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    website = getattr(proj, "website", None)

    if request.method == "POST" and website and can_manage:
        if request.POST.get("action") == "create_fix":
            key = request.POST.get("finding")
            finding = next((f for f in ops.analyze(website) if f.key == key
                            and f.action.get("type") == "change"), None)
            if finding:
                change = changes_service.create_change(
                    proj, f"Operations fix — {finding.title}.\n\n{finding.recommendation}",
                    request.user)
                changes_service.build_plan(change)
                return redirect("dashboard:change", pk=change.id)
        return redirect("dashboard:operations", pk=pk)

    findings = ops.analyze(website) if website else []
    from apps.deployments.operations import operations_overview
    from apps.notifications.alerts import recent as recent_alerts
    return render(request, "dashboard/site_operations.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "website": website, "findings": findings,
        "summary": ops.summary_line(findings) if website else "",
        # The composed Operations Center (spec §10): runtime health across the app.
        "opsview": operations_overview(proj),
        "alerts": recent_alerts(proj, limit=8),
    })


@login_required
def monitoring(request, pk):
    """Health monitoring for the published site (spec §36). Real serve-health probes;
    remote-server resource metrics are honestly marked not-monitored."""
    from apps.publishing import monitor
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    website = getattr(proj, "website", None)

    if request.method == "POST" and website and can_manage:
        if request.POST.get("action") == "run_check":
            if monitor.run_check(website) is None:
                messages.error(request, "Publish the site before running a health check.")
            else:
                messages.success(request, "Health check recorded.")
        return redirect("dashboard:monitoring", pk=pk)

    summary = monitor.uptime_summary(website, days=7) if website else None
    domains = list(website.domains.all()) if website else []
    return render(request, "dashboard/monitoring.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "website": website, "summary": summary, "domains": domains,
    })


@login_required
def accessibility(request, pk):
    """Automated accessibility checks on the built site (spec §30). Reports actual
    findings — never claims guaranteed compliance."""
    from apps.publishing import accessibility as a11y
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    website = getattr(proj, "website", None)
    audits = a11y.audit_pages(website) if website else []
    return render(request, "dashboard/accessibility.html", {
        "active": "projects", "project": proj, "website": website,
        "audits": audits, "score": a11y.score(audits) if audits else 0,
    })


@login_required
def analytics(request, pk):
    """Website analytics (spec §28) — real page views of the published site."""
    from apps.publishing import analytics as an
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    website = getattr(proj, "website", None)
    try:
        days = max(7, min(90, int(request.GET.get("days", 30))))
    except (TypeError, ValueError):
        days = 30
    data = an.summary(website, days=days) if website else None
    peak = max((p["views"] for p in data["series"]), default=0) if data else 0
    commerce = an.commerce_summary(website, days=days) if website else None
    rev_peak = max((p["revenue_cents"] for p in commerce["series"]), default=0) if commerce else 0
    return render(request, "dashboard/analytics.html", {
        "active": "projects", "project": proj, "website": website,
        "data": data, "days": days, "peak": peak or 1,
        "commerce": commerce, "rev_peak": rev_peak or 1,
    })


@login_required
def store(request, pk):
    """Merchant e-commerce console (spec §32): products, orders, manual-payment
    confirmation. Card gateways are shown with their real availability."""
    from apps.publishing import ecommerce_service as shop
    from apps.publishing import payments
    from apps.publishing import service as pub
    from apps.publishing.models import Order
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    website = getattr(proj, "website", None)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin required.")
            return redirect("dashboard:store", pk=pk)
        if website is None:
            website = pub.get_or_create_website(proj)
        action = request.POST.get("action")
        try:
            if action == "add_product":
                price = request.POST.get("price", "0").strip()
                cents = int(round(float(price) * 100))
                track = bool(request.POST.get("track_inventory"))
                stock = int(request.POST.get("stock") or 0)
                shop.create_product(website, name=(request.POST.get("name") or "").strip(),
                                    price_cents=cents,
                                    currency=(request.POST.get("currency") or "USD").strip().upper()[:3],
                                    description=(request.POST.get("description") or "").strip(),
                                    track_inventory=track, stock=stock,
                                    image_asset_id=request.POST.get("image_asset") or None,
                                    user=request.user)
                messages.success(request, "Product added.")
            elif action == "confirm_payment":
                order = Order.objects.filter(pk=request.POST.get("order", 0), website=website).first()
                if order:
                    shop.confirm_manual_payment(order, user=request.user)
                    messages.success(request, f"Order {order.reference} marked paid.")
            elif action == "cancel_order":
                order = Order.objects.filter(pk=request.POST.get("order", 0), website=website).first()
                if order:
                    shop.cancel_order(order, user=request.user)
                    messages.success(request, "Order cancelled.")
            elif action == "refund_order":
                order = Order.objects.filter(pk=request.POST.get("order", 0), website=website).first()
                if order:
                    shop.refund_order(order, user=request.user,
                                      reason=(request.POST.get("reason") or "").strip())
                    messages.success(request, f"Order {order.reference} refunded.")
            elif action == "edit_product":
                product = website.products.filter(pk=request.POST.get("product", 0)).first()
                if product:
                    product.name = (request.POST.get("name") or product.name).strip()
                    product.price_cents = int(round(float(request.POST.get("price") or 0) * 100))
                    product.description = (request.POST.get("description") or "").strip()
                    product.track_inventory = bool(request.POST.get("track_inventory"))
                    product.stock = max(0, int(request.POST.get("stock") or 0))
                    if "image_asset" in request.POST:
                        product.image = shop.resolve_image(website, request.POST.get("image_asset") or None)
                    product.save()
                    messages.success(request, "Product updated.")
            elif action == "toggle_product":
                product = website.products.filter(pk=request.POST.get("product", 0)).first()
                if product:
                    product.active = not product.active
                    product.save(update_fields=["active"])
                    messages.success(request, f"Product {'activated' if product.active else 'deactivated'}.")
            elif action == "add_discount":
                shop.create_discount(
                    website, code=request.POST.get("code", ""),
                    kind=request.POST.get("kind", "percent"),
                    percent_off=int(request.POST.get("percent_off") or 0),
                    amount_off_cents=int(round(float(request.POST.get("amount_off") or 0) * 100)),
                    currency=(request.POST.get("currency") or "USD").strip().upper()[:3],
                    min_subtotal_cents=int(round(float(request.POST.get("min_subtotal") or 0) * 100)),
                    max_uses=int(request.POST.get("max_uses") or 0), user=request.user)
                messages.success(request, "Discount code created.")
            elif action == "toggle_discount":
                from apps.publishing.models import DiscountCode
                dc = DiscountCode.objects.filter(pk=request.POST.get("discount", 0), website=website).first()
                if dc:
                    dc.active = not dc.active
                    dc.save(update_fields=["active"])
                    messages.success(request, f"Code {'activated' if dc.active else 'deactivated'}.")
            elif action == "add_variant":
                product = website.products.filter(pk=request.POST.get("product", 0)).first()
                if product:
                    shop.create_variant(
                        product, label=(request.POST.get("label") or "").strip(),
                        price_cents=int(round(float(request.POST.get("price") or 0) * 100)),
                        track_inventory=bool(request.POST.get("track_inventory")),
                        stock=int(request.POST.get("stock") or 0), user=request.user)
                    messages.success(request, "Variant added.")
            elif action == "delete_variant":
                from apps.publishing.models import ProductVariant
                v = ProductVariant.objects.filter(pk=request.POST.get("variant", 0),
                                                  product__website=website).first()
                if v:
                    v.delete()
                    messages.success(request, "Variant removed.")
            elif action == "set_tax":
                shop.set_tax_rate(website, name=request.POST.get("name", "Tax"),
                                  percent=request.POST.get("percent", "0"), user=request.user)
                messages.success(request, "Tax rate set.")
            elif action == "clear_tax":
                website.tax_rates.filter(active=True).update(active=False)
                messages.success(request, "Tax removed.")
            elif action == "add_shipping":
                shop.create_shipping_rate(
                    website, name=request.POST.get("name", ""),
                    price_cents=int(round(float(request.POST.get("price") or 0) * 100)),
                    currency=(request.POST.get("currency") or "USD").strip().upper()[:3],
                    free_over_cents=int(round(float(request.POST.get("free_over") or 0) * 100)),
                    user=request.user)
                messages.success(request, "Shipping option added.")
            elif action == "toggle_shipping":
                from apps.publishing.models import ShippingRate
                rate = ShippingRate.objects.filter(pk=request.POST.get("rate", 0), website=website).first()
                if rate:
                    rate.active = not rate.active
                    rate.save(update_fields=["active"])
                    messages.success(request, f"Shipping option {'enabled' if rate.active else 'disabled'}.")
            elif action == "generate_storefront":
                from apps.publishing import storefront
                try:
                    result = storefront.generate_storefront(website, user=request.user)
                    messages.success(request, f"Generated {result['pages']} storefront page(s). "
                                              "Publish to make the shop live.")
                except storefront.StorefrontError as exc:
                    messages.error(request, str(exc))
        except (shop.EcommerceError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:store", pk=pk)

    return render(request, "dashboard/store.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "website": website,
        "products": list(website.products.all()) if website else [],
        "orders": list(website.orders.prefetch_related("items")[:50]) if website else [],
        "providers": payments.provider_status(),
        "summary": shop.sales_summary(website) if website else None,
        "discounts": list(website.discount_codes.all()) if website else [],
        "shipping_rates": list(website.shipping_rates.all()) if website else [],
        "tax": website.tax_rates.filter(active=True).first() if website else None,
        "image_assets": list(website.assets.filter(kind__in=["image", "icon"])) if website else [],
    })


@login_required
def order_detail(request, pk, order_id):
    """Full order view for the merchant (spec §32): items, totals, payments, and the
    lifecycle actions (confirm / refund / cancel)."""
    from apps.publishing import ecommerce_service as shop
    from apps.publishing.models import Order
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    order = get_object_or_404(Order, pk=order_id, website__project=proj)

    if request.method == "POST" and can_manage:
        action = request.POST.get("action")
        try:
            if action == "confirm_payment":
                shop.confirm_manual_payment(order, user=request.user)
                messages.success(request, "Marked paid.")
            elif action == "refund_order":
                shop.refund_order(order, user=request.user, reason=(request.POST.get("reason") or "").strip())
                messages.success(request, "Order refunded.")
            elif action == "cancel_order":
                shop.cancel_order(order, user=request.user)
                messages.success(request, "Order cancelled.")
        except shop.EcommerceError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:order_detail", pk=pk, order_id=order_id)

    return render(request, "dashboard/order_detail.html", {
        "active": "projects", "project": proj, "can_manage": can_manage, "order": order,
    })


@login_required
def order_invoice(request, pk, order_id):
    """A real invoice/receipt for an order (spec §24/§32). HTML by default; add
    ?format=pdf for a genuine PDF. Built from the order's recorded figures and
    payments — nothing is fabricated."""
    from django.http import HttpResponse
    from apps.publishing import invoicing
    from apps.publishing.models import Order
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "payments"),
        pk=order_id, website__project=proj,
    )
    number = invoicing.invoice_number(order)
    if request.GET.get("format") == "pdf":
        pdf = invoicing.render_invoice_pdf(order)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{number}.pdf"'
        return resp
    return HttpResponse(invoicing.render_invoice_html(order), content_type="text/html")


@login_required
def content(request, pk):
    """Content management (spec §25): opt-in collections that generate real pages."""
    from apps.publishing import cms_service as cms
    from apps.publishing import service as pub
    from apps.publishing.models import ContentCollection
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    website = getattr(proj, "website", None)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin required.")
            return redirect("dashboard:content", pk=pk)
        if website is None:
            website = pub.get_or_create_website(proj)
        action = request.POST.get("action")
        try:
            if action == "add_collection":
                cms.create_collection(website, kind=request.POST.get("kind", "blog"),
                                      user=request.user)
                messages.success(request, "Collection added.")
            elif action == "add_item":
                coll = website.collections.filter(pk=request.POST.get("collection", 0)).first()
                if coll and (request.POST.get("title") or "").strip():
                    cms.add_item(coll, title=request.POST["title"].strip(),
                                 subtitle=request.POST.get("subtitle", "").strip(),
                                 body=request.POST.get("body", "").strip(), user=request.user)
                    messages.success(request, "Item added.")
                else:
                    messages.error(request, "A title is required.")
            elif action == "delete_item":
                from apps.publishing.models import ContentItem
                item = ContentItem.objects.filter(pk=request.POST.get("item", 0),
                                                  collection__website=website).first()
                if item:
                    item.delete()
                    messages.success(request, "Item deleted.")
            elif action == "generate":
                result = cms.generate(website, user=request.user)
                messages.success(request, f"Generated {result['pages']} content page(s). "
                                          "Publish to make them live.")
        except cms.CmsError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:content", pk=pk)

    collections = []
    if website:
        for c in website.collections.all():
            collections.append({"c": c, "items": list(c.items.all())})
    return render(request, "dashboard/content.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "website": website, "collections": collections, "kinds": ContentCollection.KINDS,
    })


@login_required
def assets(request, pk):
    """Asset manager for a website (spec §26): upload/resize/compress/replace/delete."""
    from apps.publishing import assets_service as assets_svc
    from apps.publishing import service as pub
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    website = getattr(proj, "website", None)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin required.")
            return redirect("dashboard:assets", pk=pk)
        if website is None:
            website = pub.get_or_create_website(proj)
        action = request.POST.get("action")
        try:
            if action == "upload":
                f = request.FILES.get("file")
                if not f:
                    messages.error(request, "Choose a file to upload.")
                else:
                    assets_svc.store_asset(website, filename=f.name, data=f.read(),
                                           content_type=f.content_type or "", user=request.user)
                    messages.success(request, "Asset uploaded.")
            else:
                asset = website.assets.filter(pk=request.POST.get("asset", 0)).first()
                if asset is None:
                    messages.error(request, "No such asset.")
                elif action == "resize":
                    assets_svc.resize_image(asset, width=int(request.POST.get("width") or 0),
                                            user=request.user)
                    messages.success(request, "Image resized.")
                elif action == "compress":
                    assets_svc.compress_image(asset, user=request.user)
                    messages.success(request, "Image compressed.")
                elif action == "replace":
                    f = request.FILES.get("file")
                    if f:
                        assets_svc.replace_asset(asset, data=f.read(), user=request.user)
                        messages.success(request, "Asset replaced.")
                elif action == "delete":
                    assets_svc.delete_asset(asset, user=request.user)
                    messages.success(request, "Asset deleted.")
        except (assets_svc.AssetError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:assets", pk=pk)

    rows = list(website.assets.all()) if website else []
    return render(request, "dashboard/assets.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "website": website, "assets": rows,
    })


@login_required
def asset_raw(request, pk, asset_id):
    """Serve an asset from the repo working tree for in-dashboard preview. Org-scoped."""
    import mimetypes
    from django.http import FileResponse, Http404
    from apps.publishing import assets_service as assets_svc
    from apps.publishing.models import Asset
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    asset = get_object_or_404(Asset, pk=asset_id, website__project=proj)
    try:
        data = assets_svc.read_bytes(asset)
    except Exception:
        raise Http404("Asset file missing.")
    ctype = asset.content_type or mimetypes.guess_type(asset.path)[0] or "application/octet-stream"
    return FileResponse(iter([data]), content_type=ctype)


@login_required
def leads(request, pk):
    """Leads inbox — the CRM surface for a website's captured leads (spec §23)."""
    from apps.publishing.models import Lead
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    website = getattr(proj, "website", None)

    if request.method == "POST" and website and can_manage:
        lead = Lead.objects.filter(pk=request.POST.get("lead", 0), website=website).first()
        status = request.POST.get("status")
        if lead and status in dict(Lead.STATUS):
            lead.status = status
            lead.save(update_fields=["status"])
        return redirect("dashboard:leads", pk=pk)

    rows = list(website.leads.select_related("source_form")[:200]) if website else []
    status_counts = []
    if website:
        status_counts = [(label, website.leads.filter(status=s).count()) for s, label in Lead.STATUS]
    return render(request, "dashboard/leads.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "website": website, "leads": rows, "status_counts": status_counts, "statuses": Lead.STATUS,
    })


@login_required
def preview(request, pk):
    """Two-pane preview: chat (change requests) + a visual view of the app.

    Honest scope: this shows the app's real design (its screens/structure from the
    twin) and a sandboxed static render when the generated output is standalone
    HTML. A preview of the *running* application requires a deployment (a preview
    runner that executes the app in isolation) — surfaced as a Deploy link, not
    faked here.
    """
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)
    if request.method == "POST" and can_manage:
        from apps.preview_runner.runner import PreviewError, runner
        action = request.POST.get("action")
        if action == "start_preview":
            try:
                runner.start(proj)  # runs the app's server if declared, else serves files
                messages.success(request, "Live preview started.")
            except PreviewError as exc:
                messages.error(request, str(exc))
            return redirect("dashboard:preview", pk=pk)
        if action == "stop_preview":
            runner.stop(proj.id)
            messages.success(request, "Live preview stopped.")
            return redirect("dashboard:preview", pk=pk)
        desc = (request.POST.get("message") or "").strip()
        if desc:
            change = changes_service.create_change(proj, desc, request.user)
            changes_service.build_plan(change)
            if change.requires_approval:
                messages.success(request, "Planned — this change needs your approval.")
            else:
                changes_service.implement(change)
                messages.success(request, f"Done — {settings.APP_NAME} applied your change.")
        return redirect("dashboard:preview", pk=pk)

    ctx = ProjectContext(proj)
    screens = [
        {"name": e.title, "route": (e.data or {}).get("route", ""),
         "components": (e.data or {}).get("components", []),
         "platform": (e.data or {}).get("platform", "web")}
        for e in ctx.by_kind(ContextKind.SCREEN)
    ]
    # A truly standalone HTML file can be shown as a static snapshot (sandboxed,
    # scripts disabled). Skipped when it references external scripts/modules.
    from apps.repositories.service import repo_for_project
    preview_html = ""
    repo = repo_for_project(proj)
    if repo.is_initialized:
        files = repo.list_files()
        for cand in ("index.html", "public/index.html", "templates/index.html"):
            if cand in files:
                content = (repo.path / cand).read_text()
                if "<script" not in content.lower():
                    preview_html = content
                break
    from apps.preview_runner.runner import runner
    return render(request, "dashboard/preview.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "screens": screens, "preview_html": preview_html,
        "changes": proj.changes.all()[:8],
        "live": runner.get(proj.id) is not None,
    })


@login_required
def preview_live(request, pk, path=""):
    """Proxy the project's running static preview into the dashboard iframe."""
    import urllib.error
    import urllib.request

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    from apps.preview_runner.runner import runner
    pv = runner.get(proj.id)
    if pv is None:
        raise Http404("No running preview for this project.")
    url = f"http://127.0.0.1:{pv.port}/{path}"
    if request.META.get("QUERY_STRING"):
        url += "?" + request.META["QUERY_STRING"]
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read()
            ctype = resp.headers.get_content_type() or "application/octet-stream"
    except urllib.error.URLError:
        raise Http404("The preview is not responding.")
    from django.http import HttpResponse
    return HttpResponse(body, content_type=ctype)


@login_required
def import_software(request):
    """Import an existing codebase (ZIP upload or Git connect) and analyze it.

    Paused for v1 (BOLDRON_IMPORT_ENABLED). the platform v1 ships "build new software";
    bringing in a customer's existing software returns to the dashboard with a note."""
    from django.conf import settings
    if not settings.BOLDRON_IMPORT_ENABLED:
        messages.info(request, f"Importing existing software isn't available yet — {settings.APP_NAME} "
                               "v1 focuses on building new software. It's coming soon.")
        return redirect("dashboard:home")
    from apps.ingest.analyzer import IngestError, extract_zip, import_codebase
    from apps.ingest.connect import PROVIDERS, fetch_repo_archive, parse_repo

    orgs = list(organizations_for(request.user))
    manageable = [o for o in orgs if o.id in _manageable_ids(request.user)]

    if request.method == "POST":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0))
        name = (request.POST.get("name") or "").strip()
        source = request.POST.get("source") or "zip"
        if org.id not in {o.id for o in manageable} or not name:
            messages.error(request, "Need a name and owner/admin rights in that org.")
            return redirect("dashboard:import")

        # Resolve the chosen source into an in-memory archive.
        try:
            if source == "git":
                provider = request.POST.get("provider") or "github"
                owner, repo = parse_repo(request.POST.get("repo", ""))
                archive = fetch_repo_archive(
                    provider, owner, repo,
                    ref=(request.POST.get("ref") or "").strip(),
                    token=(request.POST.get("token") or "").strip(),
                )
            else:
                upload = request.FILES.get("archive")
                if not upload:
                    messages.error(request, "Choose a .zip of your codebase to import.")
                    return redirect("dashboard:import")
                if upload.size > 20 * 1024 * 1024:
                    messages.error(request, "Archive too large (max 20 MB for now).")
                    return redirect("dashboard:import")
                archive = upload
            files = extract_zip(archive)
        except IngestError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:import")

        project = Project.objects.create(
            organization=org, name=name, mode="import", created_by=request.user
        )
        project.ensure_default_workspace()
        summary = import_codebase(project, files, created_by=request.user)
        stack = ", ".join(f"{r}: {t}" for r, t in summary["stack"].items()) or "unknown stack"
        origin = f"from {PROVIDERS.get(request.POST.get('provider'), 'Git')} " if source == "git" else ""
        messages.success(
            request,
            f"Imported {summary['files']} files {origin}· detected {stack}. "
            f"{settings.APP_NAME} now understands this app — request changes below.",
        )
        return redirect("dashboard:project", pk=project.id)

    return render(request, "dashboard/import.html", {
        "active": "analyze-software", "manageable_orgs": manageable,
    })


@login_required
def people(request):
    """Members, invitations, and teams for the user's organizations."""
    orgs = list(organizations_for(request.user))
    manageable = _manageable_ids(request.user)

    if request.method == "POST":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0))
        if not Membership.objects.filter(organization=org, user=request.user).exists():
            messages.error(request, "Not your organization.")
            return redirect("dashboard:people")
        can_manage = org.id in manageable
        action = request.POST.get("action")
        try:
            # Leaving is allowed for any member (guarded against the last owner).
            if action == "leave":
                members_svc.leave_organization(org, request.user)
                messages.success(request, f"You left {org.name}.")
                return redirect("dashboard:people")
            if not can_manage:
                messages.error(request, "Owner or admin rights required.")
                return redirect("dashboard:people")
            if action == "invite":
                team = None
                if request.POST.get("team"):
                    team = Team.objects.filter(pk=request.POST["team"], organization=org).first()
                inv = invites.create_invitation(
                    org, request.POST.get("email", ""),
                    role=request.POST.get("role") or Role.MEMBER,
                    team=team, invited_by=request.user,
                )
                link = request.build_absolute_uri(
                    reverse("dashboard:accept_invite", args=[inv.token])
                )
                from apps.notifications.email import send_invitation_email
                try:
                    sent = send_invitation_email(inv, link)
                except Exception:
                    sent = 0  # delivery failed; the invite still stands, link below
                note = "invitation email sent" if sent else "email not delivered"
                messages.success(request, f"Invited {inv.email} ({note}). Link: {link}")
            elif action == "revoke":
                inv = get_object_or_404(Invitation, pk=request.POST.get("invitation", 0), organization=org)
                invites.revoke_invitation(inv)
                messages.success(request, f"Revoked the invite for {inv.email}.")
            elif action == "resend":
                inv = get_object_or_404(Invitation, pk=request.POST.get("invitation", 0), organization=org)
                invites.resend_invitation(inv)
                link = request.build_absolute_uri(
                    reverse("dashboard:accept_invite", args=[inv.token]))
                from apps.notifications.email import send_invitation_email
                try:
                    send_invitation_email(inv, link)
                except Exception:
                    pass
                messages.success(request, f"Resent the invite to {inv.email}.")
            elif action == "set_role":
                from apps.accounts.models import User
                target = get_object_or_404(User, pk=request.POST.get("user", 0))
                members_svc.change_member_role(
                    org, target, request.POST.get("role") or Role.MEMBER, actor=request.user)
                messages.success(request, f"Updated {target.email}'s role.")
            elif action == "remove_member":
                from apps.accounts.models import User
                target = get_object_or_404(User, pk=request.POST.get("user", 0))
                members_svc.remove_member(org, target, actor=request.user)
                messages.success(request, f"Removed {target.email} from {org.name}.")
            elif action == "create_team":
                name = (request.POST.get("name") or "").strip()
                if name:
                    Team.objects.create(organization=org, name=name)
                    messages.success(request, f"Team “{name}” created.")
                else:
                    messages.error(request, "Team name required.")
        except (invites.InvitationError, members_svc.MemberError) as exc:
            messages.error(request, str(exc))
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:people")

    cards = []
    for o in orgs:
        cards.append({
            "org": o,
            "can_manage": o.id in manageable,
            "members": Membership.objects.filter(organization=o).select_related("user"),
            "invites": Invitation.objects.filter(organization=o, status=InvitationStatus.PENDING),
            "teams": Team.objects.filter(organization=o).prefetch_related("members"),
            "roles": Role.choices,
        })
    return render(request, "dashboard/people.html", {"active": "people", "cards": cards})


@login_required
def accept_invite(request, token):
    """Accept an organization invitation via its token (must be logged in)."""
    try:
        membership = invites.accept_invitation(token, request.user)
        messages.success(
            request, f"You’ve joined {membership.organization.name} as {membership.role}."
        )
    except invites.InvitationError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:people")


@login_required
def security(request):
    """Per-project security posture from the twin's SECURITY findings, plus an
    on-demand scan (runs the deterministic Security Agent)."""
    orgs = list(organizations_for(request.user))
    manageable = _manageable_ids(request.user)

    if request.method == "POST" and request.POST.get("action") == "run_scan":
        proj = get_object_or_404(
            Project, pk=request.POST.get("project", 0), organization__in=orgs
        )
        if proj.organization_id not in manageable:
            messages.error(request, "Owner or admin rights required to run a scan.")
        else:
            orch = Orchestrator()
            task = orch.create_task(
                project=proj, agent_key="security", input={}, created_by=request.user
            )
            orch.run_task(task)
            task.refresh_from_db()
            note = task.messages[-1] if task.messages else "Scan complete."
            messages.success(request, f"{proj.name}: {note}")
        return redirect("dashboard:security")

    rows = []
    for p in Project.objects.filter(organization__in=orgs).select_related("organization"):
        entries = list(
            ContextEntry.objects.filter(project=p, kind=ContextKind.SECURITY)
        )
        counts = {"high": 0, "medium": 0, "low": 0}
        for e in entries:
            sev = (e.data or {}).get("severity", "low")
            if sev in counts:
                counts[sev] += 1
        rows.append({
            "project": p, "counts": counts, "total": len(entries),
            "findings": entries[:25], "can_manage": p.organization_id in manageable,
        })
    return render(request, "dashboard/security.html", {"active": "security", "rows": rows})


@login_required
def change_detail(request, pk):
    change = get_object_or_404(
        ChangeRequest.objects.filter(
            project__organization__in=organizations_for(request.user)
        ).select_related("project", "migration"),
        pk=pk,
    )
    can_manage = change.project.organization_id in _manageable_ids(request.user)
    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin required.")
            return redirect("dashboard:change", pk=pk)
        action = request.POST.get("action")
        if action == "approve":
            changes_service.approve(change, request.user)
            messages.success(request, "Change approved.")
        elif action == "implement":
            changes_service.implement(change)
            messages.success(request, "Change implemented — agents ran against the project.")
        elif action == "rollback":
            if change.can_rollback:
                changes_service.rollback(change)
                messages.success(request, "Change rolled back — repo restored to its pre-change state.")
            else:
                messages.error(request, "This change can't be rolled back.")
        return redirect("dashboard:change", pk=pk)

    tasks = AgentTask.objects.filter(id__in=change.task_ids or [])
    areas = (change.plan or {}).get("affected_areas", {})
    from apps.changes.impact import analyze_impact
    return render(request, "dashboard/change.html", {
        "active": "projects", "change": change, "can_manage": can_manage,
        "areas": areas, "tasks": tasks, "impact": analyze_impact(change),
    })


def _handle_project_action(request, proj):
    action = request.POST.get("action")
    orch = Orchestrator()
    if action == "create_task":
        key = request.POST.get("agent_key")
        if key in agent_registry:
            orch.create_task(project=proj, agent_key=key,
                             input={"brief": (request.POST.get("brief") or "").strip()},
                             created_by=request.user)
            messages.success(request, f"Queued a {key} task.")
        else:
            messages.error(request, "Unknown agent.")
    elif action == "run":
        processed = orch.run_ready(proj)
        messages.success(request, f"Ran {len(processed)} task(s).")
    elif action == "select_stack":
        chosen = {r: request.POST.get(r) for r in ROLES if request.POST.get(r) in tech_registry}
        proj.technology = {**(proj.technology or {}), **chosen}
        proj.save(update_fields=["technology", "updated_at"])
        messages.success(request, "Stack updated.")
    elif action == "create_backup":
        from apps.backups.service import BackupError, create_backup
        try:
            b = create_backup(proj, label=request.POST.get("label") or "Snapshot",
                              created_by=request.user)
            messages.success(request, f"Backup “{b.label}” created.")
        except BackupError as exc:
            messages.error(request, str(exc))
    elif action == "restore_backup":
        from apps.backups.models import ProjectBackup
        from apps.backups.service import BackupError, restore_backup
        backup = ProjectBackup.objects.filter(
            pk=request.POST.get("backup", 0), project=proj).first()
        if backup is None:
            messages.error(request, "No such backup.")
        else:
            try:
                restore_backup(backup, actor=request.user)
                messages.success(request, f"Restored “{backup.label}”.")
            except BackupError as exc:
                messages.error(request, str(exc))


# --- engineering / project lists (real data) --------------------------------

# Customer-facing capabilities — outcomes only. The internal agent roster,
# capability model and orchestration are proprietary and never exposed here.
_CAPABILITIES = [
    ("Build", "Turn a brief into working, tested websites and web apps in the stack you choose."),
    ("Web & mobile", "Publish websites to a live URL, and design mobile apps and prepare their Android & iOS releases for the app stores."),
    ("Test", "Every change is compiled and its tests actually run before it's called done."),
    ("Secure", "Code is scanned for secrets, injection and unsafe patterns as part of each change."),
    ("Deploy", "Promote to dev and staging; production changes stay behind an approval gate."),
    ("Operate", "Track cost and activity per project, with rollback on any change."),
]


@login_required
def agents(request):
    return render(request, "dashboard/agents.html", {
        "active": "agents",
        "capabilities": [{"title": t, "blurb": b} for t, b in _CAPABILITIES],
    })


@login_required
def tasks(request):
    orgs = organizations_for(request.user)
    rows = (
        AgentTask.objects.filter(project__organization__in=orgs)
        .select_related("project").order_by("-created_at")[:100]
    )
    return render(request, "dashboard/tasks.html", {"active": "tasks", "tasks": rows})


@login_required
def deployments(request):
    orgs = organizations_for(request.user)
    rows = (
        Deployment.objects.filter(project__organization__in=orgs)
        .select_related("project").order_by("-created_at")[:100]
    )
    return render(request, "dashboard/deployments.html", {"active": "deployments", "deployments": rows})


@login_required
def usage(request):
    orgs = list(organizations_for(request.user))
    manageable = _manageable_ids(request.user)

    if request.method == "POST" and request.POST.get("action") == "generate_invoice":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0))
        if org.id in manageable:
            from apps.credits.services import generate_invoice
            inv = generate_invoice(org)
            messages.success(
                request,
                f"Statement for {inv.period_start:%B %Y}: ${inv.subtotal_usd:.2f} "
                f"({inv.credits_used:.0f} credits).",
            )
        else:
            messages.error(request, "Owner or admin rights required.")
        return redirect("dashboard:usage")

    records = (
        UsageRecord.objects.filter(organization__in=orgs)
        .select_related("project").order_by("-created_at")[:100]
    )
    spend = sum((r.cost_usd for r in records), Decimal("0"))
    credits = sum((r.credits_charged for r in records), Decimal("0"))
    accounts = CreditAccount.objects.filter(organization__in=orgs)
    invoices = Invoice.objects.filter(organization__in=orgs).select_related("organization")
    return render(request, "dashboard/usage.html", {
        "active": "usage", "records": records, "spend": spend,
        "credits": credits, "accounts": accounts, "invoices": invoices,
        "manageable_orgs": [o for o in orgs if o.id in manageable],
    })


# --- honest placeholder for areas without a backend yet ---------------------

@login_required
def soon(request, slug):
    return render(request, "dashboard/soon.html", {
        "active": slug, "title": slug.replace("-", " ").title(),
    })


# --- Real workspace pages (were SOON) ---------------------------------------

_SECTION = {
    "apis": ([ContextKind.API], "APIs", f"HTTP endpoints {settings.APP_NAME} has designed for your apps."),
    "database": ([ContextKind.SCHEMA], "Database", "Data models, detected databases, and migrations."),
    "tests": ([ContextKind.TESTING], "Tests", f"Test cases {settings.APP_NAME} has designed across your projects."),
    "code-issues": ([ContextKind.REVIEW, ContextKind.SECURITY], "Code Issues",
                    "Review findings and security scan results across your projects."),
}


@login_required
def section(request, slug):
    """A slice of the digital twin (APIs / schema / tests / issues) per project."""
    meta = _SECTION.get(slug)
    if meta is None:
        raise Http404
    kinds, title, sub = meta
    from apps.database.models import DatabaseMigration
    rows = []
    for p in Project.objects.filter(
        organization__in=organizations_for(request.user)
    ).select_related("organization"):
        entries = list(ContextEntry.objects.filter(project=p, kind__in=kinds))
        extra = {}
        if slug == "database":
            extra = {"db": (p.technology or {}).get("database"),
                     "migrations": DatabaseMigration.objects.filter(project=p).count()}
        if entries or extra.get("db") or extra.get("migrations"):
            rows.append({"project": p, "entries": entries[:60], "count": len(entries), **extra})
    return render(request, "dashboard/section.html", {
        "active": slug, "title": title, "sub": sub, "rows": rows, "slug": slug,
    })


@login_required
def repository(request):
    """Browse the generated source and git history of each project."""
    from apps.repositories.service import repo_for_project
    rows = []
    for p in Project.objects.filter(
        organization__in=organizations_for(request.user)
    ).select_related("organization"):
        repo = repo_for_project(p)
        if not repo.is_initialized:
            rows.append({"project": p, "files": [], "log": []})
            continue
        rows.append({"project": p, "files": repo.list_files()[:100], "log": repo.log(10)})
    return render(request, "dashboard/repository.html", {"active": "repository", "rows": rows})


@login_required
def templates_page(request):
    """Starter templates = the technology stacks the platform can build and run."""
    from apps.technology.stacks import all_stacks
    stacks = [
        {"id": s.id, "language": s.language, "framework": s.framework,
         "kind": s.kind, "runnable": s.is_runnable()}
        for s in all_stacks()
    ]
    return render(request, "dashboard/templates.html", {"active": "templates", "stacks": stacks})


def _logout_other_sessions(request) -> int:
    """Delete every OTHER active session belonging to this user (keeps the current
    one). Works with the database session backend. Returns how many were removed."""
    from django.contrib.sessions.models import Session
    from django.utils import timezone as tz

    current = request.session.session_key
    removed = 0
    uid = str(request.user.pk)
    for s in Session.objects.filter(expire_date__gte=tz.now()).iterator():
        if s.session_key == current:
            continue
        if str(s.get_decoded().get("_auth_user_id")) == uid:
            s.delete()
            removed += 1
    return removed


@login_required
def account(request):
    """Account & security: update profile, change password, sign out other sessions."""
    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.forms import PasswordChangeForm
    from apps.accounts.models import User

    user = request.user
    pwd_form = PasswordChangeForm(user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profile":
            full_name = (request.POST.get("full_name") or "").strip()[:255]
            email = User.objects.normalize_email(request.POST.get("email") or "")
            if not email:
                messages.error(request, "Email can't be blank.")
            elif User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                messages.error(request, "That email is already in use by another account.")
            else:
                user.full_name, user.email = full_name, email
                user.job_title = (request.POST.get("job_title") or "").strip()[:120]
                user.pronouns = (request.POST.get("pronouns") or "").strip()[:40]
                user.bio = (request.POST.get("bio") or "").strip()[:1000]
                user.save(update_fields=["full_name", "email", "job_title", "pronouns", "bio"])
                messages.success(request, "Profile updated.")
                return redirect("dashboard:account")
        elif action == "password":
            pwd_form = PasswordChangeForm(user, request.POST)
            if pwd_form.is_valid():
                pwd_form.save()
                # Keep THIS session; the password change invalidates the others.
                update_session_auth_hash(request, user)
                from apps.accounts import security as _sec
                from apps.accounts.models import LoginEvent as _LE
                _sec.record_event(user, request, _LE.PASSWORD_CHANGED)
                messages.success(request, "Password changed — other sessions were signed out.")
                return redirect("dashboard:account")
            messages.error(request, "Please fix the errors below.")
        elif action == "sessions":
            n = _logout_other_sessions(request)
            messages.success(request, f"Signed out of {n} other session(s).")
            return redirect("dashboard:account")
        elif action == "avatar":
            from apps.accounts.avatars import AvatarError, save_avatar
            try:
                save_avatar(user, request.FILES.get("avatar"))
                messages.success(request, "Profile photo updated.")
            except AvatarError as exc:
                messages.error(request, str(exc))
            return redirect("dashboard:account")
        elif action == "remove_avatar":
            if user.avatar:
                user.avatar.delete(save=True)
                messages.success(request, "Profile photo removed.")
            return redirect("dashboard:account")

    return render(request, "dashboard/account.html", {"active": "account", "pwd_form": pwd_form})


def verify_email(request, token):
    """Confirm an email from a signed link (public — the user may be logged out)."""
    from apps.accounts import verification
    user, reason = verification.verify(token)
    if user:
        verification.mark_verified(user)
        return render(request, "dashboard/verify_email.html", {"ok": True})
    return render(request, "dashboard/verify_email.html", {"ok": False, "reason": reason})


@login_required
def resend_verification(request):
    from apps.accounts import verification
    if request.user.email_verified:
        messages.info(request, "Your email is already verified.")
    elif request.method == "POST":
        verification.send_verification(request, request.user)
        messages.success(request, "Verification email sent — check your inbox.")
    return redirect("dashboard:home")


# Plan presentation lives in the shared credits catalog so the web Settings hub
# and the mobile billing API read the same source.
from apps.credits.catalog import PLAN_FEATURES as _PLAN_FEATURES  # noqa: E402
from apps.credits.catalog import PLAN_LABEL as _PLAN_LABEL  # noqa: E402
from apps.credits.catalog import PLAN_ORDER as _PLAN_ORDER  # noqa: E402
from apps.credits.catalog import PLAN_PRICE as _PLAN_PRICE  # noqa: E402
_LANGUAGES = [("", "English (default)"), ("en-us", "English (US)"), ("en-gb", "English (UK)"),
              ("es", "Español"), ("fr", "Français"), ("de", "Deutsch"), ("pt", "Português"),
              ("af", "Afrikaans"), ("ar", "العربية")]
_TIMEZONES = ["", "UTC", "Africa/Johannesburg", "Europe/London", "Europe/Berlin",
              "America/New_York", "America/Chicago", "America/Los_Angeles",
              "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Australia/Sydney"]


@login_required
def security_center(request):
    """Account Security Center (spec §9): password + MFA status, active sessions
    with device/last-active + revoke, and recent login history."""
    from apps.accounts import mfa, security as sec

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "revoke":
            sec.revoke_session_by_id(request.user, request.POST.get("session", 0), request=request)
            messages.success(request, "Signed out of that session.")
            return redirect("dashboard:security_center")
        if action == "mfa_disable":
            if not request.user.check_password(request.POST.get("password") or ""):
                messages.error(request, "Your current password is required to disable two-factor auth.")
            elif mfa.disable(request.user):
                from apps.settings import service as _svc
                _svc.audit_change("mfa.disabled", actor=request.user, summary="MFA disabled")
                messages.success(request, "Two-factor authentication disabled.")
            return redirect("dashboard:security_center")

    current = request.session.session_key
    return render(request, "dashboard/security_center.html", {
        "active": "settings",
        "status": sec.security_status(request.user),
        "sessions": [sec.session_dict(s, current_key=current)
                     for s in sec.active_sessions(request.user)],
        "history": [sec.event_dict(e) for e in request.user.login_events.all()[:25]],
    })


@login_required
def mfa_setup(request):
    """Enrol a TOTP second factor: GET shows a QR + manual secret and asks for a
    code; POST confirms the code, enables MFA, and reveals the one-time recovery
    codes. Already-enabled accounts are sent back to the Security Center."""
    from apps.accounts import mfa

    if mfa.is_enabled(request.user):
        messages.info(request, "Two-factor authentication is already enabled.")
        return redirect("dashboard:security_center")

    if request.method == "POST":
        codes = mfa.confirm_enrollment(request.user, request.POST.get("code") or "")
        if codes is None:
            messages.error(request, "That code isn't valid. Scan the QR and try the latest code.")
            return redirect("dashboard:mfa_setup")
        from apps.settings import service as _svc
        _svc.audit_change("mfa.enabled", actor=request.user, summary="MFA enabled")
        return render(request, "dashboard/mfa_recovery_codes.html",
                      {"active": "settings", "codes": codes})

    enroll = mfa.begin_enrollment(request.user)
    return render(request, "dashboard/mfa_setup.html", {
        "active": "settings",
        "secret": enroll["secret"],
        "qr_svg": enroll["qr_svg"],
    })


@login_required
def settings_center(request):
    """The Settings control center: a status-aware overview of the whole
    platform's settings, scoped to user / organization / project. Reads the
    shared settings service (no new source of truth); sections that aren't wired
    yet are shown honestly as upcoming, not faked."""
    from apps.settings import service

    return render(request, "dashboard/settings_center.html", {
        "active": "settings",
        "overview": service.overview(request.user),
    })


@login_required
def org_settings(request):
    """Organization general settings (spec §15): name + description per org.
    Editing is gated by the real RBAC permission; members see it read-only."""
    from apps.organizations.permissions import has_perm, permissions_for_member

    orgs = list(organizations_for(request.user).order_by("name"))

    if request.method == "POST":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0),
                                memberships__user=request.user)
        if not has_perm(request.user, org, "org.manage"):
            messages.error(request, "You don't have permission to edit this organization.")
            return redirect("dashboard:org_settings")
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Organization name can't be blank.")
        else:
            org.name = name
            org.description = (request.POST.get("description") or "").strip()[:2000]
            org.save(update_fields=["name", "description", "updated_at"])
            from apps.settings.service import audit_change
            audit_change("organization.updated", actor=request.user, organization=org,
                         summary="updated general settings")
            messages.success(request, "Organization settings saved.")
        return redirect("dashboard:org_settings")

    cards = [{
        "org": o,
        "can_manage": has_perm(request.user, o, "org.manage"),
        "role": o.memberships.get(user=request.user).role,
        "members": o.memberships.count(),
        "projects": o.projects.count() if hasattr(o, "projects") else 0,
    } for o in orgs]
    return render(request, "dashboard/org_settings.html",
                  {"active": "settings", "cards": cards})


@login_required
def org_roles(request):
    """Roles & permissions (spec §16): an honest reference of what each built-in
    role can do, plus the caller's own role per organization. Role assignment
    lives on the Members page."""
    from apps.organizations.permissions import permissions_for_member, role_matrix

    roles = list(Role)
    # Flatten the matrix into cells aligned to the role column order (templates
    # can't index a dict by a loop variable).
    rows = [{
        "label": row["label"],
        "description": row["description"],
        "cells": [row["roles"][r.value] for r in roles],
    } for row in role_matrix()]

    orgs = list(organizations_for(request.user).order_by("name"))
    my_orgs = [{
        "org": o,
        "role": o.memberships.get(user=request.user).role,
        "permissions": permissions_for_member(request.user, o),
    } for o in orgs]
    return render(request, "dashboard/org_roles.html", {
        "active": "settings",
        "rows": rows,
        "roles": roles,
        "my_orgs": my_orgs,
    })


@login_required
def org_ai(request):
    """Organization AI settings (spec §19): a soft preferred provider/model for
    the org's builds. Keys stay environment-only; this only chooses among the
    providers already connected. Editing requires org management rights."""
    from apps.ai_providers.registry import generation_status
    from apps.organizations import ai_settings
    from apps.organizations.permissions import has_perm

    orgs = list(organizations_for(request.user).order_by("name"))

    if request.method == "POST":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0),
                                memberships__user=request.user)
        if not has_perm(request.user, org, "org.manage"):
            messages.error(request, "You don't have permission to change AI settings.")
            return redirect("dashboard:org_ai")
        try:
            ai_settings.set_preferences(
                org,
                preferred_provider=request.POST.get("preferred_provider", ""),
                preferred_model=request.POST.get("preferred_model", ""),
                actor=request.user,
            )
            messages.success(request, "AI settings saved.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:org_ai")

    cards = [{
        "org": o,
        "can_manage": has_perm(request.user, o, "org.manage"),
        "prefs": ai_settings.preferences_for(o),
    } for o in orgs]
    return render(request, "dashboard/org_ai.html", {
        "active": "settings",
        "cards": cards,
        "options": ai_settings.available_options(),
        "generation": generation_status(),
    })


@login_required
def project_jobs(request, pk):
    """Background jobs for a project (spec §20). Start a report, watch real
    status (queued → running → done/failed), read the result. Status is never
    faked — a job is 'completed' only when its handler actually finished."""
    from apps.jobs import service as jobs_svc

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)

    if request.method == "POST" and request.POST.get("action") == "run":
        kind = request.POST.get("kind", "")
        try:
            jobs_svc.enqueue(kind, organization=proj.organization, project=proj,
                             created_by=request.user)
            messages.success(request, "Job started — it runs in the background.")
        except jobs_svc.JobError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:jobs", pk=pk)

    jobs = list(proj.jobs.all()[:30])
    return render(request, "dashboard/jobs.html", {
        "active": "projects", "project": proj, "jobs": jobs,
        "kinds": jobs_svc.kinds(),
    })


@login_required
def project_payments(request, pk):
    """Payments surface (spec §24): connected providers (honest, env-gated), the
    transaction history, and a real money summary. Read-only; confirming and
    refunding happen on the order itself."""
    from apps.publishing.ecommerce_service import payment_overview

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    return render(request, "dashboard/payments.html",
                  {"active": "projects", "project": proj,
                   "overview": payment_overview(proj)})


@login_required
def project_files(request, pk):
    """A project's files & media (spec §17). Any member can upload and view;
    deleting is for the uploader or a manager. Private files are served only to
    members; public files get an unguessable shareable link."""
    from apps.files import service as files_svc
    from apps.files.models import StoredFile

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "upload":
            try:
                files_svc.store(
                    request.FILES.get("file"), organization=proj.organization,
                    project=proj, uploaded_by=request.user,
                    is_public=request.POST.get("is_public") == "on")
                messages.success(request, "File uploaded.")
            except files_svc.FileError as exc:
                messages.error(request, str(exc))
        elif action == "delete":
            sf = get_object_or_404(StoredFile, pk=request.POST.get("file", 0), project=proj)
            if can_manage or sf.uploaded_by_id == request.user.id:
                files_svc.delete_file(sf)
                messages.success(request, "File deleted.")
            else:
                messages.error(request, "You can only delete files you uploaded.")
        return redirect("dashboard:files", pk=pk)

    files = [files_svc.public_dict(f, request=request) for f in proj.stored_files.all()]
    return render(request, "dashboard/files.html",
                  {"active": "projects", "project": proj, "files": files})


@login_required
def project_environment(request, pk):
    """A project's environment variables (spec §20). Members view; owners/admins
    edit. Values set here are really injected into the project's preview run."""
    from apps.projects import env as envsvc

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk
    )
    can_manage = proj.organization_id in _manageable_ids(request.user)

    try:
        selected_env = envsvc.validate_environment(request.GET.get("env", "development"))
    except envsvc.EnvVarError:
        selected_env = "development"

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:environment", pk=pk)
        action = request.POST.get("action")
        post_env = request.POST.get("environment", "development")
        if action == "set":
            try:
                var = envsvc.set_var(
                    proj, request.POST.get("key", ""), request.POST.get("value", ""),
                    is_secret=request.POST.get("is_secret") == "on",
                    environment=post_env,
                )
                from apps.settings.service import audit_change
                audit_change("project.env_set", actor=request.user,
                             organization=proj.organization,
                             summary=f"{proj.name}: set {var.key} ({var.environment})")
                messages.success(request, "Variable saved.")
                selected_env = var.environment
            except envsvc.EnvVarError as exc:
                messages.error(request, str(exc))
        elif action == "delete":
            envsvc.delete_var(proj, request.POST.get("var", 0))
            messages.success(request, "Variable deleted.")
        return redirect(f"{reverse('dashboard:environment', args=[pk])}?env={selected_env}")

    return render(request, "dashboard/environment.html", {
        "active": "projects",
        "project": proj,
        "can_manage": can_manage,
        "environments": envsvc.environments(),
        "selected_env": selected_env,
        "vars": [envsvc.public_dict(v) for v in envsvc.list_vars(proj, environment=selected_env)],
    })


@login_required
def notifications_settings(request):
    """Per-user notification preferences (spec §24). Opt-out; only categories
    wired to a real email are shown."""
    from apps.notifications import preferences

    if request.method == "POST":
        # Unchecked checkboxes aren't submitted, so build the full set explicitly.
        values = {c["key"]: (request.POST.get(c["key"]) == "on")
                  for c in preferences.CATEGORIES}
        preferences.update(request.user, values)
        messages.success(request, "Notification preferences saved.")
        return redirect("dashboard:notifications_settings")

    prefs = preferences.as_dict(request.user)
    rows = [{**c, "on": prefs.get(c["key"], True)} for c in preferences.CATEGORIES]
    return render(request, "dashboard/notifications.html", {
        "active": "settings",
        "rows": rows,
    })


@login_required
def org_audit(request):
    """Read-only organization audit log (spec §27). Sensitive — managers only."""
    from apps.audit.service import event_dict, events_for
    from apps.organizations.permissions import has_perm

    orgs = [o for o in organizations_for(request.user).order_by("name")
            if has_perm(request.user, o, "org.manage")]
    selected_id = request.GET.get("org")
    selected = None
    if orgs:
        selected = next((o for o in orgs if str(o.id) == str(selected_id)), orgs[0])
    events = [event_dict(e) for e in events_for(selected)] if selected else []
    return render(request, "dashboard/org_audit.html", {
        "active": "settings",
        "orgs": orgs,
        "selected": selected,
        "events": events,
    })


@login_required
def org_data(request):
    """Data export (spec §25): download the account's data, or (for managers) the
    organization's data, as JSON. No secret values are included."""
    from apps.organizations.permissions import has_perm

    orgs = list(organizations_for(request.user).order_by("name"))
    manageable = [o for o in orgs if has_perm(request.user, o, "org.manage")]
    return render(request, "dashboard/org_data.html", {
        "active": "settings",
        "manageable": manageable,
    })


@login_required
def export_account_data(request):
    from django.http import JsonResponse
    from apps.settings.data_export import export_account

    resp = JsonResponse(export_account(request.user), json_dumps_params={"indent": 2})
    resp["Content-Disposition"] = 'attachment; filename="account-data.json"'
    return resp


@login_required
def export_org_data(request, pk):
    from django.http import JsonResponse
    from apps.organizations.permissions import has_perm
    from apps.settings.data_export import export_organization

    org = get_object_or_404(Organization, pk=pk, memberships__user=request.user)
    if not has_perm(request.user, org, "org.manage"):
        messages.error(request, "Owner or admin rights required.")
        return redirect("dashboard:org_data")
    resp = JsonResponse(export_organization(org), json_dumps_params={"indent": 2})
    resp["Content-Disposition"] = f'attachment; filename="{org.slug}-data.json"'
    return resp


@login_required
def connected_accounts(request):
    """Connected accounts / single sign-on (spec §8). SSO is an operator
    integration: it only appears when an identity provider is configured in the
    environment. Honest — nothing is shown as linked unless it genuinely is."""
    providers = []
    for key, env in (("Google", "GOOGLE_OAUTH_CLIENT_ID"),
                     ("GitHub", "GITHUB_OAUTH_CLIENT_ID"),
                     ("Microsoft", "MICROSOFT_OAUTH_CLIENT_ID")):
        providers.append({"name": key, "configured": bool(os.environ.get(env))})
    return render(request, "dashboard/connected_accounts.html", {
        "active": "settings", "providers": providers,
        "any_configured": any(p["configured"] for p in providers),
    })


@login_required
def org_domains(request):
    """Custom domains across the organization's projects (spec §17). Reads the
    real publishing CustomDomain records; verification reflects a real DNS check."""
    from apps.publishing.models import CustomDomain

    orgs = list(organizations_for(request.user).order_by("name"))
    domains = (
        CustomDomain.objects
        .filter(website__project__organization__in=orgs)
        .select_related("website__project", "website__project__organization")
        .order_by("website__project__organization__name", "hostname")
    )
    rows = [{
        "hostname": d.hostname,
        "status": d.verification_status,
        "verified": d.is_verified,
        "project": d.website.project,
    } for d in domains]
    return render(request, "dashboard/org_domains.html",
                  {"active": "domains", "rows": rows})


@login_required
def org_commerce(request):
    """Commerce overview across the organization's stores (spec §32). The store
    itself is configured per project (publishing); this is a real read-only
    rollup of products and orders."""
    from apps.publishing.models import Order, Product, Website

    orgs = list(organizations_for(request.user))
    stores = []
    for site in (Website.objects
                 .filter(project__organization__in=orgs)
                 .select_related("project")):
        products = Product.objects.filter(website=site).count()
        if not products:
            continue
        orders = Order.objects.filter(website=site).count()
        stores.append({"project": site.project, "products": products, "orders": orders})
    return render(request, "dashboard/org_commerce.html",
                  {"active": "settings", "stores": stores})


@login_required
def org_documents(request):
    """Project export documents (spec §28). Each project can export a real
    archive (README, API spec, data model, generated source) built on demand."""
    projects = (Project.objects
                .filter(organization__in=organizations_for(request.user))
                .select_related("organization").order_by("organization__name", "name"))
    return render(request, "dashboard/org_documents.html",
                  {"active": "settings", "projects": projects})


@login_required
def project_documents_download(request, pk):
    from django.http import HttpResponse
    from apps.exporter.service import build_export

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    filename, data = build_export(proj)
    resp = HttpResponse(data, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
def org_privacy(request):
    """Privacy & data handling (spec §26): what the platform stores, links to the
    real data export, and a genuine data-deletion request (filed as a support
    ticket for a human to action — never an instant irreversible wipe)."""
    orgs = list(organizations_for(request.user).order_by("name"))
    if request.method == "POST" and request.POST.get("action") == "request_deletion":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0),
                                memberships__user=request.user)
        from apps.support.service import create_ticket
        t = create_ticket(
            organization=org, user=request.user, category="account", priority="high",
            subject=f"Data deletion request — {org.name}",
            body=f"{request.user.email} requested deletion of data for “{org.name}”.",
        )
        messages.success(request, f"Deletion request submitted ({t.number}). Our team "
                                  "will confirm before anything is removed.")
        return redirect("dashboard:org_privacy")
    return render(request, "dashboard/org_privacy.html",
                  {"active": "settings", "orgs": orgs})


@login_required
def project_ai(request, pk):
    """Per-project AI preference (spec §18). Overrides the org default for this
    project's builds; soft (falls back when unavailable). Managers only."""
    from apps.ai_providers.registry import generation_status
    from apps.projects import ai_settings as pai

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:project_ai", pk=pk)
        try:
            pai.set_preferences(
                proj, preferred_provider=request.POST.get("preferred_provider", ""),
                preferred_model=request.POST.get("preferred_model", ""), actor=request.user)
            messages.success(request, "Project AI settings saved.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:project_ai", pk=pk)

    return render(request, "dashboard/project_ai.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "own": pai.own_preferences(proj), "effective": pai.preferences_for(proj),
        "options": pai.available_options(), "generation": generation_status(),
    })


@login_required
def project_repository(request, pk):
    """The project's source repository (spec §22). Shows the real local git repo
    state. Connecting an external remote (GitHub/GitLab) needs an operator
    integration and is reported honestly as unavailable until configured."""
    from apps.repositories.service import GitError, repo_for_project

    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    repo = repo_for_project(proj)
    info = {"initialized": repo.is_initialized, "files": 0, "branch": None}
    if repo.is_initialized:
        try:
            info["files"] = len(repo.list_files())
            info["branch"] = repo.current_branch()
        except GitError:
            pass
    remote_configured = bool(os.environ.get("GIT_REMOTE_TOKEN"))
    return render(request, "dashboard/project_repository.html", {
        "active": "projects", "project": proj, "info": info,
        "remote_configured": remote_configured,
    })


@login_required
def analyze(request):
    """Pre-build requirements analysis (spec §30): given a brief, return the
    capabilities the app would need, grouped and with an honest built/coming
    split. Lets the customer see the plan before building."""
    from django.http import JsonResponse

    from apps.capabilities.analysis import analyze as run_analysis

    brief = request.POST.get("brief", "") if request.method == "POST" else request.GET.get("brief", "")
    return JsonResponse(run_analysis(brief))


@login_required
def set_theme(request):
    """Persist the user's colour-theme choice (dark / light / system)."""
    from django.http import HttpResponse
    from apps.accounts.models import User

    if request.method != "POST":
        return HttpResponse(status=405)
    theme = (request.POST.get("theme") or "").strip()
    if theme in dict(User.THEME_CHOICES):
        request.user.theme = theme
        request.user.save(update_fields=["theme"])
    return HttpResponse(status=204)


@login_required
def project_comments(request, pk):
    """A project's comment thread (spec §4): members discuss and @mention each other.
    Any member can post; a @handle resolves only to a member of the same org."""
    from apps.comments import service as comments
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)

    if request.method == "POST":
        try:
            comments.post_comment(proj, request.user, request.POST.get("body", ""))
        except comments.CommentError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:project_comments", pk=pk)

    members = [{"name": m.user.display_name,
                "handle": (m.user.email or "").split("@", 1)[0]}
               for m in comments._org_members(proj.organization) if m.user]
    return render(request, "dashboard/project_comments.html", {
        "active": "projects", "project": proj,
        "comments": comments.comments_for(proj), "members": members,
    })


@login_required
def project_incidents(request, pk):
    """A project's incidents (spec §20): the lifecycle board + per-incident timeline
    and actions. Members view; owners/admins open, note and transition. The AI can
    analyse, but only a person resolves an incident."""
    from apps.incidents import service as inc
    from apps.incidents.models import Incident, IncidentStatus
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:project_incidents", pk=pk)
        action = request.POST.get("action")
        try:
            if action == "open":
                inc.open_incident(proj, title=request.POST.get("title", ""),
                                  severity=request.POST.get("severity", "medium"),
                                  detail=request.POST.get("detail", ""), user=request.user)
                messages.success(request, "Incident opened.")
            elif action == "transition":
                incident = get_object_or_404(Incident, pk=request.POST.get("incident", 0), project=proj)
                inc.transition(incident, request.POST.get("status", ""),
                               note=request.POST.get("note", ""), user=request.user)
                inc.set_resolution(incident, resolution=request.POST.get("resolution", ""),
                                   postmortem=request.POST.get("postmortem", ""), user=request.user)
                messages.success(request, "Incident updated.")
            elif action == "note":
                incident = get_object_or_404(Incident, pk=request.POST.get("incident", 0), project=proj)
                inc.add_note(incident, request.POST.get("text", ""), user=request.user)
            elif action == "analyze":
                incident = get_object_or_404(Incident, pk=request.POST.get("incident", 0), project=proj)
                inc.analyze(incident, user=request.user)
                messages.success(request, "Analysis added — the incident stays open until you resolve it.")
        except inc.IncidentError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:project_incidents", pk=pk)

    incidents = list(proj.incidents.prefetch_related("events")[:50])
    return render(request, "dashboard/project_incidents.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "incidents": incidents, "summary": inc.summary(proj),
        "statuses": IncidentStatus.choices,
    })


@login_required
def project_acceptance(request, pk):
    """A project's acceptance criteria (spec §3): the testable conditions each
    requirement must meet, with an HONEST status. Members view; owners/admins
    import, add and verify. The AI never marks a criterion met — a person does."""
    from apps.acceptance import service as acc
    from apps.acceptance.models import AcceptanceCriterion, CriterionStatus
    from apps.project_context.models import ContextKind
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:project_acceptance", pk=pk)
        action = request.POST.get("action")
        try:
            if action == "import":
                n = acc.import_from_requirements(proj, user=request.user)
                messages.success(request, f"Imported {n} criteria from requirements."
                                 if n else "No new criteria to import.")
            elif action == "add":
                requirement = None
                req_id = request.POST.get("requirement")
                if req_id:
                    requirement = get_object_or_404(
                        proj.context_entries, pk=req_id, kind=ContextKind.REQUIREMENT)
                acc.add(proj, request.POST.get("statement", ""),
                        requirement=requirement, user=request.user)
                messages.success(request, "Criterion added.")
            elif action == "verify":
                crit = get_object_or_404(
                    AcceptanceCriterion, pk=request.POST.get("criterion", 0), project=proj)
                acc.verify(crit, request.POST.get("status", ""),
                           note=request.POST.get("note", ""), user=request.user)
        except acc.AcceptanceError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:project_acceptance", pk=pk)

    # Group criteria by their requirement (with an "unlinked" bucket last).
    crits = list(proj.acceptance_criteria.select_related("requirement", "verified_by"))
    groups: dict = {}
    for c in crits:
        key = c.requirement_id or 0
        groups.setdefault(key, {"title": c.requirement_title or "Other criteria",
                                "items": []})["items"].append(c)
    grouped = [groups[k] for k in sorted(groups, key=lambda k: (k == 0, k))]
    requirements = proj.context_entries.filter(kind=ContextKind.REQUIREMENT)
    return render(request, "dashboard/project_acceptance.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "summary": acc.summary(proj), "grouped": grouped,
        "requirements": requirements, "statuses": CriterionStatus.choices,
    })


@login_required
def project_automations(request, pk):
    """A project's automations (spec §10-11): trigger → conditions → actions, with
    a run history that records each action's honest outcome. Members view and
    test-run; owners/admins create, edit and change status. Actions that need
    unconfigured capabilities are skipped honestly, never faked."""
    import json

    from apps.automations import engine, service
    from apps.automations.actions import ACTIONS
    from apps.automations.models import Workflow, WorkflowStatus
    from apps.automations.triggers import TRIGGERS
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)
    last_run = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "run":   # test-run is a safe action any member may do
            wf = get_object_or_404(Workflow, pk=request.POST.get("workflow", 0), project=proj)
            try:
                facts = json.loads(request.POST.get("facts") or "{}")
                if not isinstance(facts, dict):
                    raise ValueError
                last_run = engine.run_now(wf, facts, user=request.user)
            except (ValueError, json.JSONDecodeError):
                messages.error(request, "Facts must be a JSON object.")
        elif not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:project_automations", pk=pk)
        else:
            try:
                if action == "add":
                    conditions, actions = [], []
                    if request.POST.get("conditions", "").strip():
                        conditions = json.loads(request.POST["conditions"])
                    actions = json.loads(request.POST.get("actions") or "[]")
                    service.create(
                        proj, name=request.POST.get("name", ""),
                        trigger=request.POST.get("trigger", ""),
                        description=request.POST.get("description", ""),
                        conditions=conditions, actions=actions, user=request.user)
                    messages.success(request, "Automation created.")
                    return redirect("dashboard:project_automations", pk=pk)
                elif action == "status":
                    wf = get_object_or_404(Workflow, pk=request.POST.get("workflow", 0), project=proj)
                    service.set_status(wf, request.POST.get("status", ""), user=request.user)
                    return redirect("dashboard:project_automations", pk=pk)
            except json.JSONDecodeError:
                messages.error(request, "Conditions / actions must be valid JSON.")
            except service.AutomationError as exc:
                messages.error(request, str(exc))

    automations = list(proj.automations.prefetch_related("runs"))
    for wf in automations:   # annotate a readable trigger label for the template
        wf.trigger_label = TRIGGERS.get(wf.trigger, {}).get("label", wf.trigger)
    return render(request, "dashboard/project_automations.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "summary": service.summary(proj), "automations": automations,
        "triggers": TRIGGERS, "actions_catalog": ACTIONS,
        "statuses": WorkflowStatus.choices, "last_run": last_run,
    })


@login_required
def project_health(request, pk):
    """A project's composed Health Score (spec §30): one honest signal built from
    the real security, test, incident, acceptance and deployment ledgers. Read-only
    and customer-safe — a project with no signal scores 'unknown', never a fake 100."""
    from apps.health.score import health_score
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    return render(request, "dashboard/project_health.html", {
        "active": "projects", "project": proj, "health": health_score(proj),
    })


@login_required
def project_rules(request, pk):
    """A project's formal business rules (spec §12-13): categorised policies with
    an honest enforced/documented split and a draft→active→retired lifecycle.
    Members view and test rules against facts; owners/admins import, add and
    change status. Enforcement is deterministic — never invented."""
    import json

    from apps.business_rules import service as rules
    from apps.business_rules.engine import evaluate
    from apps.business_rules.models import BusinessRule, RuleCategory, RuleStatus
    from apps.project_context.models import ContextKind
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)
    evaluation = None

    if request.method == "POST":
        action = request.POST.get("action")
        # Evaluating rules is a read — any member may test the rule set.
        if action == "evaluate":
            try:
                facts = json.loads(request.POST.get("facts") or "{}")
                if not isinstance(facts, dict):
                    raise ValueError
                evaluation = evaluate(proj, facts)
            except (ValueError, json.JSONDecodeError):
                messages.error(request, "Facts must be a JSON object, e.g. {\"total\": 1500}.")
        elif not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:project_rules", pk=pk)
        else:
            try:
                if action == "import":
                    n = rules.import_from_context(proj, user=request.user)
                    messages.success(request, f"Imported {n} rule(s) from project memory."
                                     if n else "No new rules to import.")
                    return redirect("dashboard:project_rules", pk=pk)
                elif action == "add":
                    definition = {}
                    raw = (request.POST.get("definition") or "").strip()
                    if raw:
                        definition = json.loads(raw)
                    rules.create(
                        proj, name=request.POST.get("name", ""),
                        description=request.POST.get("description", ""),
                        category=request.POST.get("category", "other"),
                        definition=definition, priority=request.POST.get("priority") or 100,
                        user=request.user)
                    messages.success(request, "Rule added.")
                    return redirect("dashboard:project_rules", pk=pk)
                elif action == "status":
                    rule = get_object_or_404(
                        BusinessRule, pk=request.POST.get("rule", 0), project=proj)
                    rules.set_status(rule, request.POST.get("status", ""), user=request.user)
                    return redirect("dashboard:project_rules", pk=pk)
            except json.JSONDecodeError:
                messages.error(request, "The rule definition must be valid JSON.")
            except rules.RuleError as exc:
                messages.error(request, str(exc))

    return render(request, "dashboard/project_rules.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "summary": rules.summary(proj),
        "rules": list(proj.business_rules.all()),
        "categories": RuleCategory.choices, "statuses": RuleStatus.choices,
        "evaluation": evaluation, "facts_input": request.POST.get("facts", ""),
    })


@login_required
def project_compatibility(request, pk):
    """A project's browser & device compatibility report (spec §9): real static
    risks per target; live cross-browser/device runs are honestly gated."""
    from apps.testing.compatibility import compatibility_report
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    return render(request, "dashboard/project_compatibility.html", {
        "active": "projects", "project": proj,
        "report": compatibility_report(proj),
    })


@login_required
def project_security(request, pk):
    """A project's security scans (spec §8): real findings history + latest status.
    Members view; owners/admins run a scan. Production deploys are blocked on
    high-severity findings."""
    from apps.security import ledger
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:project_security", pk=pk)
        scan = ledger.run_scan(proj, trigger="manual", user=request.user)
        messages.success(request, f"Scan finished: {scan.get_status_display().lower()} — {scan.summary}")
        return redirect("dashboard:project_security", pk=pk)

    latest = ledger.latest_scan(proj)
    return render(request, "dashboard/project_security.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "ok": ledger.security_ok(proj),
        "latest": latest,
        "findings": latest.findings.all()[:100] if latest else [],
        "scans": proj.security_scans.all()[:25],
    })


@login_required
def project_tests(request, pk):
    """A project's test runs (spec §8): real history + latest status + the tests the
    latest change requires. Members view; owners/admins can run the suite."""
    from apps.testing import runner
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    can_manage = proj.organization_id in _manageable_ids(request.user)

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:project_tests", pk=pk)
        action = request.POST.get("action", "run")
        if action == "propose_fix":
            from apps.testing.debug import propose_fix
            from apps.testing.models import TestRun
            run = get_object_or_404(TestRun, pk=request.POST.get("run", 0), project=proj)
            try:
                change = propose_fix(run, user=request.user)
                messages.success(request, "A fix was proposed as a change — review and approve it.")
                return redirect("dashboard:change", pk=change.id)
            except ValueError as exc:
                messages.error(request, str(exc))
        else:
            run = runner.run_project_tests(proj, trigger="manual", user=request.user)
            messages.success(request, f"Test run finished: {run.get_status_display().lower()} — {run.summary}")
        return redirect("dashboard:project_tests", pk=pk)

    required = []
    change = proj.changes.exclude(plan={}).first()
    if change is not None:
        from apps.changes.impact import analyze_impact
        required = analyze_impact(change).get("required_tests", [])
    latest = runner.latest_run(proj)
    from apps.testing.debug import analyze_failure
    return render(request, "dashboard/project_tests.html", {
        "active": "projects", "project": proj, "can_manage": can_manage,
        "green": runner.tests_green(proj),
        "latest": latest,
        "diagnosis": analyze_failure(latest) if latest else None,
        "required_tests": required,
        "runs": proj.test_runs.all()[:25],
    })


@login_required
def project_intelligence(request, pk):
    """The project's structured intelligence (spec §14): the knowledge the platform
    keeps about this app — requirements, data, APIs, UI, mobile, capabilities,
    change history. Composed read-only from existing sources; customer-safe."""
    from apps.project_context.intelligence import build_intelligence
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    return render(request, "dashboard/project_intelligence.html", {
        "active": "projects", "project": proj,
        "intel": build_intelligence(proj),
    })


@login_required
def project_graph(request, pk):
    """The Application Graph (spec §4) + Dependency Intelligence (spec §5): the
    node+edge model of this app and, when a node is selected, what depends on it.
    Composed read-only from existing data; customer-safe."""
    from apps.project_context.graph import build_graph, dependency_report
    proj = get_object_or_404(
        Project.objects.filter(organization__in=organizations_for(request.user)), pk=pk)
    graph = build_graph(proj)
    selected = request.GET.get("node")
    report = dependency_report(proj, selected) if selected else None
    # Group nodes by type for a readable, dependency-first layout.
    _type_labels = {
        "application": "Application", "feature": "Features",
        "infrastructure": "Infrastructure & hosting", "integration": "Integrations",
        "security": "Security & trust", "screen": "Web screens",
        "mobile_screen": "Mobile screens", "api": "APIs", "entity": "Data entities",
        "requirement": "Requirements", "business_rule": "Business rules",
        "environment": "Environments", "mobile_platform": "Mobile platforms",
    }
    _order = list(_type_labels)
    grouped = []
    by_type: dict[str, list] = {}
    for n in graph["nodes"]:
        by_type.setdefault(n["type"], []).append(n)
    # direct dependency targets per node, for the "depends on" hint on each row
    deps_of: dict[str, list] = {}
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    _DEP_KINDS = {"requires", "uses", "runs_on", "part_of", "stored_in"}
    for e in graph["edges"]:
        if e["kind"] in _DEP_KINDS:
            deps_of.setdefault(e["source"], []).append(labels.get(e["target"], e["target"]))
    for t in _order:
        if t in by_type:
            rows = [{**n, "deps": deps_of.get(n["id"], [])} for n in by_type[t]]
            grouped.append({"type": t, "label": _type_labels[t], "nodes": rows})
    return render(request, "dashboard/project_graph.html", {
        "active": "projects", "project": proj, "graph": graph,
        "grouped": grouped, "selected": selected, "report": report,
    })


@login_required
def mobile_plan(request):
    """Mobile app planner (spec §5/§48): describe a mobile app, see the honest plan —
    capabilities (generated vs gated), device permissions, and target platforms —
    before building. Server-rendered over apps.mobile.planner."""
    from apps.mobile import planner

    brief = (request.GET.get("brief") or "").strip()
    selected = request.GET.getlist("platform") or ["ios", "android", "huawei"]
    plan = planner.plan(brief, platforms=selected) if brief else None
    return render(request, "dashboard/mobile_plan.html", {
        "active": "mobile_plan",
        "brief": brief,
        "selected_platforms": set(selected),
        "platform_choices": planner.platform_choices(),
        "plan": plan,
    })


@login_required
def releases(request):
    """Global Mobile Releases hub: the user's projects, each linking to its
    release center (reuses the per-project release workflow — no new backend)."""
    projects = (Project.objects
                .filter(organization__in=organizations_for(request.user))
                .select_related("organization").order_by("-updated_at"))
    return render(request, "dashboard/releases.html",
                  {"active": "releases", "projects": projects})


# A static index of navigable destinations for the command palette. Each entry
# resolves to a real route — search only surfaces things that actually exist.
_SEARCH_PAGES = [
    ("Home", "dashboard:home", None, "overview start"),
    ("Projects", "dashboard:projects", None, "apps builds"),
    ("Deployments", "dashboard:deployments", None, "deploy ship release"),
    ("Domains", "dashboard:org_domains", None, "dns custom domain"),
    ("Analytics", "dashboard:usage", None, "usage cost credits metrics"),
    ("Activity", "dashboard:tasks", None, "feed events history"),
    ("Environments", "dashboard:ops", "environments", "env deploy targets"),
    ("Integrations", "dashboard:org_integrations", None, "connectors github slack"),
    ("API keys", "dashboard:org_developer", None, "developer token programmatic"),
    ("Webhooks", "dashboard:org_developer", None, "events callbacks"),
    ("Monitoring", "dashboard:ops", "monitoring", "uptime logs incidents"),
    ("Security", "dashboard:security", None, "mfa sessions audit"),
    ("Plan a mobile app", "dashboard:mobile_plan", None, "mobile app ios android huawei capabilities plan"),
    ("Mobile Releases", "dashboard:releases", None, "app store play ios android"),
    ("AI Engineering", "dashboard:agents", None, "agents pipeline build"),
    ("Settings", "dashboard:settings_center", None, "preferences configuration"),
    ("Notifications", "dashboard:notifications_settings", None, "email alerts"),
    ("Privacy & data", "dashboard:org_data", None, "export deletion gdpr"),
    ("Audit log", "dashboard:org_audit", None, "events history security"),
    ("Billing & plan", "dashboard:settings", None, "credits upgrade payment"),
    ("Team", "dashboard:people", None, "members invites roles"),
    ("Help & Support", "support:mine", None, "tickets contact"),
    ("Account & security", "dashboard:account", None, "profile password mfa"),
]


@login_required
def search(request):
    """Grouped global search for the command palette (projects + pages).

    Returns JSON only; every result is a real, permission-scoped destination."""
    from django.http import JsonResponse

    q = (request.GET.get("q") or "").strip().lower()
    groups = []

    # Projects the user can see (tenant-scoped), matched by name.
    proj_qs = Project.objects.filter(organization__in=organizations_for(request.user))
    if q:
        proj_qs = proj_qs.filter(name__icontains=q)
    proj_items = [{
        "title": p.name,
        "url": reverse("dashboard:project", args=[p.id]),
        "meta": p.organization.name,
        "icon": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>',
    } for p in proj_qs.select_related("organization").order_by("-updated_at")[:6]]
    if proj_items:
        groups.append({"label": "Projects", "items": proj_items})

    # Navigable pages (static index); include all when the query is blank.
    page_icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16"><path d="M5 3h9l5 5v13H5z"/><path d="M14 3v5h5"/></svg>'
    page_items = []
    for title, route, arg, kw in _SEARCH_PAGES:
        if q and q not in title.lower() and q not in kw:
            continue
        try:
            url = reverse(route, args=[arg]) if arg else reverse(route)
        except Exception:
            continue
        page_items.append({"title": title, "url": url, "meta": "", "icon": page_icon})
    if page_items:
        groups.append({"label": "Pages", "items": page_items[:12]})

    return JsonResponse({"groups": groups})


@login_required
def org_developer(request):
    """Developer settings (spec §21/§22): programmatic API keys + outbound
    webhooks, per organization. Managing requires org rights. Secrets (a key's
    plaintext, a webhook's signing secret) are shown exactly once, on creation."""
    from apps.developer.events import EVENTS, is_known
    from apps.developer.models import ApiKey, Webhook
    from apps.organizations.permissions import has_perm

    manageable = [o for o in organizations_for(request.user).order_by("name")
                  if has_perm(request.user, o, "org.manage")]
    mids = {o.id for o in manageable}

    if request.method == "POST":
        org = get_object_or_404(Organization, pk=request.POST.get("organization", 0))
        if org.id not in mids:
            messages.error(request, "Owner or admin rights required.")
            return redirect("dashboard:org_developer")
        action = request.POST.get("action")
        from apps.settings.service import audit_change
        if action == "create_key":
            name = (request.POST.get("name") or "").strip() or "API key"
            key, plaintext = ApiKey.generate(org, name, created_by=request.user)
            audit_change("developer.api_key_created", actor=request.user,
                         organization=org, summary=f"API key '{name}' created")
            messages.success(request,
                             f"API key '{name}' created. Copy it now — it won't be shown "
                             f"again: {plaintext}")
        elif action == "revoke_key":
            key = get_object_or_404(ApiKey, pk=request.POST.get("key", 0), organization=org)
            if key.is_active:
                from django.utils import timezone as _tz
                key.revoked_at = _tz.now()
                key.save(update_fields=["revoked_at"])
                audit_change("developer.api_key_revoked", actor=request.user,
                             organization=org, summary=f"API key '{key.name}' revoked")
                messages.success(request, f"Revoked API key '{key.name}'.")
        elif action == "create_webhook":
            url = (request.POST.get("url") or "").strip()
            events = request.POST.getlist("events")
            if not url.startswith("https://"):
                messages.error(request, "A webhook needs an https:// URL.")
            elif any(not is_known(e) for e in events):
                messages.error(request, "Unknown event selected.")
            else:
                secret = Webhook.new_secret()
                Webhook.objects.create(organization=org, url=url, events=events,
                                       secret=secret, created_by=request.user)
                audit_change("developer.webhook_created", actor=request.user,
                             organization=org, summary=f"webhook → {url}")
                messages.success(request,
                                 f"Webhook created. Signing secret (shown once): {secret}")
        elif action == "delete_webhook":
            wh = get_object_or_404(Webhook, pk=request.POST.get("webhook", 0), organization=org)
            wh.delete()
            audit_change("developer.webhook_deleted", actor=request.user,
                         organization=org, summary="webhook deleted")
            messages.success(request, "Webhook deleted.")
        return redirect("dashboard:org_developer")

    cards = [{
        "org": o,
        "keys": o.api_keys.all(),
        "webhooks": o.webhooks.all(),
    } for o in manageable]
    return render(request, "dashboard/org_developer.html", {
        "active": "developer",
        "cards": cards,
        "events": [{"key": k, "description": v} for k, v in EVENTS.items()],
        "has_manageable": bool(manageable),
    })


@login_required
def org_integrations(request):
    """Integration marketplace (spec §12): every connectable service grouped by
    category with its real honest status. 'Connected' reflects a genuine credential
    or backend, never a fabricated connection; credentials are operator (environment)
    configuration, so this is read-only."""
    from apps.settings.marketplace import marketplace

    return render(request, "dashboard/org_integrations.html", {
        "active": "integrations",
        "market": marketplace(),
    })


@login_required
def settings_page(request):
    """Settings hub: plan & billing, usage summary, preferences, and projects."""
    from decimal import Decimal

    from django.db.models import Sum
    from django.utils import timezone as tz

    from apps.credits.models import CreditAccount, UsageRecord
    from apps.credits.services import daily_usd_cap, plans

    orgs = list(organizations_for(request.user))
    manageable = _manageable_ids(request.user)
    tab = request.GET.get("tab", "plan")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_preferences":
            from apps.accounts.models import User as _User
            u = request.user
            lang = (request.POST.get("language") or "").strip()[:16]
            u.language = lang if lang in dict(_LANGUAGES) else ""
            tzname = (request.POST.get("timezone") or "").strip()[:64]
            u.timezone = tzname if tzname in _TIMEZONES else ""
            scale = (request.POST.get("font_scale") or "").strip()
            u.font_scale = scale if scale in dict(_User.FONT_SCALES) else _User.FONT_MD
            u.reduce_motion = request.POST.get("reduce_motion") == "on"
            theme = (request.POST.get("theme") or "").strip()
            u.theme = theme if theme in dict(_User.THEME_CHOICES) else _User.THEME_DARK
            u.save(update_fields=["language", "timezone", "font_scale", "reduce_motion", "theme"])
            messages.success(request, "Preferences saved.")
            return redirect(f"{reverse('dashboard:settings')}?tab=preferences")

        if action == "request_upgrade":
            org = get_object_or_404(Organization, pk=request.POST.get("organization", 0),
                                    memberships__user=request.user)
            if org.id not in manageable:
                messages.error(request, "Owner or admin rights required.")
                return redirect(f"{reverse('dashboard:settings')}?tab=plan")
            target = request.POST.get("plan", "")
            label = _PLAN_LABEL.get(target, target)
            from apps.support.service import create_ticket
            t = create_ticket(
                organization=org, user=request.user, category="billing", priority="normal",
                subject=f"Upgrade request — {label} plan",
                body=f"{request.user.email} requested upgrading “{org.name}” to the {label} plan.",
            )
            messages.success(request, f"Upgrade request sent ({t.number}). Our team will follow "
                                      "up — you can track it under Help & Support.")
            return redirect(f"{reverse('dashboard:settings')}?tab=plan")

        # Project rename / delete (owner/admin).
        proj = get_object_or_404(Project, pk=request.POST.get("project", 0), organization__in=orgs)
        if proj.organization_id not in manageable:
            messages.error(request, "Owner or admin rights required.")
            return redirect(f"{reverse('dashboard:settings')}?tab=projects")
        if action == "rename":
            name = (request.POST.get("name") or "").strip()
            if name:
                proj.name = name
                proj.description = (request.POST.get("description") or "").strip()
                proj.save(update_fields=["name", "description", "updated_at"])
                messages.success(request, "Project updated.")
        elif action == "delete":
            proj.delete()
            messages.success(request, "Project deleted.")
        return redirect(f"{reverse('dashboard:settings')}?tab=projects")

    # --- plan & billing cards (one per org) ---
    month_start = tz.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    accounts = {a.organization_id: a for a in CreditAccount.objects.filter(organization__in=orgs)}
    plan_cards = []
    for o in orgs:
        acct = accounts.get(o.id)
        plan = acct.plan if acct else "free"
        allowance = Decimal(str(plans().get(plan, 0)))
        balance = acct.balance if acct else Decimal("0")
        remaining_pct = int(min(balance, allowance) / allowance * 100) if allowance else 0
        month = UsageRecord.objects.filter(organization=o, created_at__gte=month_start).aggregate(
            spend=Sum("cost_usd"), credits=Sum("credits_charged"), tokens=Sum("total_tokens"))
        upgrades = [p for p in _PLAN_ORDER[_PLAN_ORDER.index(plan) + 1:]] if plan in _PLAN_ORDER else []
        plan_cards.append({
            "org": o, "can_manage": o.id in manageable, "plan": plan,
            "plan_label": _PLAN_LABEL.get(plan, plan.title()), "price": _PLAN_PRICE.get(plan, ""),
            "features": _PLAN_FEATURES.get(plan, []), "allowance": allowance, "balance": balance,
            "remaining_pct": remaining_pct,
            "low": remaining_pct < 15,
            "daily_cap": daily_usd_cap(acct) if acct else None,
            "month_spend": month["spend"] or Decimal("0"),
            "month_credits": month["credits"] or Decimal("0"),
            "month_tokens": month["tokens"] or 0,
            "upgrades": [{"plan": p, "label": _PLAN_LABEL[p], "price": _PLAN_PRICE[p],
                          "features": _PLAN_FEATURES[p]} for p in upgrades],
        })

    rows = [
        {"project": p, "can_manage": p.organization_id in manageable}
        for p in Project.objects.filter(organization__in=orgs).select_related("organization")
    ]
    from apps.accounts.models import User as _User
    return render(request, "dashboard/settings.html", {
        "active": "settings", "tab": tab, "plan_cards": plan_cards, "rows": rows,
        "languages": _LANGUAGES, "timezones": _TIMEZONES,
        "currency": getattr(settings, "APP_DEFAULT_CURRENCY", "USD"),
        "pref_language": request.user.language, "pref_timezone": request.user.timezone,
        "font_scales": _User.FONT_SCALES, "pref_font_scale": request.user.font_scale,
        "pref_reduce_motion": request.user.reduce_motion,
        "themes": _User.THEME_CHOICES, "pref_theme": request.user.theme,
    })


_OPS = {
    "environments": "Environments", "cloud": "Cloud", "infrastructure": "Infrastructure",
    "monitoring": "Monitoring", "logs": "Logs", "incidents": "Incidents",
    "scaling": "Scaling", "performance": "Performance", "modernization": "Modernization",
}
# Areas that need a live connection before they can show real metrics.
_OPS_NEEDS_CONNECTION = {
    "monitoring": "a monitored, deployed environment",
    "incidents": "monitoring connected to a live deployment",
    "scaling": "live traffic and resource metrics from a deployment",
    "performance": "profiling data from a running app",
    "infrastructure": "a connected cloud/infrastructure provider",
}


@login_required
def operations(request, area):
    """Deploy/operate pages. Shows real adjacent state; never invents metrics."""
    if area not in _OPS:
        raise Http404
    orgs = organizations_for(request.user)
    ctx = {"active": area, "title": _OPS[area], "area": area,
           "needs": _OPS_NEEDS_CONNECTION.get(area)}
    if area == "environments":
        ctx["workspaces"] = Workspace.objects.filter(
            project__organization__in=orgs).select_related("project")
        ctx["deployments"] = Deployment.objects.filter(
            project__organization__in=orgs).select_related("project").order_by("-created_at")[:50]
    elif area == "cloud":
        from apps.deployments.providers import provider_status
        ctx["providers"] = provider_status()
    elif area == "logs":
        ctx["tasks"] = AgentTask.objects.filter(
            project__organization__in=orgs).select_related("project").order_by("-created_at")[:60]
    elif area == "modernization":
        ctx["imports"] = Project.objects.filter(
            organization__in=orgs, mode="import").select_related("organization")
    return render(request, "dashboard/operations.html", ctx)
