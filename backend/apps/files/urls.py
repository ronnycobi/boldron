from django.urls import path

from apps.files.api import (
    FileDetailView,
    FileListCreateView,
    FileServeView,
    FileThumbView,
    PublicFileServeView,
)

app_name = "files_api"

urlpatterns = [
    path("files/", FileListCreateView.as_view(), name="list"),
    path("files/<int:pk>/", FileDetailView.as_view(), name="detail"),
    path("files/<int:pk>/raw/", FileServeView.as_view(), name="serve"),
    path("files/<int:pk>/thumb/", FileThumbView.as_view(), name="thumb"),
    path("files/public/<str:key>/", PublicFileServeView.as_view(), name="serve-public"),
]
