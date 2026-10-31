"""Localization lifecycle + honest coverage/bundles (spec §17-18)."""
from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.audit.service import record as audit
from apps.localization.models import ProjectLocale, Translation, TranslationString

# A small display-name table so a new locale reads nicely; unknown codes just use
# the code itself (never a fabricated language name).
_LOCALE_NAMES = {
    "en": "English", "fr": "French", "es": "Spanish", "pt": "Portuguese",
    "pt-br": "Portuguese (Brazil)", "de": "German", "ar": "Arabic",
    "zh": "Chinese", "ja": "Japanese", "af": "Afrikaans", "sw": "Swahili",
    "zu": "Zulu", "xh": "Xhosa", "he": "Hebrew", "hi": "Hindi",
}


class LocalizationError(Exception):
    pass


def _norm(code: str) -> str:
    return (code or "").strip().lower().replace("_", "-")


def add_locale(project, *, code, name="", make_default=False, user=None) -> ProjectLocale:
    code = _norm(code)
    if not code:
        raise LocalizationError("A locale needs a code (e.g. 'fr').")
    first = not project.locales.exists()
    try:
        with transaction.atomic():
            locale = ProjectLocale.objects.create(
                project=project, code=code[:15],
                name=(name or _LOCALE_NAMES.get(code, code)).strip()[:80],
                is_default=(make_default or first))
            if locale.is_default:
                project.locales.exclude(pk=locale.pk).update(is_default=False)
    except IntegrityError:
        raise LocalizationError(f"Locale '{code}' already exists.")
    audit("i18n.locale.add", actor=user, organization=project.organization,
          target=f"project:{project.id}", summary=code)
    return locale


def set_default_locale(locale: ProjectLocale, *, user=None) -> ProjectLocale:
    with transaction.atomic():
        locale.project.locales.update(is_default=False)
        locale.is_default = True
        locale.enabled = True
        locale.save(update_fields=["is_default", "enabled"])
    return locale


def remove_locale(locale: ProjectLocale, *, user=None):
    if locale.is_default:
        raise LocalizationError("Can't remove the default locale.")
    locale.translations_cleanup = locale.code
    # drop translations in that locale, then the locale row
    Translation.objects.filter(string__project=locale.project, locale=locale.code).delete()
    locale.delete()


def default_code(project) -> str | None:
    d = project.locales.filter(is_default=True).first()
    return d.code if d else None


def add_string(project, *, key, source_text, description="", user=None) -> TranslationString:
    key = (key or "").strip()
    if not key:
        raise LocalizationError("A string needs a key.")
    if not (source_text or "").strip():
        raise LocalizationError("A string needs source text.")
    try:
        s = TranslationString.objects.create(
            project=project, key=key[:200], source_text=source_text.strip(),
            description=(description or "").strip()[:300])
    except IntegrityError:
        raise LocalizationError(f"A string with key '{key}' already exists.")
    return s


def set_translation(string: TranslationString, locale_code: str, value: str, *, user=None):
    code = _norm(locale_code)
    if not string.project.locales.filter(code=code).exists():
        raise LocalizationError(f"'{code}' is not a locale of this project.")
    if code == default_code(string.project):
        raise LocalizationError("The default locale is the source text — edit the string instead.")
    value = (value or "").strip()
    if not value:
        # Clearing a translation is honest: it goes back to missing/fallback.
        Translation.objects.filter(string=string, locale=code).delete()
        return None
    tr, _ = Translation.objects.update_or_create(
        string=string, locale=code, defaults={"value": value})
    return tr


def coverage(project) -> list[dict]:
    """Per non-default locale: how many strings are really translated."""
    total = project.translation_strings.count()
    default = default_code(project)
    rows = []
    for loc in project.locales.all():
        if loc.code == default:
            continue
        done = Translation.objects.filter(
            string__project=project, locale=loc.code).exclude(value="").count()
        rows.append({
            "code": loc.code, "name": loc.name, "rtl": loc.rtl,
            "enabled": loc.enabled, "translated": done, "total": total,
            "missing": total - done,
            "percent": round(done / total * 100) if total else 0,
        })
    return rows


def bundle(project, locale_code: str) -> dict:
    """The app's strings for one locale. Missing translations fall back to the
    source text and are flagged — the bundle never pretends a string is translated."""
    code = _norm(locale_code)
    if not project.locales.filter(code=code).exists():
        raise LocalizationError(f"'{code}' is not a locale of this project.")
    default = default_code(project)
    is_default = code == default
    by_string = {}
    if not is_default:
        by_string = {t.string_id: t.value for t in Translation.objects.filter(
            string__project=project, locale=code).exclude(value="")}
    strings, missing = {}, []
    for s in project.translation_strings.all():
        if is_default or s.id in by_string:
            strings[s.key] = {"value": by_string.get(s.id, s.source_text), "fallback": False}
        else:
            strings[s.key] = {"value": s.source_text, "fallback": True}
            missing.append(s.key)
    loc = project.locales.get(code=code)
    return {
        "locale": code, "rtl": loc.rtl, "is_default": is_default,
        "strings": strings, "missing": missing, "complete": not missing,
    }


def summary(project) -> dict:
    locales = list(project.locales.all())
    return {
        "locales": len(locales),
        "default": default_code(project),
        "strings": project.translation_strings.count(),
        "has_rtl": any(l.rtl for l in locales),
    }
