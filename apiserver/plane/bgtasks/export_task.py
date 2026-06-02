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
from django.db.models import F, Func, OuterRef
from django.utils import timezone
from openpyxl import Workbook

# Module imports
from plane.db.models import ExporterHistory, FileAsset, Issue, IssueLink
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

    exporter_instance = ExporterHistory.objects.get(token=token_id)

    # Update the exporter instance with the presigned url
    if presigned_url:
        exporter_instance.url = presigned_url
        exporter_instance.status = "completed"
        exporter_instance.key = file_name
    else:
        exporter_instance.status = "failed"

    exporter_instance.save(update_fields=["status", "url", "key"])


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


def _prettify(key):
    """`trip_reference_number` → `Trip Reference Number`."""
    return key.replace("_", " ").title()


# ────────────────────────────────────────────────────────────────────────────
# Dynamic column registry
# ────────────────────────────────────────────────────────────────────────────
# Two things vary per column:
#   • the ORM `.values(...)` field(s) needed to fetch the data
#   • how to render a row dict into a CSV cell
#
# For 90 % of the columns these are trivially derivable from the Issue model
# (a CharField named `hub_code` becomes label "Hub Code" and is read from the
# row dict by key). Those columns are *introspected* at runtime — adding a
# new field to the `Issue` model makes it instantly exportable.
#
# A few columns need joins, annotations, or string concatenation. Those are
# the only ones that need a hand-written entry, kept in `COMPLEX_RESOLVERS`.

class _Resolver:
    """Holds everything needed to render one CSV column.

    Attributes:
      label: header string (e.g. "Trip Reference Number")
      values_fields: list of ORM lookup paths to add to `.values(...)`
      extractor: callable(row_dict) → cell value
      requires_annotation: optional name of an annotation that must be added
                           to the queryset (sub_issues_count / link_count /
                           attachment_count).
    """

    __slots__ = ("label", "values_fields", "extractor", "requires_annotation")

    def __init__(self, label, values_fields, extractor, requires_annotation=None):
        self.label = label
        self.values_fields = list(values_fields)
        self.extractor = extractor
        self.requires_annotation = requires_annotation


# Resolvers for columns that can't be auto-derived from a single Issue field.
# Keyed by the frontend's `displayProperties` key.
COMPLEX_RESOLVERS = {
    "state": _Resolver(
        label="State",
        values_fields=["state__name"],
        extractor=lambda i: i.get("state__name") or "",
    ),
    "assignee": _Resolver(
        label="Assignees",
        values_fields=["assignees__first_name", "assignees__last_name"],
        extractor=_assignee_cell,
    ),
    "labels": _Resolver(
        label="Labels",
        values_fields=["labels__name"],
        extractor=lambda i: i.get("labels__name") or "",
    ),
    "cycle": _Resolver(
        label="Cycle",
        values_fields=["issue_cycle__cycle__name"],
        extractor=lambda i: i.get("issue_cycle__cycle__name") or "",
    ),
    "modules": _Resolver(
        label="Modules",
        values_fields=["issue_module__module__name"],
        extractor=lambda i: i.get("issue_module__module__name") or "",
    ),
    "estimate": _Resolver(
        label="Estimate",
        values_fields=["estimate_point__value"],
        extractor=lambda i: i.get("estimate_point__value") or "",
    ),
    "issue_type": _Resolver(
        label="Issue Type",
        values_fields=["type__name"],
        extractor=lambda i: i.get("type__name") or "",
    ),
    # Frontend keys differ from Issue.field names → handled here.
    "due_date": _Resolver(
        label="Due Date",
        values_fields=["target_date"],
        extractor=lambda i: dateConverter(i.get("target_date")),
    ),
    "start_date": _Resolver(
        label="Start Date",
        values_fields=["start_date"],
        extractor=lambda i: dateConverter(i.get("start_date")),
    ),
    "created_on": _Resolver(
        label="Created On",
        values_fields=["created_at"],
        extractor=lambda i: dateTimeConverter(i.get("created_at")),
    ),
    "updated_on": _Resolver(
        label="Updated On",
        values_fields=["updated_at"],
        extractor=lambda i: dateTimeConverter(i.get("updated_at")),
    ),
    # Counts (need `.annotate(...)`).
    "link": _Resolver(
        label="Links",
        values_fields=["link_count"],
        extractor=lambda i: i.get("link_count") or 0,
        requires_annotation="link_count",
    ),
    "attachment_count": _Resolver(
        label="Attachments",
        values_fields=["attachment_count"],
        extractor=lambda i: i.get("attachment_count") or 0,
        requires_annotation="attachment_count",
    ),
    "sub_issue_count": _Resolver(
        label="Sub-issues",
        values_fields=["sub_issues_count"],
        extractor=lambda i: i.get("sub_issues_count") or 0,
        requires_annotation="sub_issues_count",
    ),
}


# Always-on columns — the ones we always emit regardless of displayProperties.
# Keep this minimal: the UI's "Issues" cell shows ID + Name, so those two
# are the only true "must-haves".
ALWAYS_COLUMNS = [
    _Resolver(
        label="ID",
        values_fields=["project__identifier", "sequence_id"],
        extractor=lambda i: f"{i['project__identifier']}-{i['sequence_id']}",
    ),
    _Resolver(
        label="Name",
        values_fields=["name"],
        extractor=lambda i: i.get("name") or "",
    ),
]


