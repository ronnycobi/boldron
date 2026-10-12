from django.urls import path

from apps.support.api import (
    SupportMetaView,
    TicketDetailView,
    TicketListCreateView,
    TicketReplyView,
)

app_name = "support_api"

urlpatterns = [
    path("support/tickets/", TicketListCreateView.as_view(), name="tickets"),
    path("support/tickets/<int:pk>/", TicketDetailView.as_view(), name="ticket"),
    path("support/tickets/<int:pk>/reply/", TicketReplyView.as_view(), name="ticket-reply"),
    path("support/meta/", SupportMetaView.as_view(), name="meta"),
]
