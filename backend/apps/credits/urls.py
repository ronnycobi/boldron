from django.urls import path

from apps.credits.api import (
    BillingView,
    CreditBalanceView,
    InvoiceListView,
    UpgradeRequestView,
    UsageListView,
    UsageOverviewView,
    UsageSummaryView,
)

app_name = "credits"

urlpatterns = [
    path("orgs/<int:org_pk>/credits/", CreditBalanceView.as_view(), name="balance"),
    path("orgs/<int:org_pk>/usage/", UsageListView.as_view(), name="usage"),
    path("orgs/<int:org_pk>/usage/summary/", UsageSummaryView.as_view(), name="usage-summary"),
    path("orgs/<int:org_pk>/usage/overview/", UsageOverviewView.as_view(), name="usage-overview"),
    path("orgs/<int:org_pk>/billing/", BillingView.as_view(), name="billing"),
    path("orgs/<int:org_pk>/invoices/", InvoiceListView.as_view(), name="invoices"),
    path("orgs/<int:org_pk>/upgrade-request/", UpgradeRequestView.as_view(), name="upgrade-request"),
]
