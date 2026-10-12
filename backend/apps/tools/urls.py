from django.urls import path

from apps.tools.api import IntegrationListView

app_name = "tools"

urlpatterns = [
    path("integrations/", IntegrationListView.as_view(), name="integrations"),
]
