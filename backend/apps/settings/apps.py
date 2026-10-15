from django.apps import AppConfig


class SettingsCenterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.settings"
    label = "settings_center"
    verbose_name = "Settings control center"
