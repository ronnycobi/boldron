from django.urls import path

from apps.organizations.api import (
    AcceptInvitationView,
    InvitationListCreateView,
    InvitationResendView,
    InvitationRevokeView,
    LeaveOrganizationView,
    MemberDetailView,
    MemberListView,
    OrganizationAiView,
    OrganizationDetailView,
    OrganizationListCreateView,
    OrganizationRolesView,
)

app_name = "organizations"

urlpatterns = [
    path("organizations/", OrganizationListCreateView.as_view(), name="list"),
    path("organizations/<int:pk>/", OrganizationDetailView.as_view(), name="detail"),
    path("organizations/<int:pk>/roles/", OrganizationRolesView.as_view(), name="roles"),
    path("organizations/<int:pk>/ai/", OrganizationAiView.as_view(), name="ai"),
    path("organizations/<int:pk>/members/", MemberListView.as_view(), name="members"),
    path("organizations/<int:pk>/members/<int:user_id>/", MemberDetailView.as_view(), name="member-detail"),
    path("organizations/<int:pk>/leave/", LeaveOrganizationView.as_view(), name="leave"),
    path("organizations/<int:pk>/invitations/", InvitationListCreateView.as_view(), name="invitations"),
    path("organizations/<int:pk>/invitations/<int:inv_id>/revoke/", InvitationRevokeView.as_view(), name="invitation-revoke"),
    path("organizations/<int:pk>/invitations/<int:inv_id>/resend/", InvitationResendView.as_view(), name="invitation-resend"),
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
]
