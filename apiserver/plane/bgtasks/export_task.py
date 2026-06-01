# Python imports
import csv
import io
import json
import zipfile

import boto3
from botocore.client import Config

# Third party imports
from celery import shared_task

# Django imports
from django.conf import settings
from django.utils import timezone
from openpyxl import Workbook

# Module imports
from plane.db.models import ExporterHistory
from plane.utils.exception_logger import log_exception
from plane.utils.order_queryset import order_issue_queryset


def dateTimeConverter(time):
    if time:
        return time.strftime("%a, %d %b %Y %I:%M:%S %Z%z")


def dateConverter(time):
    if time:
        return time.strftime("%a, %d %b %Y")


def create_csv_file(data):
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, delimiter=",", quoting=csv.QUOTE_ALL)

    for row in data:
        csv_writer.writerow(row)

    csv_buffer.seek(0)
    return csv_buffer.getvalue()


def create_json_file(data):
    return json.dumps(data)


def create_xlsx_file(data):
    workbook = Workbook()
    sheet = workbook.active

    for row in data:
        sheet.append(row)

    xlsx_buffer = io.BytesIO()
    workbook.save(xlsx_buffer)
    xlsx_buffer.seek(0)
    return xlsx_buffer.getvalue()


def create_zip_file(files):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for filename, file_content in files:
            zipf.writestr(filename, file_content)

    zip_buffer.seek(0)
    return zip_buffer


EXPORT_CONTENT_TYPES = {
    "csv": "text/csv",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


def upload_to_s3(file_obj, workspace_id, token_id, slug, extension="zip"):
    content_type = EXPORT_CONTENT_TYPES.get(extension, "application/octet-stream")
    file_name = (
        f"{workspace_id}/export-{slug}-{token_id[:6]}-"
        f"{str(timezone.now().date())}.{extension}"
    )
    expires_in = 7 * 24 * 60 * 60

    print(
        f"[EXPORT_UPLOAD] start token={str(token_id)[:8]} slug={slug} "
        f"bucket={settings.AWS_STORAGE_BUCKET_NAME} key={file_name} "
        f"content_type={content_type} "
        f"USE_MINIO={settings.USE_MINIO} "
        f"AWS_S3_ENDPOINT_URL={settings.AWS_S3_ENDPOINT_URL} "
        f"AWS_S3_CUSTOM_DOMAIN={getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)} "
        f"AWS_S3_URL_PROTOCOL={getattr(settings, 'AWS_S3_URL_PROTOCOL', None)}"
    )

    if settings.USE_MINIO:
        upload_s3 = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
        upload_s3.upload_fileobj(
            file_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            file_name,
            ExtraArgs={"ACL": "public-read", "ContentType": content_type},
        )

        # Generate presigned url for the uploaded file with different base
        presign_s3 = boto3.client(
            "s3",
            endpoint_url=f"{settings.AWS_S3_URL_PROTOCOL}//{str(settings.AWS_S3_CUSTOM_DOMAIN).replace('/uploads', '')}/",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )

        presigned_url = presign_s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": file_name,
            },
            ExpiresIn=expires_in,
        )
    else:
        # If endpoint url is present, use it
        if settings.AWS_S3_ENDPOINT_URL:
            s3 = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4"),
            )
        else:
            s3 = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4"),
            )

        # Upload the file to S3
        s3.upload_fileobj(
            file_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            file_name,
            ExtraArgs={"ContentType": content_type},
        )

        # Generate presigned url for the uploaded file
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": file_name,
            },
            ExpiresIn=expires_in,
        )

    print(
        f"[EXPORT_UPLOAD] stored token={str(token_id)[:8]} key={file_name} "
        f"presigned_url={(presigned_url[:140] + '...') if presigned_url else None}"
    )

    exporter_instance = ExporterHistory.objects.get(token=token_id)

    # Update the exporter instance with the presigned url
    if presigned_url:
        exporter_instance.url = presigned_url
        exporter_instance.status = "completed"
        exporter_instance.key = file_name
    else:
        exporter_instance.status = "failed"

    exporter_instance.save(update_fields=["status", "url", "key"])
    print(f"[EXPORT_UPLOAD] DB updated token={str(token_id)[:8]} status={exporter_instance.status}")


