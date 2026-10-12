from django.urls import path

from apps.release.api import (
    MobileAppDetailView,
    MobileAppListCreateView,
    ProviderListView,
    StoreConnectionListView,
)

app_name = "release"

urlpatterns = [
    path("release/providers/", ProviderListView.as_view(), name="providers"),
    path("projects/<int:project_pk>/mobile-apps/", MobileAppListCreateView.as_view(), name="apps"),
    path("mobile-apps/<int:pk>/", MobileAppDetailView.as_view(), name="app"),
    path("orgs/<int:org_pk>/store-connections/", StoreConnectionListView.as_view(), name="store-connections"),
]
