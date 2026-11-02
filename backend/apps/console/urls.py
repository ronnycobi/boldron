from django.urls import path

from apps.console import views

app_name = "console"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("orgs/", views.organizations, name="orgs"),
    path("orgs/<int:pk>/", views.organization_detail, name="org"),
    path("users/", views.users, name="users"),
    path("projects/", views.projects, name="projects"),
    path("tasks/", views.tasks, name="tasks"),
    path("economics/", views.economics, name="economics"),
    path("deployments/", views.deployments, name="deployments"),
    path("mobile/", views.mobile_releases, name="mobile"),
    path("websites/", views.websites, name="websites"),
    path("connectors/", views.connectors, name="connectors"),
    path("skills/", views.skills, name="skills"),
    path("hooks/", views.hooks, name="hooks"),
    path("leads/", views.leads, name="leads"),
    path("governance/", views.governance, name="governance"),
    path("legal/", views.legal, name="legal"),
    path("privacy/", views.privacy, name="privacy"),
    path("trust/", views.trust, name="trust"),
    path("audit/", views.audit, name="audit"),
]
