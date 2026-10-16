# Django imports
from django.conf import settings

# Module imports
from plane.db.models import APIToken


def is_service_caller(request):
    """True when the request carries the static token or a service API token"""
    token = request.headers.get("X-Api-Key")
    if not token:
        return False
    if settings.STATIC_API_TOKEN and token == settings.STATIC_API_TOKEN:
        return True
    return APIToken.objects.filter(
        token=token, is_service=True, is_active=True
    ).exists()
