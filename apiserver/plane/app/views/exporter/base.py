import logging
import threading

# Python imports
from django.db import connections
from django.http import HttpResponse
from django.utils import timezone

# Third Party imports
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import allow_permission, ROLE
from plane.app.serializers import ExporterHistorySerializer
from plane.bgtasks.export_task import (
    create_zip_file,
    generate_csv,
    generate_json,
    generate_xlsx,
    issue_export_task,
    resolve_export_columns,
)
from django.db.models import Exists, OuterRef, Q

from plane.db.models import (
    ExporterHistory,
    Issue,
    Project,
    ProjectMember,
    State,
    Workspace,
)
from plane.settings.storage import S3Storage
from plane.utils.issue_filters import (
    apply_user_hub_filters,
    build_custom_property_q_objects,
    issue_filters,
)
from plane.utils.order_queryset import order_issue_queryset

# Module imports
from .. import BaseAPIView

logger = logging.getLogger("plane.exporter")


def _run_export_in_background(**kwargs):
    """Run the export task synchronously in a worker thread and clean up DB
    connections after. Avoids the Celery dependency."""
    token = str(kwargs.get("token_id", ""))[:8]
    try:
        issue_export_task(**kwargs)
    except Exception:
        logger.exception("export thread failed token=%s", token)
        raise
    finally:
        connections.close_all()


_LEGACY_ISSUE_EXPORT_HEADER = [
    "ID",
    "Project",
    "Name",
    "Description",
    "State",
    "Priority",
    "Created By",
    "Assignee",
    "Labels",
    "Cycle Name",
    "Cycle Start Date",
    "Cycle End Date",
    "Module Name",
    "Module Start Date",
    "Module Target Date",
    "Created At",
    "Updated At",
    "Completed At",
    "Archived At",
]

EXPORTER_MAPPER = {
    "csv": generate_csv,
    "json": generate_json,
    "xlsx": generate_xlsx,
}

def _build_list_view_base_queryset(slug, user, project_ids):
    """Mirror the baseline queryset used by WorkspaceViewIssuesViewSet.list so
    the export contains exactly the rows the user sees on the page (drafts /
    archived / triage states excluded, hub-scoped, guest restrictions applied).
    """
    qs = (
        Issue.objects.filter(
            workspace__slug=slug,
            project_id__in=project_ids,
            deleted_at__isnull=True,
            archived_at__isnull=True,
            is_draft=False,
            project__archived_at__isnull=True,
            state_id__isnull=False,
        )
        .exclude(
            state_id__in=State.objects.filter(is_triage=True).values("id")
        )
        .filter(
            Exists(
                ProjectMember.objects.filter(
                    project_id=OuterRef("project_id"),
                    member=user,
                    is_active=True,
                )
            )
        )
    )

    # Mirror the guest_view_all_features split applied by the list view.
    guest_pm = ProjectMember.objects.filter(
        project_id=OuterRef("project_id"),
        member=user,
        is_active=True,
        role=5,
    )
    non_guest_pm = ProjectMember.objects.filter(
        project_id=OuterRef("project_id"),
        member=user,
        is_active=True,
        role__gt=5,
    )
    qs = qs.filter(
        Exists(non_guest_pm)
        | (Exists(guest_pm) & Q(project__guest_view_all_features=True))
        | (Exists(guest_pm) & Q(project__guest_view_all_features=False) & Q(created_by=user))
    )

    return apply_user_hub_filters(qs, user, workspace_slug=slug)


