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
)
from plane.db.models import ExporterHistory, Issue, Project, Workspace
from plane.settings.storage import S3Storage
from plane.utils.issue_filters import issue_filters
from plane.utils.order_queryset import order_issue_queryset

# Module imports
from .. import BaseAPIView

logger = logging.getLogger("plane.exporter")


def _run_export_in_background(**kwargs):
    """Run the export task synchronously in a worker thread and clean up DB
    connections after. Avoids the Celery dependency."""
    token = str(kwargs.get("token_id", ""))[:8]
    print(
        f"[EXPORT_BG] start token={token} provider={kwargs.get('provider')} "
        f"slug={kwargs.get('slug')} projects={len(kwargs.get('project_ids') or [])} "
        f"multiple={kwargs.get('multiple')}"
    )
    try:
        issue_export_task(**kwargs)
        print(f"[EXPORT_BG] finished token={token}")
    except Exception as e:
        print(f"[EXPORT_BG] FAILED token={token} err={e}")
        logger.exception("export thread failed token=%s", token)
        raise
    finally:
        connections.close_all()


ISSUE_EXPORT_HEADER = [
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

        print(
            f"[EXPORT_POST] slug={slug} host={request.get_host()} provider={provider} "
            f"multiple={multiple} project_ids={project_ids} user={request.user.id}"
        )

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
            # start_date, target_date, search, etc.) so the export matches the
            # list view 1:1.
            filters = issue_filters(request.query_params, "GET")
            filters.pop("custom_properties", None)
            order_by_param = request.query_params.get("order_by", "-created_at")
            print(
                f"[EXPORT_POST] full_path={request.get_full_path()}\n"
                f"[EXPORT_POST] query_params={dict(request.query_params)}\n"
                f"[EXPORT_POST] body={dict(request.data)}\n"
                f"[EXPORT_POST] parsed_filters={filters}\n"
                f"[EXPORT_POST] order_by={order_by_param}"
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
                    "order_by_param": order_by_param,
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
        # ─── DEBUG ──────────────────────────────────────────────────────────
        print(f"[EXPORT_HISTORY] GET slug={slug} host={request.get_host()} scheme={request.scheme}")
        logger.info(
            "[EXPORT_HISTORY] GET slug=%s host=%s scheme=%s user=%s",
            slug,
            request.get_host(),
            request.scheme,
            getattr(request.user, "id", "anon"),
        )
        # ────────────────────────────────────────────────────────────────────

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
                print(f"[EXPORT_HISTORY]   row={str(row_obj.token)[:8]} status={row_obj.status} key=None → no URL")
                row_data["url"] = None
                return row_data
            try:
                fresh_url = storage.generate_presigned_url(
                    object_name=key,
                    expiration=7 * 24 * 60 * 60,
                    disposition="attachment",
                )
                print(
                    f"[EXPORT_HISTORY]   row={str(row_obj.token)[:8]} status={row_obj.status} "
                    f"key={key} → {fresh_url[:120]}..."
                )
                row_data["url"] = fresh_url
            except Exception as e:
                print(f"[EXPORT_HISTORY]   row={str(row_obj.token)[:8]} re-sign FAILED: {e}")
                logger.exception("Failed to resign export URL for token=%s", row_obj.token)
            return row_data

        def _on_results(rows):
            serialized = ExporterHistorySerializer(rows, many=True).data
            print(f"[EXPORT_HISTORY] paginated batch size={len(serialized)}")
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
        # search/name, etc.) from the request query string so the export
        # matches what the user sees on the frontend.
        filters = issue_filters(request.query_params, "GET")
        filters.pop("custom_properties", None)
        order_by_param = request.query_params.get("order_by", "-created_at")
        print(
            f"[DOWNLOAD_POST] full_path={request.get_full_path()}\n"
            f"[DOWNLOAD_POST] query_params={dict(request.query_params)}\n"
            f"[DOWNLOAD_POST] body={dict(request.data)}\n"
            f"[DOWNLOAD_POST] parsed_filters={filters}\n"
            f"[DOWNLOAD_POST] order_by={order_by_param}\n"
            f"[DOWNLOAD_POST] project_ids={project_ids}"
        )

        base_qs = (
            Issue.objects.filter(
                workspace__id=workspace.id,
                project_id__in=project_ids,
                project__project_projectmember__member=request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
            )
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
                exporter(ISSUE_EXPORT_HEADER, project_id, issues, files)
        else:
            exporter(ISSUE_EXPORT_HEADER, str(workspace.id), workspace_issues, files)

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
