from django.urls import path

from apps.release.api import (
    MobileAppDetailView,
    MobileAppListCreateView,
    ProviderListView,
    StoreConnectionListView,
    StoreListingApproveView,
    StoreListingView,
    StoreScreenshotsApproveView,
    StoreScreenshotsView,
)

app_name = "release"

urlpatterns = [
    path("release/providers/", ProviderListView.as_view(), name="providers"),
    path("projects/<int:project_pk>/mobile-apps/", MobileAppListCreateView.as_view(), name="apps"),
    path("mobile-apps/<int:pk>/", MobileAppDetailView.as_view(), name="app"),
    # Store listing (metadata) + screenshots per app + provider.
    path("mobile-apps/<int:pk>/stores/<str:provider>/listing/",
         StoreListingView.as_view(), name="listing"),
    path("mobile-apps/<int:pk>/stores/<str:provider>/listing/approve/",
         StoreListingApproveView.as_view(), name="listing-approve"),
    path("mobile-apps/<int:pk>/stores/<str:provider>/screenshots/",
         StoreScreenshotsView.as_view(), name="screenshots"),
    path("mobile-apps/<int:pk>/stores/<str:provider>/screenshots/approve/",
         StoreScreenshotsApproveView.as_view(), name="screenshots-approve"),
    path("orgs/<int:org_pk>/store-connections/", StoreConnectionListView.as_view(), name="store-connections"),
]