CONTENT_TYPES = {
    "csv": "text/csv",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


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

        if provider in ["csv", "xlsx", "json"]:
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
            threading.Thread(
                target=_run_export_in_background,
                kwargs={
                    "provider": exporter.provider,
                    "workspace_id": workspace.id,
                    "project_ids": project_ids,
                    "token_id": exporter.token,
                    "multiple": multiple,
                    "slug": slug,
                    "filters": filters,
                    "custom_properties": custom_properties,
                    "order_by_param": order_by_param,
                    "display_properties": display_properties,
                },
                daemon=True,
            ).start()
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


class DownloadIssuesEndpoint(BaseAPIView):
    """Synchronously build and return the export file as a download. No Celery, no S3."""

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def post(self, request, slug):
        provider = request.data.get("provider", False)
        multiple = request.data.get("multiple", False)
        project_ids = request.data.get("project", [])

        if provider not in ["csv", "xlsx", "json"]:
            return Response(
                {"error": f"Provider '{provider}' not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        workspace = Workspace.objects.get(slug=slug)

        if not project_ids:
            project_ids = list(
                Project.objects.filter(
                    workspace__slug=slug,
                    project_projectmember__member=request.user,
                    project_projectmember__is_active=True,
                    archived_at__isnull=True,
                ).values_list("id", flat=True)
            )
            project_ids = [str(project_id) for project_id in project_ids]

        # Parse same filters the issues list view uses (assignees, state,
        # labels, priority, sub_issue, cycle, module, start_date, target_date,
        # search/name, hub/customer/vendor/worker/business fields,
        # custom_properties, etc.) from the request query string so the export
        # matches what the user sees on the frontend.
        filters = issue_filters(request.query_params, "GET")
        custom_properties = filters.pop("custom_properties", {}) or {}
        custom_filters = build_custom_property_q_objects(custom_properties)
        order_by_param = request.query_params.get("order_by", "-created_at")
        display_properties_raw = request.query_params.get("display_properties")
        display_properties = (
            [k.strip() for k in display_properties_raw.split(",") if k.strip()]
            if display_properties_raw
            else None
        )
        columns = resolve_export_columns(display_properties)
        header = [label for (_key, label, _fn) in columns]

        base_qs = (
            _build_list_view_base_queryset(
                slug=slug,
                user=request.user,
                project_ids=project_ids,
            )
            .filter(*custom_filters)
            .filter(**filters)
        )
        base_qs, _ = order_issue_queryset(
            issue_queryset=base_qs,
            order_by_param=order_by_param,
        )
        workspace_issues = (
            base_qs
            .select_related("project", "workspace", "state", "parent", "created_by")
            .prefetch_related(
                "assignees",
                "labels",
                "issue_cycle__cycle",
                "issue_module__module",
            )
            .values(
                "id",
                "project__identifier",
                "project__name",
                "project__id",
                "sequence_id",
                "name",
                "description_stripped",
                "priority",
                "state__name",
                "start_date",
                "target_date",
                "created_at",
                "updated_at",
                "completed_at",
                "archived_at",
                "issue_cycle__cycle__name",
                "issue_cycle__cycle__start_date",
                "issue_cycle__cycle__end_date",
                "issue_module__module__name",
                "issue_module__module__start_date",
                "issue_module__module__target_date",
                "created_by__first_name",
                "created_by__last_name",
                "assignees__first_name",
                "assignees__last_name",
                "labels__name",
            )
            .distinct()
        )

        exporter = EXPORTER_MAPPER.get(provider)
        files = []

        if multiple:
            for project_id in project_ids:
                issues = workspace_issues.filter(project__id=project_id)
                exporter(header, project_id, issues, files, columns)
        else:
            exporter(header, str(workspace.id), workspace_issues, files, columns)

        date_str = timezone.now().date().isoformat()

        # Single project / single file → send the raw file. Multi-file → zip it.
        if len(files) == 1 and not multiple:
            filename, content = files[0]
            download_name = f"{slug}-issues-{date_str}.{provider}"
            content_type = CONTENT_TYPES[provider]
            response_body = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8")
            response = HttpResponse(response_body, content_type=content_type)
            response["Content-Disposition"] = f'attachment; filename="{download_name}"'
            return response

        zip_buffer = create_zip_file(files)
        download_name = f"{slug}-issues-{date_str}.zip"
        response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{download_name}"'
        return response
