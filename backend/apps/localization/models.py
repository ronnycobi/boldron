"""Localization / i18n (spec §17-18).

An app can be offered in more than one language. A project declares the locales
it supports (one default), keeps a catalogue of translatable strings (each with
its source text in the default locale), and a translation per locale per string.

Honesty: a string with no translation for a locale is reported as missing and
falls back to the source text — it is never shown as "translated" when it isn't,
and coverage percentages reflect real, human-entered translations only. Nothing
is machine-translated behind the scenes.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone

# Right-to-left scripts, so the app can lay out correctly for these locales.
RTL_CODES = {"ar", "he", "fa", "ur"}


class ProjectLocale(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="locales")
    code = models.CharField(max_length=15)          # e.g. "en", "fr", "pt-br"
    name = models.CharField(max_length=80, blank=True)
    is_default = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-is_default", "code"]
        constraints = [
            models.UniqueConstraint(fields=["project", "code"],
                                    name="unique_locale_per_project")
        ]

    def __str__(self):
        return f"{self.code}{' (default)' if self.is_default else ''}"

    @property
    def rtl(self) -> bool:
        return self.code.split("-")[0].lower() in RTL_CODES


class TranslationString(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE,
        related_name="translation_strings")
    key = models.CharField(max_length=200)          # stable identifier, e.g. "cart.checkout"
    source_text = models.TextField()                # the text in the default locale
    description = models.CharField(max_length=300, blank=True)  # context for translators
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "key"],
                                    name="unique_string_per_project")
        ]

    def __str__(self):
        return self.key


class Translation(models.Model):
    string = models.ForeignKey(
        TranslationString, on_delete=models.CASCADE, related_name="translations")
    locale = models.CharField(max_length=15)
    value = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["string", "locale"],
                                    name="unique_translation_per_locale")
        ]

    def __str__(self):
        return f"{self.string.key}[{self.locale}]"
