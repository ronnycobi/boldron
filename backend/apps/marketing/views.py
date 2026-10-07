"""Public marketing site + self-serve sign-up.

All pages are public (no login). Content is real product description; live data
(the agent roster, supported stacks, pricing tiers) comes from the platform, so
nothing here is fabricated — no fake customers, logos, or metrics.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from apps.credits.services import ensure_account, plans
from apps.marketing.models import ContactMessage
from apps.organizations.models import Organization, Role
from apps.technology.registry import Category
from apps.technology.registry import registry as tech_registry


def _brand(text: str) -> str:
    """Fill the {brand} placeholder in marketing copy with the configured brand
    name, so a rebrand (settings.APP_NAME) flows through the Python-side copy
    just like it does through {{ app_name }} in templates."""
    return text.replace("{brand}", settings.APP_NAME)

# Public messaging shows OUTCOMES across the software lifecycle — never the
# internal machinery (no agent names, orchestration, routing, permissions, or
# model-selection logic). That topology is proprietary and stays behind auth.
# v1 scope: the platform builds NEW software — websites, web apps and mobile apps.
# (Bringing in and modernizing a customer's EXISTING software is paused for v1 —
# gated behind BOLDRON_IMPORT_ENABLED.)
_PILLARS = [
    ("Build", "Turn ideas into working websites and web apps in the technology stack you choose."),
    ("Ship", "Publish websites to a live URL, and design mobile apps and prepare their Android & iOS releases for the app stores."),
    ("Deploy", "Ship to dev and staging automatically; production stays behind an approval gate."),
    ("Operate", "Monitor, track cost per project, and keep improving — with a full audit trail."),
]

_CAPABILITIES = [
    ("Build", "Turn ideas into working software.",
     "Describe what you need and get websites and web apps — designed, generated and tested in the stack you choose."),
    ("Web & mobile", "Ship to the web and the app stores.",
     "Publish websites and web apps to a live URL, and design mobile apps and prepare their Android and iOS releases for Google Play and the App Store."),
    ("Test", "Validate software automatically.",
     "Generated projects come with tests that actually run."),
    ("Deploy", "Move applications into production environments.",
     "Promote to dev and staging; production changes stay behind an approval gate."),
    ("Operate", "Monitor and continuously improve running software.",
     "Track usage and cost per project, with a full audit trail."),
]


_BUILD_CATEGORIES = [
    ("Business applications", ["CRM", "ERP", "Operations software", "HR systems", "Finance systems"]),
    ("Customer products", ["SaaS", "Marketplaces", "Booking systems", "E-commerce", "Customer portals"]),
    ("Websites", ["Business websites", "Landing pages", "Marketing sites", "Directories"]),
    ("Mobile apps", ["Android apps", "iOS apps", "App-store releases"]),
    ("Internal tools", ["Dashboards", "Approval systems", "Workflow tools", "Reporting"]),
    ("Developer products", ["APIs", "Backend systems", "Data applications", "Developer tools"]),
]
_EXAMPLES = [
    ("CRM", "Build a CRM with contacts, companies, leads, deals and a sales dashboard."),
    ("SaaS", "Build a SaaS platform where teams sign up, manage members and subscribe."),
    ("Website", "Build a professional website for my business with services and contact pages."),
    ("E-commerce", "Build an online store with a product catalog, cart, checkout and orders."),
    ("Mobile app", "Build a mobile app for Android and iOS with sign-in and a home feed."),
    ("Internal Tool", "Build an internal tool to manage tasks, approvals and reports."),
]

# Three headline use-cases, each with its own prompt + CTA (the pattern the
# category leaders use). Prompts are prefilled into the hero box when clicked.
_USECASES = [
    ("Web apps & business software",
     "Turn an idea into a working application — designed, generated and tested in the stack you choose.",
     ["CRM", "ERP", "SaaS", "Customer portals", "Internal tools"],
     "Build a CRM for my construction company with customers, leads, quotations, projects and a sales dashboard."),
    ("Websites & online stores",
     "Business sites, landing pages and e-commerce — published to a live URL with a product catalog, cart and checkout.",
     ["Business sites", "Landing pages", "E-commerce", "Directories"],
     "Build a professional website for my business with services, pricing, a contact form and an online store."),
    ("Mobile — Android & iOS",
     "Design mobile apps and prepare their Google Play and App Store releases, from one description.",
     ["Android", "iOS", "App-store releases"],
     "Design a mobile app for Android and iOS with sign-in, a home feed and push notifications."),
]

# SEO-oriented FAQ. Every answer is strictly true of the platform today —
# including the honest limits (approval-gated production, AI key for real
# generation). No fabricated customers, metrics, or capabilities.
_FAQS = [
    ("What is {brand}?",
     "{brand} is an AI software-engineering platform. You describe the software you need in "
     "plain language and {brand} designs it, generates it and tests it in a real technology "
     "stack — then helps you deploy and operate it. You get real source code you can export "
     "and keep, not a closed black box."),
    ("Do I need to know how to code?",
     "No. You describe what you want in plain language to get a working first version. Because "
     "{brand} produces real, exportable source code, developers can also take it further — so "
     "it works for non-technical founders and engineering teams alike."),
    ("What can I build?",
     "Websites and online stores, web apps and business software (CRM, ERP, e-commerce, customer "
     "portals), internal tools, dashboards and APIs — plus designing mobile apps and preparing "
     "their Android and iOS releases for the app stores."),
    ("Which technology stack does it use?",
     "You choose. {brand} builds in real, production frameworks rather than a proprietary runtime, "
     "so your project is standard software you can host and maintain anywhere."),
    ("Can I deploy to production?",
     "{brand} ships to development and staging automatically. Production changes stay behind an "
     "explicit approval gate, with a full audit trail of who changed what — safe by default."),
    ("Is my code locked in?",
     "No. You can export your full source code at any time and run it yourself. No lock-in is a "
     "core principle of the platform."),
    ("Does it need an AI API key?",
     "{brand} runs in an offline demo mode with no key. Connect an API key (Anthropic, OpenAI or "
     "Gemini) to enable real code generation — the platform routes each task to a suitable model."),
    ("How much does it cost?",
     "There's a free tier to start, with paid plans that scale your AI credits, projects and "
     "deployment capacity as you grow. See the pricing page for current tiers."),
]


def _base_context():
    return {
        "pillars": _PILLARS,
        "capabilities": _CAPABILITIES,
        "languages": tech_registry.by_category(Category.LANGUAGE),
        "frameworks": tech_registry.by_category(Category.FRAMEWORK),
    }


def home(request):
    from apps.capabilities.registry import all_capabilities, by_group
    caps = all_capabilities()
    ctx = _base_context()
    ctx.update({
        "build_categories": _BUILD_CATEGORIES,
        "examples": _EXAMPLES,
        "usecases": _USECASES,
        "faqs": [(_brand(q), _brand(a)) for q, a in _FAQS],
        "capability_groups": by_group(),
        # Live, honest counts for the trust strip — sourced from the registries,
        # never hard-coded marketing numbers.
        "stat_capabilities": sum(1 for c in caps if c.is_available),
        "stat_languages": len(ctx["languages"]),
        "stat_frameworks": len(ctx["frameworks"]),
    })
    return render(request, "marketing/home.html", ctx)


def platform(request):
    return render(request, "marketing/platform.html", _base_context())


def how_it_works(request):
    # Outcome steps only — no agent names or internal routing.
    steps = [
        ("Describe", _brand("Tell {brand} what you want to build, in plain language.")),
        ("Plan", "Your intent becomes clear requirements and a technical plan — and you choose the technology stack."),
        ("Build", "Your application is generated in the chosen stack."),
        ("Validate", "Tests run automatically to check it works."),
        ("Deploy", "Ship to development and staging; production changes need your approval."),
        ("Operate", "Monitor, track cost, and keep improving."),
    ]
    return render(request, "marketing/how_it_works.html", {**_base_context(), "steps": steps})


def capabilities(request):
    return render(request, "marketing/capabilities.html", _base_context())


def pricing(request):
    tiers = [
        {"name": "Free", "price": "$0", "credits": plans().get("free", 0),
         "blurb": _brand("Explore {brand}."),
         "features": ["Build projects", "Limited AI usage", "Preview", "Export your code anytime"]},
        {"name": "Builder", "price": "$29", "credits": plans().get("pro", 0),
         "blurb": "For serious builders.",
         "features": ["More AI credits", "More projects", "Deployment", "Git integration", "Custom domain"],
         "highlight": True},
        {"name": "Pro", "price": "$99", "credits": plans().get("business", 0),
         "blurb": "For businesses.",
         "features": ["Higher AI allowance", "Mobile apps (Android & iOS)", "Team collaboration",
                      "Monitoring", "More deployment capacity"]},
        {"name": "Business", "price": "Custom", "credits": None,
         "blurb": "For growing teams.",
         "features": ["Team management", "Security & audit logs", "Private deployments",
                      "Advanced controls", "Priority support"]},
    ]
    return render(request, "marketing/pricing.html", {**_base_context(), "tiers": tiers})


def about(request):
    return render(request, "marketing/about.html", _base_context())


def contact(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        body = (request.POST.get("message") or "").strip()
        if name and email and body:
            ContactMessage.objects.create(
                name=name, email=email,
                company=(request.POST.get("company") or "").strip(), message=body,
            )
            messages.success(request, "Thanks — we’ve received your message and will be in touch.")
            return redirect("marketing:contact")
        messages.error(request, "Please provide your name, email, and a message.")
    return render(request, "marketing/contact.html", _base_context())


def signup(request):
    from apps.accounts.forms import RegistrationForm

    idea = (request.GET.get("idea") or request.POST.get("idea") or "").strip()
    if request.user.is_authenticated:
        if idea:
            request.session["build_idea"] = idea[:2000]
        return redirect("dashboard:home")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        default_name = f"{user.full_name or user.email.split('@')[0]}'s workspace"
        org = Organization.objects.create(
            name=form.cleaned_data.get("org_name") or default_name, created_by=user,
        )
        org.add_member(user, role=Role.OWNER)
        ensure_account(org, plan="free")  # start with free-tier credits
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        if idea:
            request.session["build_idea"] = idea[:2000]  # carried into the builder
        return redirect("dashboard:home")

    ctx = _base_context()
    ctx["idea"] = idea
    ctx["form"] = form
    return render(request, "marketing/signup.html", ctx)
