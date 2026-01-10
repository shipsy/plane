from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.api.views.base import BaseAPIView
from plane.db.models import Workspace


class WorkspaceScopedIssueAccessAPIEndpoint(BaseAPIView):
    """
    Endpoint for TTS to enable/disable scoped issue access
    at workspace level.
    """

    def post(self, request, slug):
        """Enable scoped issue access."""
        return self._update_flag(slug=slug, enabled=True)

    def delete(self, request, slug):
        """Disable scoped issue access."""
        return self._update_flag(slug=slug, enabled=False)

    def patch(self, request, slug):
        """Toggle scoped issue access based on request payload."""
        enabled = request.data.get("enabled")
        if enabled is None:
            return Response(
                {"error": "`enabled` boolean field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(enabled, bool):
            return Response(
                {"error": "`enabled` must be a boolean"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._update_flag(slug=slug, enabled=enabled)

    def get(self, request, slug):
        """Get current scoped issue access status."""
        workspace = get_object_or_404(Workspace, slug=slug)
        return Response(
            {
                "success": True,
                "scoped_issue_access": workspace.scoped_issue_access,
            },
            status=status.HTTP_200_OK,
        )

    def _update_flag(self, slug, enabled):
        workspace = get_object_or_404(Workspace, slug=slug)
        workspace.scoped_issue_access = enabled
        workspace.save(update_fields=["scoped_issue_access"])
        return Response(
            {
                "success": True,
                "scoped_issue_access": workspace.scoped_issue_access,
            },
            status=status.HTTP_200_OK,
        )
