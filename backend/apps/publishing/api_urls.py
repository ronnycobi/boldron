from django.urls import path

from apps.publishing import api
from apps.publishing import commerce_api as m
from apps.publishing import website_api as w

app_name = "commerce_api"

urlpatterns = [
    # Public storefront (shopper) — keyed by store subdomain.
    path("stores/<slug:subdomain>/products", api.ProductListView.as_view(), name="products"),
    path("stores/<slug:subdomain>/products/<slug:slug>", api.ProductDetailView.as_view(), name="product"),
    path("stores/<slug:subdomain>/checkout", api.CheckoutView.as_view(), name="checkout"),
    path("stores/<slug:subdomain>/orders/<str:reference>", api.OrderStatusView.as_view(), name="order"),
    path("stores/<slug:subdomain>/orders/<str:reference>/invoice", api.OrderInvoiceView.as_view(), name="order-invoice"),

    # Merchant console (authenticated) — keyed by project, over the same engine.
    path("projects/<int:project_pk>/commerce/products/", m.ProductListCreateView.as_view(), name="admin-products"),
    path("projects/<int:project_pk>/commerce/products/<int:pk>/", m.ProductDetailView.as_view(), name="admin-product"),
    path("projects/<int:project_pk>/commerce/products/<int:pk>/variants/", m.VariantListCreateView.as_view(), name="admin-variants"),
    path("projects/<int:project_pk>/commerce/inventory/", m.InventoryView.as_view(), name="admin-inventory"),
    path("projects/<int:project_pk>/commerce/orders/", m.OrderListView.as_view(), name="admin-orders"),
    path("projects/<int:project_pk>/commerce/orders/<int:pk>/", m.OrderDetailView.as_view(), name="admin-order"),
    path("projects/<int:project_pk>/commerce/orders/<int:pk>/refund/", m.OrderRefundView.as_view(), name="admin-order-refund"),
    path("projects/<int:project_pk>/commerce/orders/<int:pk>/cancel/", m.OrderCancelView.as_view(), name="admin-order-cancel"),
    path("projects/<int:project_pk>/commerce/discounts/", m.DiscountListCreateView.as_view(), name="admin-discounts"),
    path("projects/<int:project_pk>/commerce/sales/", m.SalesSummaryView.as_view(), name="admin-sales"),
    path("projects/<int:project_pk>/commerce/plans/", m.PlanListCreateView.as_view(), name="admin-plans"),
    path("projects/<int:project_pk>/commerce/subscriptions/", m.SubscriptionListCreateView.as_view(), name="admin-subscriptions"),
    path("projects/<int:project_pk>/commerce/subscriptions/<int:pk>/cancel/", m.SubscriptionCancelView.as_view(), name="admin-subscription-cancel"),
    path("projects/<int:project_pk>/commerce/subscriptions/renew/", m.SubscriptionRenewView.as_view(), name="admin-subscriptions-renew"),
    path("projects/<int:project_pk>/commerce/currency/", m.CurrencyView.as_view(), name="admin-currency"),
    path("projects/<int:project_pk>/commerce/currency/revenue/", m.CurrencyRevenueView.as_view(), name="admin-currency-revenue"),
    path("projects/<int:project_pk>/campaigns/", m.CampaignListCreateView.as_view(), name="admin-campaigns"),
    path("projects/<int:project_pk>/campaigns/<int:pk>/send/", m.CampaignSendView.as_view(), name="admin-campaign-send"),

    # Website management (authenticated) — keyed by project, over publishing.
    path("projects/<int:project_pk>/website/", w.WebsiteView.as_view(), name="website"),
    path("projects/<int:project_pk>/website/publish/", w.PublishView.as_view(), name="website-publish"),
    path("projects/<int:project_pk>/website/versions/", w.VersionListView.as_view(), name="website-versions"),
    path("projects/<int:project_pk>/website/rollback/", w.RollbackView.as_view(), name="website-rollback"),
    path("projects/<int:project_pk>/website/domains/", w.DomainListCreateView.as_view(), name="website-domains"),
    path("projects/<int:project_pk>/website/leads/", w.FormLeadListView.as_view(), name="website-leads"),
    path("projects/<int:project_pk>/website/monitoring/", w.MonitoringView.as_view(), name="website-monitoring"),
    path("projects/<int:project_pk>/website/analytics/", w.AnalyticsView.as_view(), name="website-analytics"),
    path("website/domains/<int:pk>/verify/", w.DomainVerifyView.as_view(), name="domain-verify"),
    path("website/domains/<int:pk>/ssl/", w.DomainSslView.as_view(), name="domain-ssl"),
    path("website/domains/<int:pk>/", w.DomainRemoveView.as_view(), name="domain-remove"),
]
