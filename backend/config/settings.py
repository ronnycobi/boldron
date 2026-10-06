"""
Django settings for the platform.

Configuration is driven entirely by environment variables so the same code runs
locally, in CI, and in production without edits. See `.env.example` for the full
list. Secrets NEVER live in this file or in version control.
"""
import os
import sys
from pathlib import Path

# backend/ directory (this file is backend/config/settings.py).
BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent  # where .env / .env.example live

# The test suite must be hermetic: it should not pick up a developer's local
# .env or exported API keys, or its behaviour (default provider, which models
# are "available") would vary machine to machine.
RUNNING_TESTS = "test" in sys.argv


def load_env_file(path, environ=None) -> int:
    """Load KEY=VALUE pairs from a .env file into the environment.

    Real environment variables always win — a key already set is left untouched —
    so this only fills in what the shell/host hasn't provided. Deliberately tiny
    and dependency-free: blank lines and `#` comments are skipped, a leading
    `export ` is tolerated, and surrounding single/double quotes are stripped.
    Returns the number of keys it set. Never raises on a malformed line.
    """
    environ = os.environ if environ is None else environ
    path = Path(path)
    if not path.is_file():
        return 0
    set_count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key not in environ:  # real env wins
            environ[key] = value
            set_count += 1
    return set_count


# Load .env from the repo root before any setting is read, so a local .env works
# out of the box (the documented copy-.env.example-to-.env flow). A custom path
# can be given via DEVFORGE_ENV_FILE. Skipped under tests to keep them hermetic.
if not RUNNING_TESTS:
    load_env_file(os.environ.get("DEVFORGE_ENV_FILE", REPO_ROOT / ".env"))


def env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core -------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# --- Application identity (white-label branding) ----------------------------
# The product is brand-agnostic: NO product name, company, domain, logo, support
# address, locale or currency is hard-coded in the code. Everything customer-
# facing is configured here from the environment, so the same codebase ships as
# any brand by changing env vars only. This is the single source of truth —
# templates read it via apps.core.context_processors.branding ({{ app_name }}…),
# Python reads settings.APP_*. Internal platform concepts (agents, projects,
# builds, deployments, capabilities, providers, commerce, the "devforge" app
# label and DEVFORGE_ operational vars) are implementation identifiers and stay.
APP_NAME = env("APP_NAME", "Application")
APP_COMPANY_NAME = env("APP_COMPANY_NAME", "")  # falls back to APP_NAME in the branding layer
APP_TAGLINE = env("APP_TAGLINE", "")
APP_URL = env("APP_URL", "")
APP_LOGO_URL = env("APP_LOGO_URL", "")          # empty -> bundled fallback mark
APP_FAVICON_URL = env("APP_FAVICON_URL", "")    # empty -> bundled fallback favicon
APP_SUPPORT_EMAIL = env("APP_SUPPORT_EMAIL", "")
APP_SUPPORT_URL = env("APP_SUPPORT_URL", "")
APP_DEFAULT_LOCALE = env("APP_DEFAULT_LOCALE", "en-us")
# Back-compat: honour the older DJANGO_TIME_ZONE if APP_DEFAULT_TIMEZONE is unset.
APP_DEFAULT_TIMEZONE = env("APP_DEFAULT_TIMEZONE", env("DJANGO_TIME_ZONE", "UTC"))
APP_DEFAULT_CURRENCY = env("APP_DEFAULT_CURRENCY", "USD")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    # the platform apps (modular monolith; add phased apps here — see docs/PRODUCT.md)
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.projects",
    "apps.workspaces",
    "apps.technology",
    "apps.capabilities",
    "apps.agents",
    "apps.tools",
    "apps.orchestrator",
    "apps.ai_providers",
    "apps.model_router",
    "apps.project_context",
    "apps.requirements",
    "apps.architecture",
    "apps.backend",
    "apps.frontend",
    "apps.database",
    "apps.testing",
    "apps.code_review",
    "apps.security",
    "apps.mobile",
    "apps.devops",
    "apps.build_sandbox",
    "apps.preview_runner",
    "apps.repositories",
    "apps.codegen",
    "apps.exporter",
    "apps.credits",
    "apps.costs",
    "apps.deployments",
    "apps.changes",
    "apps.backups",
    "apps.ingest",
    "apps.dashboard",
    "apps.console",
    "apps.audit",
    "apps.release",
    "apps.publishing",
    "apps.support",
    "apps.skills",
    "apps.hooks",
    "apps.marketing",
    "apps.notifications",
]

# --- Auth redirects (server-rendered dashboard UI) --------------------------
LOGIN_URL = "dashboard:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "dashboard:login"

# Email is the identity across the platform; set before any migrations reference it.
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    # Serve verified custom domains by Host header (real virtual hosting). Outermost
    # so a customer domain is served from our controlled allowlist before host
    # validation rejects it as an unknown ALLOWED_HOST.
    "apps.publishing.middleware.CustomDomainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.branding",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# Production target is PostgreSQL (set DB_ENGINE=postgres + DB_* vars). When
# unset the project falls back to SQLite so the app stays runnable and testable
# without a database server — see docs/PRODUCT.md, Phase 1.

