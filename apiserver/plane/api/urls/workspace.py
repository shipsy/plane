from django.urls import path

from plane.api.views.workspace import WorkspaceScopedIssueAccessAPIEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/scoped-issue-access/",
        WorkspaceScopedIssueAccessAPIEndpoint.as_view(),
        name="workspace-scoped-issue-access",
    ),
]
