from django.urls import path

from apps.developer.api import (
    ApiKeyListCreateView,
    ApiKeyRevokeView,
    WebhookDetailView,
    WebhookListCreateView,
)

app_name = "developer"

urlpatterns = [
    path("organizations/<int:pk>/api-keys/",
         ApiKeyListCreateView.as_view(), name="api-keys"),
    path("organizations/<int:pk>/api-keys/<int:key_id>/revoke/",
         ApiKeyRevokeView.as_view(), name="api-key-revoke"),
    path("organizations/<int:pk>/webhooks/",
         WebhookListCreateView.as_view(), name="webhooks"),
    path("organizations/<int:pk>/webhooks/<int:webhook_id>/",
         WebhookDetailView.as_view(), name="webhook-detail"),
]
