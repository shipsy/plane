import logging

# Third Party imports
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import allow_permission, ROLE
from plane.app.serializers import ExporterHistorySerializer
from plane.bgtasks.export_task import issue_export_task

from plane.db.models import (
    ExporterHistory,
    Project,
    Workspace,
)
from plane.settings.storage import S3Storage
from plane.utils.issue_filters import issue_filters

# Module imports
from .. import BaseAPIView

logger = logging.getLogger("plane.exporter")


class ExportIssuesEndpoint(BaseAPIView):
    model = ExporterHistory
    serializer_class = ExporterHistorySerializer

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def post(self, request, slug):
        # Get the workspace
        workspace = Workspace.objects.get(slug=slug)

        provider = request.data.get("provider", False)
        multiple = request.data.get("multiple", False)
        project_ids = request.data.get("project", [])

        if provider == "csv":
            if not project_ids:
                project_ids = Project.objects.filter(
                    workspace__slug=slug,
                    project_projectmember__member=request.user,
                    project_projectmember__is_active=True,
                    archived_at__isnull=True,
                ).values_list("id", flat=True)
                project_ids = [str(project_id) for project_id in project_ids]

            exporter = ExporterHistory.objects.create(
                workspace=workspace,
                project=project_ids,
                initiated_by=request.user,
                provider=provider,
                type="issue_exports",
            )

            # Forward the same filters the user has applied on the frontend
            # (assignees, state, labels, priority, sub_issue, cycle, module,
            # start_date, target_date, search, hub/customer/vendor/worker/
            # business fields, custom_properties, etc.) so the export matches
            # the list view 1:1.
            filters = issue_filters(request.query_params, "GET")
            custom_properties = filters.pop("custom_properties", {}) or {}
            order_by_param = request.query_params.get("order_by", "-created_at")
            display_properties_raw = request.query_params.get("display_properties")
            display_properties = (
                [k.strip() for k in display_properties_raw.split(",") if k.strip()]
                if display_properties_raw
                else None
            )
            issue_export_task.delay(
                provider=exporter.provider,
                workspace_id=workspace.id,
                project_ids=project_ids,
                token_id=exporter.token,
                multiple=multiple,
                slug=slug,
                filters=filters,
                custom_properties=custom_properties,
                order_by_param=order_by_param,
                display_properties=display_properties,
            )
            return Response(
                {
                    "message": "Once the export is ready you will be able to download it"
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": f"Provider '{provider}' not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @allow_permission(
        allowed_roles=[ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE"
    )
    def get(self, request, slug):
        exporter_history = ExporterHistory.objects.filter(
            workspace__slug=slug,
            type="issue_exports",
        ).select_related("workspace", "initiated_by")

        # Build one request-aware S3Storage. This is exactly the same pattern
        # used by /api/.../assets/ for image downloads — endpoint_url is built
        # from request.get_host(), so the resulting presigned URL points to
        # whatever host the browser is already talking to (proxy port, public
        # domain, etc.).
        storage = S3Storage(request=request)

        def _resign(row_data, row_obj):
            """Override the stale `url` on each serialized row with a fresh
            presigned URL minted against the current request host."""
            key = row_obj.key
            if not key:
                row_data["url"] = None
                return row_data
            try:
                fresh_url = storage.generate_presigned_url(
                    object_name=key,
                    expiration=7 * 24 * 60 * 60,
                    disposition="attachment",
                )
                row_data["url"] = fresh_url
            except Exception:
                logger.exception("Failed to resign export URL for token=%s", row_obj.token)
            return row_data

        def _on_results(rows):
            serialized = ExporterHistorySerializer(rows, many=True).data
            return [_resign(d, r) for d, r in zip(serialized, rows)]

        if request.GET.get("per_page", False) and request.GET.get(
            "cursor", False
        ):
            return self.paginate(
                order_by=request.GET.get("order_by", "-created_at"),
                request=request,
                queryset=exporter_history,
                on_results=_on_results,
            )
        else:
            return Response(
                {"error": "per_page and cursor are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
