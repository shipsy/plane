from django.urls import path

from plane.api.views import UserSessionRevokeEndpoint


urlpatterns = [
    path(
        "users/sessions/revoke/",
        UserSessionRevokeEndpoint.as_view(),
        name="user-sessions-revoke",
    ),
]