# Column registry. Each column is gated on a `displayProperties` key the
# frontend sends; `"always"` means the column is unconditionally included
# (id, name, project are not toggleable on the page either).
#
# The order here defines the column order in the exported file.
def _assignee_cell(issue):
    if issue.get("assignees__first_name") and issue.get("assignees__last_name"):
        return f"{issue['assignees__first_name']} {issue['assignees__last_name']}"
    return ""


def _created_by_cell(issue):
    if issue.get("created_by__first_name") and issue.get("created_by__last_name"):
        return f"{issue['created_by__first_name']} {issue['created_by__last_name']}"
    return ""


EXPORT_COLUMNS = [
    # (display_key, header, extractor)
    ("always", "ID", lambda i: f"{i['project__identifier']}-{i['sequence_id']}"),
    ("always", "Project", lambda i: i["project__name"]),
    ("always", "Name", lambda i: i["name"]),
    ("always", "Description", lambda i: i["description_stripped"]),
    ("state", "State", lambda i: i["state__name"]),
    ("priority", "Priority", lambda i: i["priority"]),
    ("always", "Created By", _created_by_cell),
    ("assignee", "Assignee", _assignee_cell),
    ("labels", "Labels", lambda i: i["labels__name"] if i.get("labels__name") else ""),
    ("cycle", "Cycle Name", lambda i: i["issue_cycle__cycle__name"]),
    ("cycle", "Cycle Start Date", lambda i: dateConverter(i["issue_cycle__cycle__start_date"])),
    ("cycle", "Cycle End Date", lambda i: dateConverter(i["issue_cycle__cycle__end_date"])),
    ("modules", "Module Name", lambda i: i["issue_module__module__name"]),
    ("modules", "Module Start Date", lambda i: dateConverter(i["issue_module__module__start_date"])),
    ("modules", "Module Target Date", lambda i: dateConverter(i["issue_module__module__target_date"])),
    ("start_date", "Start Date", lambda i: dateConverter(i.get("start_date"))),
    ("due_date", "Due Date", lambda i: dateConverter(i.get("target_date"))),
    ("created_on", "Created At", lambda i: dateTimeConverter(i["created_at"])),
    ("updated_on", "Updated At", lambda i: dateTimeConverter(i["updated_at"])),
    ("always", "Completed At", lambda i: dateTimeConverter(i["completed_at"])),
    ("always", "Archived At", lambda i: dateTimeConverter(i["archived_at"])),
]


def resolve_export_columns(display_properties=None):
    """Filter EXPORT_COLUMNS to the subset enabled by displayProperties.

    `display_properties` is the list of enabled property keys forwarded by
    the frontend. If `None`, all columns are kept (so direct API callers
    still get the full export). "always" columns are always included.
    """
    if display_properties is None:
        return list(EXPORT_COLUMNS)
    enabled = set(display_properties)
    return [c for c in EXPORT_COLUMNS if c[0] == "always" or c[0] in enabled]


def _index_for(columns, header_label):
    for idx, (_key, label, _fn) in enumerate(columns):
        if label == header_label:
            return idx
    return None


def generate_table_row(issue, columns):
    return [extractor(issue) for (_key, _label, extractor) in columns]


def generate_json_row(issue, columns):
    return {label: extractor(issue) for (_key, label, extractor) in columns}


def update_json_row(rows, row, columns):
    assignee_key = "Assignee" if any(label == "Assignee" for _, label, _ in columns) else None
    labels_key = "Labels" if any(label == "Labels" for _, label, _ in columns) else None

    matched_index = next(
        (index for index, existing_row in enumerate(rows) if existing_row["ID"] == row["ID"]),
        None,
    )

    if matched_index is not None:
        if assignee_key:
            existing = rows[matched_index].get(assignee_key) or ""
            incoming = row.get(assignee_key) or ""
            if incoming and incoming not in existing:
                rows[matched_index][assignee_key] = (
                    f"{existing}, {incoming}" if existing else incoming
                )
        if labels_key:
            existing = rows[matched_index].get(labels_key) or ""
            incoming = row.get(labels_key) or ""
            if incoming and incoming not in existing:
                rows[matched_index][labels_key] = (
                    f"{existing}, {incoming}" if existing else incoming
                )
    else:
        rows.append(row)


