from django.urls import path

from apps.publishing import api
from apps.publishing import commerce_api as m

app_name = "commerce_api"

urlpatterns = [
    # Public storefront (shopper) — keyed by store subdomain.
    path("stores/<slug:subdomain>/products", api.ProductListView.as_view(), name="products"),
    path("stores/<slug:subdomain>/products/<slug:slug>", api.ProductDetailView.as_view(), name="product"),
    path("stores/<slug:subdomain>/checkout", api.CheckoutView.as_view(), name="checkout"),
    path("stores/<slug:subdomain>/orders/<str:reference>", api.OrderStatusView.as_view(), name="order"),

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
]
