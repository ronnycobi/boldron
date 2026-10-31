from django.urls import path

from apps.localization.api import (
    BundleView,
    LocaleListCreateView,
    LocaleView,
    LocalizationView,
    StringListCreateView,
    TranslateView,
)

app_name = "localization"

urlpatterns = [
    path("projects/<int:project_pk>/i18n/", LocalizationView.as_view(), name="overview"),
    path("projects/<int:project_pk>/i18n/locales/",
         LocaleListCreateView.as_view(), name="locales"),
    path("projects/<int:project_pk>/i18n/strings/",
         StringListCreateView.as_view(), name="strings"),
    path("projects/<int:project_pk>/i18n/translate/",
         TranslateView.as_view(), name="translate"),
    path("projects/<int:project_pk>/i18n/bundle/", BundleView.as_view(), name="bundle"),
    path("i18n/locales/<int:pk>/", LocaleView.as_view(), name="locale"),
]