def update_table_row(rows, row, columns):
    id_idx = _index_for(columns, "ID")
    assignee_idx = _index_for(columns, "Assignee")
    labels_idx = _index_for(columns, "Labels")

    matched_index = next(
        (index for index, existing_row in enumerate(rows) if existing_row[id_idx] == row[id_idx]),
        None,
    )

    if matched_index is not None:
        if assignee_idx is not None:
            existing = rows[matched_index][assignee_idx] or ""
            incoming = row[assignee_idx] or ""
            if incoming and incoming not in existing:
                rows[matched_index][assignee_idx] = (
                    f"{existing}, {incoming}" if existing else incoming
                )
        if labels_idx is not None:
            existing = rows[matched_index][labels_idx] or ""
            incoming = row[labels_idx] or ""
            if incoming and incoming not in existing:
                rows[matched_index][labels_idx] = (
                    f"{existing}, {incoming}" if existing else incoming
                )
    else:
        rows.append(row)


def generate_csv(header, project_id, issues, files, columns):
    """Generate CSV export for the passed issues using `columns`."""
    rows = [header]
    for issue in issues:
        row = generate_table_row(issue, columns)
        update_table_row(rows, row, columns)
    csv_file = create_csv_file(rows)
    files.append((f"{project_id}.csv", csv_file))


def generate_json(header, project_id, issues, files, columns):
    rows = []
    for issue in issues:
        row = generate_json_row(issue, columns)
        update_json_row(rows, row, columns)
    json_file = create_json_file(rows)
    files.append((f"{project_id}.json", json_file))


def generate_xlsx(header, project_id, issues, files, columns):
    rows = [header]
    for issue in issues:
        row = generate_table_row(issue, columns)
        update_table_row(rows, row, columns)
    xlsx_file = create_xlsx_file(rows)
    files.append((f"{project_id}.xlsx", xlsx_file))


@shared_task
def issue_export_task(
    provider,
    workspace_id,
    project_ids,
    token_id,
    multiple,
    slug,
    filters=None,
    custom_properties=None,
    order_by_param="-created_at",
    display_properties=None,
):
    try:
        exporter_instance = ExporterHistory.objects.get(token=token_id)
        exporter_instance.status = "processing"
        exporter_instance.save(update_fields=["status"])

        # Use the same baseline queryset the list view uses so the export
        # mirrors what the user sees on the page (drafts/archived/triage
        # excluded, hub scoped, guest restrictions applied).
        from plane.app.views.exporter.base import _build_list_view_base_queryset
        from plane.utils.issue_filters import build_custom_property_q_objects
        base_qs = _build_list_view_base_queryset(
            slug=slug,
            user=exporter_instance.initiated_by,
            project_ids=project_ids,
        )
        if custom_properties:
            base_qs = base_qs.filter(*build_custom_property_q_objects(custom_properties))
        if filters:
            base_qs = base_qs.filter(**filters)
        base_qs, _ = order_issue_queryset(
            issue_queryset=base_qs,
            order_by_param=order_by_param,
        )

        workspace_issues = (
            (
                base_qs
                .select_related(
                    "project", "workspace", "state", "parent", "created_by"
                )
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
            )
            .distinct()
        )
        # Resolve which columns to include based on the user's displayProperties.
        columns = resolve_export_columns(display_properties)
        header = [label for (_key, label, _fn) in columns]

        EXPORTER_MAPPER = {
            "csv": generate_csv,
            "json": generate_json,
            "xlsx": generate_xlsx,
        }

        files = []
        if multiple:
            for project_id in project_ids:
                issues = workspace_issues.filter(project__id=project_id)
                exporter = EXPORTER_MAPPER.get(provider)
                if exporter is not None:
                    exporter(header, project_id, issues, files, columns)
        else:
            exporter = EXPORTER_MAPPER.get(provider)
            if exporter is not None:
                exporter(header, workspace_id, workspace_issues, files, columns)

        # Single file → upload as the raw provider extension (.csv/.json/.xlsx).
        # Multiple files → zip them together. Mirrors DownloadIssuesEndpoint.
        if not multiple and len(files) == 1:
            _filename, content = files[0]
            payload = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8")
            upload_to_s3(io.BytesIO(payload), workspace_id, token_id, slug, extension=provider)
        else:
            zip_buffer = create_zip_file(files)
            upload_to_s3(zip_buffer, workspace_id, token_id, slug, extension="zip")

    except Exception as e:
        exporter_instance = ExporterHistory.objects.get(token=token_id)
        exporter_instance.status = "failed"
        exporter_instance.reason = str(e)
        exporter_instance.save(update_fields=["status", "reason"])
        log_exception(e)
        return
