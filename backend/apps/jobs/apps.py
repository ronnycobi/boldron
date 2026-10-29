from django.apps import AppConfig


class JobsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.jobs"
    verbose_name = "Background jobs"

    def ready(self):
        # Register the real job handlers.
        from apps.jobs import handlers  # noqa: F401
