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

# Module imports
from .. import BaseAPIView


def _run_export_in_background(**kwargs):
    """Run the export task synchronously in a worker thread and clean up DB
    connections after. Avoids the Celery dependency."""
    try:
        issue_export_task(**kwargs)
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

            threading.Thread(
                target=_run_export_in_background,
                kwargs={
                    "provider": exporter.provider,
                    "workspace_id": workspace.id,
                    "project_ids": project_ids,
                    "token_id": exporter.token,
                    "multiple": multiple,
                    "slug": slug,
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

        if request.GET.get("per_page", False) and request.GET.get(
            "cursor", False
        ):
            return self.paginate(
                order_by=request.GET.get("order_by", "-created_at"),
                request=request,
                queryset=exporter_history,
                on_results=lambda exporter_history: ExporterHistorySerializer(
                    exporter_history, many=True
                ).data,
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

        workspace_issues = (
            Issue.objects.filter(
                workspace__id=workspace.id,
                project_id__in=project_ids,
                project__project_projectmember__member=request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
            )
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
            .order_by("project__identifier", "sequence_id")
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
