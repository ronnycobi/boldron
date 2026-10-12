from django.urls import path

from apps.core.search_api import GlobalSearchView
from apps.core.views import HealthView

app_name = "core"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("search/", GlobalSearchView.as_view(), name="search"),
]