if env("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "devforge"),
            "USER": env("DB_USER", "devforge"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Auth / passwords -------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n / tz --------------------------------------------------------------
# the platform builds software for customers worldwide — do not assume one locale.

LANGUAGE_CODE = APP_DEFAULT_LOCALE
TIME_ZONE = APP_DEFAULT_TIMEZONE
USE_I18N = True
USE_TZ = True

# --- Static -----------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Project static assets (logo, etc.). Served by runserver in DEBUG; collectstatic
# gathers them for production.
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Speed up the test suite: real password hashing dominates test setup time and
# adds no coverage. Only applied when running tests.
if RUNNING_TESTS:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    # Hermetic AI config: drop any provider keys that leaked in from the shell so
    # the stub stays the only available provider and tests are deterministic.
    # (Individual tests inject their own keys via mock.patch.dict when they need
    # to exercise a real provider.)
    for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        os.environ.pop(_k, None)
    os.environ["AI_DEFAULT_PROVIDER"] = "stub"

# --- DRF --------------------------------------------------------------------

# --- AI providers (Phase 6) -------------------------------------------------
# Which provider the gateway uses when none is named. Defaults to the offline
# "stub" so a fresh checkout runs with no API keys. Set to "anthropic" (and
# export ANTHROPIC_API_KEY) for real completions. Provider API keys are read
# from the environment by each provider — never stored here.
AI_DEFAULT_PROVIDER = env("AI_DEFAULT_PROVIDER", "stub")

# --- Generated-project storage ----------------------------------------------
# Where per-project git working trees live (apps.repositories). Defaults to a
# gitignored dir beside the backend; set DEVFORGE_WORKSPACES_ROOT in production.
DEVFORGE_WORKSPACES_ROOT = env(
    "DEVFORGE_WORKSPACES_ROOT", str(BASE_DIR / "workspaces")
)

# --- Credits & plans (Phase 19) ---------------------------------------------
# Credits are a platform abstraction over cost. These are config, never
# hard-coded into billing logic — tune freely.
DEVFORGE_CREDITS_PER_USD = env("DEVFORGE_CREDITS_PER_USD", "100")
DEVFORGE_PLANS = {"free": 1000, "pro": 5000, "business": 25000}
# Platform-wide hard cap on AI spend per org per day (USD). Blank/unset = no
# global cap (each org may still set its own on its CreditAccount). This is the
# safety rail that lets you hand out access without risking a runaway bill.
DEVFORGE_ORG_DAILY_USD_CAP = env("DEVFORGE_ORG_DAILY_USD_CAP", "") or None

# Model-selection posture. True (default) = pick the most capable model that fits
# each task (best product); False = cheapest-sufficient. A task can still opt the
# other way per request, or set a hard max_cost_per_mtok ceiling.
DEVFORGE_PREFER_QUALITY = env("DEVFORGE_PREFER_QUALITY", "true").lower() in ("1", "true", "yes", "on")

# Website publishing domains. BASE_DOMAIN is the platform's subdomain zone; TARGET is
# the hostname a customer points their custom domain at (CNAME target). These are
# customer-facing (shown in DNS instructions, used in published URLs), so they are
# brand-neutral by default and set per deployment via the environment. Prefer the
# APP_* names; the DEVFORGE_* names remain as back-compat aliases.
DEVFORGE_BASE_DOMAIN = env("APP_BASE_DOMAIN", env("DEVFORGE_BASE_DOMAIN", "example.com"))
DEVFORGE_DOMAIN_TARGET = env("APP_DOMAIN_TARGET", env("DEVFORGE_DOMAIN_TARGET", "hosting.example.com"))

# Reverse-DNS prefix for generated mobile app IDs (Android applicationId / iOS
# bundle id). Brand-neutral default; set per deployment.
APP_BUNDLE_ID_PREFIX = env("APP_BUNDLE_ID_PREFIX", "com.example")

# How long an unpaid order may hold its stock/discount reservations before the
# expire_orders job auto-cancels it (minutes). Default 24h.
DEVFORGE_ORDER_RESERVATION_TTL_MINUTES = int(env("DEVFORGE_ORDER_RESERVATION_TTL_MINUTES", "1440"))

# v1 ships "build new software" only. Bringing in and modernizing a customer's
# EXISTING software (the import/analyze path) is paused until after v1; the code
# stays, gated here. Set true to re-enable.
DEVFORGE_IMPORT_ENABLED = env_bool("DEVFORGE_IMPORT_ENABLED", False)

# Email. Real delivery when EMAIL_BACKEND points at SMTP and the host is set;
# dev defaults to the console backend (prints emails) so nothing is faked and no
# server is required. Tests capture via the locmem backend automatically.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
# Sender identity is brand-driven: "<App Name> <support@…>". Both halves are
# configurable; DEFAULT_FROM_EMAIL can still be set explicitly to override.
_default_sender_addr = APP_SUPPORT_EMAIL or "no-reply@localhost"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", f"{APP_NAME} <{_default_sender_addr}>")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# --- Security (tightened automatically when DEBUG is off) -------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
