"""Projects — a unit of software the platform builds, imports, or operates.

A Project belongs to exactly one Organization (the tenant). Everything the agents
eventually produce for it — requirements, architecture, code, builds, runs — is
scoped through the Project, and through it to the Organization. Isolation is
enforced at query time by filtering on organization membership; see
apps.projects.api.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.slugs import unique_slug


class Mode(models.TextChoices):
    """Which product mode this project is in (see docs/PRODUCT.md §4)."""

    BUILD = "build", "Build new software"
    IMPORT = "import", "Import existing software"


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class Project(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.BUILD)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    # Chosen technology per role, e.g. {"backend": "django", "frontend": "nextjs",
    # "database": "postgresql", "mobile": "flutter"}. the platform is stack-agnostic;
    # agents read this to generate in the customer's chosen stack. Empty => the
    # agent's default (python-stdlib for backend).
    technology = models.JSONField(default=dict, blank=True)
    # The capabilities this app composes (ids from apps.capabilities.registry),
    # inferred from the brief at build time. The AI reads this when modifying the
    # project so it reuses existing capabilities instead of rebuilding them.
    capabilities = models.JSONField(default=list, blank=True)
    # The mobile build plan (apps.mobile.planner): {capabilities, platforms,
    # permissions} inferred from the brief. The Mobile Agent reads this so the
    # screens it designs are driven by the planned mobile capabilities.
    mobile_plan = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects_created",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="unique_project_slug_per_org",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.organization.slug})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(
                Project,
                self.name,
                scope={"organization": self.organization},
                instance=self,
                fallback="project",
            )
        super().save(*args, **kwargs)

    def ensure_default_workspace(self):
        """Create the project's default workspace if it has none.

        Kept here (rather than a signal) so the caller controls when it runs and
        can attribute it; the API create flow invokes it right after creation.
        """
        from apps.workspaces.models import Workspace

        if self.workspaces.exists():
            return self.workspaces.filter(is_default=True).first() or self.workspaces.first()
        return Workspace.objects.create(
            project=self, name="Main", is_default=True
        )


class ProjectAiPreference(models.Model):
    """A project's AI routing preference (spec §18). Same soft semantics as the
    org preference, but scoped to one project and taking precedence over it — the
    Model Router only honours a choice that is actually available, and falls back
    otherwise, so a preference never breaks a build. No API keys are stored here."""

    project = models.OneToOneField(
        "projects.Project", on_delete=models.CASCADE, related_name="ai_preference"
    )
    preferred_provider = models.CharField(max_length=32, blank=True)
    preferred_model = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI prefs for project {self.project_id}"


class EnvVar(models.Model):
    """A project's environment variable (spec §20).

    These are the *customer's app* configuration — values the platform must
    store so it can inject them into the project's preview/run process (see
    apps.preview_runner). That is different from platform secrets, which remain
    environment-only and are never stored in the DB. A var flagged `is_secret` is
    masked in every read (its value is write-only); non-secret values are shown
    so they can be edited. Values are not encrypted at rest in this phase — a
    limitation stated honestly rather than faked with reversible 'encryption'.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="env_vars"
    )
    key = models.CharField(max_length=128)
    value = models.TextField(blank=True)
    is_secret = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "key"], name="unique_env_key_per_project"
            )
        ]

    def __str__(self):
        return f"{self.key} ({self.project_id})"
