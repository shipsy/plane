import logging
from typing import List, Optional

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q, QuerySet

from plane.db.models import Workspace
from plane.utils.tts_service import get_all_accessible_hubs

logger = logging.getLogger(__name__)


class ScopedIssueFilterMixin:
    """
    Mixin for applying permission-based issue filtering.
 
    Call apply_scoped_issue_filters() manually from
    get_queryset() in each ViewSet.
    """
    
    _scoped_workspace: Optional[Workspace] = None

    def apply_scoped_issue_filters(
        self, queryset: QuerySet
    ) -> QuerySet:
        """
        Apply scoped filtering based on workspace flag.

        Filters issues by:
        - assignees contains user OR
        - created_by equals user OR
        - hub_code in user's accessible hub codes

        Call this manually from get_queryset().
        """
        workspace = self._get_workspace()
        if not workspace or not workspace.scoped_issue_access:
            return queryset

        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            return queryset

        # Build base filter: assigned or created by user
        filter_q = Q(assignees=user) | Q(created_by=user)

        # Add hub code filter only if user has hub codes
        accessible_hubs = self.get_user_accessible_hub_codes(
            user=user, workspace_slug=workspace.slug
        )
        if accessible_hubs:
            filter_q |= Q(hub_code__in=accessible_hubs)

        return queryset.filter(filter_q)

    def get_user_accessible_hub_codes(
        self, user, workspace_slug: str
    ) -> List[str]:
        """
        Get expanded list of hub codes user can access.

        Calls TTS for hub expansion with fallback.
        Returns empty list if user has no hub codes.
        """
        user_hubs = getattr(user, "hub_codes", None)
        if not user_hubs:
            return []

        try:
            expanded = get_all_accessible_hubs(user_hubs, workspace_slug)
            if expanded:
                return expanded
        except Exception as exc:
            logger.error(
                "Failed to expand hub codes for user %s in workspace %s: %s",
                getattr(user, "id", "unknown"),
                workspace_slug,
                exc,
            )

        # Fallback to direct hub codes
        return user_hubs

    def _get_workspace(self) -> Workspace:
        """Get workspace instance from ViewSet context."""
        if self._scoped_workspace:
            return self._scoped_workspace

        # Get slug from kwargs (standard pattern in all ViewSets)
        slug = self.kwargs.get("slug")
        if not slug:
            raise ImproperlyConfigured(
                "ScopedIssueFilterMixin requires `slug` in kwargs"
            )

        self._scoped_workspace = Workspace.objects.only(
            "id", "slug", "scoped_issue_access"
        ).get(slug=slug)
        return self._scoped_workspace