def _introspect_field(key):
    """Try to derive a resolver from the Issue model.

    Returns a `_Resolver` if the model has a concrete scalar field named
    `key`, otherwise `None`. Used as a fallback for keys not in
    `COMPLEX_RESOLVERS`.
    """
    from django.db.models import (
        CharField, TextField, IntegerField, BooleanField, FloatField,
        DecimalField, DateField, DateTimeField, EmailField, UUIDField,
        SlugField, PositiveIntegerField, PositiveSmallIntegerField,
        SmallIntegerField, BigIntegerField,
    )

    scalar_types = (
        CharField, TextField, IntegerField, BooleanField, FloatField,
        DecimalField, EmailField, UUIDField, SlugField, PositiveIntegerField,
        PositiveSmallIntegerField, SmallIntegerField, BigIntegerField,
    )
    date_types = (DateField, DateTimeField)

    try:
        field = Issue._meta.get_field(key)
    except Exception:
        return None

    if isinstance(field, date_types):
        is_datetime = isinstance(field, DateTimeField)
        return _Resolver(
            label=getattr(field, "verbose_name", key).title()
                  if isinstance(getattr(field, "verbose_name", ""), str)
                  else _prettify(key),
            values_fields=[key],
            extractor=(lambda k: lambda i: dateTimeConverter(i.get(k)))(key) if is_datetime
                      else (lambda k: lambda i: dateConverter(i.get(k)))(key),
        )

    if isinstance(field, scalar_types):
        label = getattr(field, "verbose_name", "") or _prettify(key)
        # verbose_name is sometimes the lowercase key — prettify in that case
        if isinstance(label, str) and label == key:
            label = _prettify(key)
        else:
            label = str(label).title()
        return _Resolver(
            label=label,
            values_fields=[key],
            extractor=(lambda k: lambda i: (i.get(k) if i.get(k) is not None else ""))(key),
        )

    # Foreign keys, M2M, etc. — let COMPLEX_RESOLVERS handle anything tricky.
    return None


def resolve_export_columns(display_properties=None):
    """Build the ordered list of `_Resolver` objects for this export.

    Order:
      1. ALWAYS_COLUMNS (ID, Name) — fixed.
      2. For each key in `display_properties` (in the order the frontend
         supplied them):
            a. If it's in COMPLEX_RESOLVERS → use that.
            b. Else, try `Issue._meta.get_field(key)` introspection.
            c. Else, skip (unknown key).
    """
    cols = list(ALWAYS_COLUMNS)

    if not display_properties:
        # No frontend hint → emit every complex resolver + every introspectable
        # Issue field. Stable order = COMPLEX_RESOLVERS dict order + model
        # field declaration order.
        seen = set()
        for key, resolver in COMPLEX_RESOLVERS.items():
            cols.append(resolver)
            seen.add(key)
        for field in Issue._meta.get_fields():
            if field.name in seen:
                continue
            resolver = _introspect_field(field.name)
            if resolver is not None:
                cols.append(resolver)
                seen.add(field.name)
        return cols

    seen = set()
    for key in display_properties:
        if key in seen or key == "key":
            # "key" is the UI's name for the ID column we already include.
            continue
        seen.add(key)

        resolver = COMPLEX_RESOLVERS.get(key) or _introspect_field(key)
        if resolver is None:
            continue
        cols.append(resolver)

    return cols

def _index_for(columns, header_label):
    for idx, resolver in enumerate(columns):
        if resolver.label == header_label:
            return idx
    return None


def generate_table_row(issue, columns):
    return [resolver.extractor(issue) for resolver in columns]


def generate_json_row(issue, columns):
    return {resolver.label: resolver.extractor(issue) for resolver in columns}


def update_json_row(rows, row, columns):
    assignee_key = "Assignees" if any(r.label == "Assignees" for r in columns) else None
    labels_key = "Labels" if any(r.label == "Labels" for r in columns) else None

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
    assignee_idx = _index_for(columns, "Assignees")
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

        # ── Dynamically build the queryset from the resolved columns ────────
        # 1. Resolve which columns we need.
        columns = resolve_export_columns(display_properties)
        header = [r.label for r in columns]

        # 2. Collect the union of `.values(...)` paths from every resolver,
        #    plus a couple of always-needed bookkeeping fields used by the
        #    row deduper / `id` lookup.
        values_fields = set(["id", "project__id"])
        for r in columns:
            values_fields.update(r.values_fields)
        # 3. Add annotations only for the count-resolvers that were selected.
        needed_annotations = {r.requires_annotation for r in columns if r.requires_annotation}
        annotations = {}
        if "sub_issues_count" in needed_annotations:
            annotations["sub_issues_count"] = (
                Issue.objects.filter(
                    parent=OuterRef("id"),
                    deleted_at__isnull=True,
                    is_draft=False,
                    archived_at__isnull=True,
                )
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
        if "link_count" in needed_annotations:
            annotations["link_count"] = (
                IssueLink.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
        if "attachment_count" in needed_annotations:
            annotations["attachment_count"] = (
                FileAsset.objects.filter(
                    issue_id=OuterRef("id"),
                    entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
                )
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )

        workspace_issues = (
            base_qs
            .select_related("project", "workspace", "state", "parent", "created_by", "estimate_point", "type")
            .prefetch_related("assignees", "labels", "issue_cycle__cycle", "issue_module__module")
        )
        if annotations:
            workspace_issues = workspace_issues.annotate(**annotations)
        workspace_issues = workspace_issues.values(*sorted(values_fields)).distinct()

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
