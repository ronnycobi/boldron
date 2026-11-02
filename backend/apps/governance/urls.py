from django.urls import path

from apps.governance.api import (
    AccountStatusView,
    AppealView,
    StaffAccountView,
    StaffAppealView,
)

app_name = "governance"

urlpatterns = [
    path("orgs/<int:org_pk>/account/", AccountStatusView.as_view(), name="status"),
    path("orgs/<int:org_pk>/account/appeal/", AppealView.as_view(), name="appeal"),
    path("governance/admin/orgs/<int:org_pk>/status/",
         StaffAccountView.as_view(), name="admin_status"),
    path("governance/admin/appeals/", StaffAppealView.as_view(), name="admin_appeals"),
    path("governance/admin/appeals/<int:pk>/",
         StaffAppealView.as_view(), name="admin_appeal"),
]
