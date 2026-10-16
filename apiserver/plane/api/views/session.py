# Django imports
from django.db.models import CharField
from django.db.models.functions import Cast

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.db.models import Session, User
from plane.utils.service_auth import is_service_caller
from .base import BaseAPIView


class UserSessionRevokeEndpoint(BaseAPIView):
    """
    Ends every Plane session of a user. Called by the ticketing tool when the
    user logs out of the Ops Dashboard or is disabled there.
    """

    def post(self, request):
        if not is_service_caller(request):
            return Response(
                {"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN
            )

        email = str(request.data.get("email") or "").strip().lower()
        if not email:
            return Response(
                {"error": "email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sessions store the user id as text; match it in one query
        user_ids = (
            User.objects.filter(email=email)
            .annotate(user_id_text=Cast("id", output_field=CharField()))
            .values("user_id_text")
        )
        Session.objects.filter(user_id__in=user_ids).delete()

        # Same response whether or not the user exists
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
