import json

from django.core.serializers.json import DjangoJSONEncoder

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import (
    Case,
    CharField,
    Exists,
    F,
    Func,
    Max,
    OuterRef,
    Q,
    Value,
    When,
    Subquery,
)
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError # Added import

# Module imports
from plane.api.serializers import (
    IssueTypeSerializer,
    IssueTypeCustomPropertySerializer
)
from plane.app.permissions import (
    ProjectLitePermission,
)
from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import (
    Workspace,
    IssueType,
    IssueTypeCustomProperty
)
from .base import BaseAPIView

class IssueTypeAPIEndpoint(BaseAPIView):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions related to comments of the particular issue.

    """

    serializer_class = IssueTypeSerializer
    model = IssueType
    webhook_event = "issue_type"
    permission_classes = [
        ProjectLitePermission,
    ]

    def get_queryset(self):
        return (
            IssueType.objects.filter(
                workspace__slug=self.kwargs.get("slug")
            )
            .select_related("workspace")
            .order_by(self.kwargs.get("order_by", "-created_at"))
            .distinct()
        )

    def get(self, request, slug, pk=None):
        if pk:
            issue_type = self.get_queryset().get(pk=pk)
            serializer = IssueTypeSerializer(
                issue_type,
                fields=self.fields,
                expand=self.expand,
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        return self.paginate(
            request=request,
            queryset=(self.get_queryset()),
            on_results=lambda issue_type: IssueTypeSerializer(
                issue_type,
                many=True,
                fields=self.fields,
                expand=self.expand,
            ).data,
        )

    def post(self, request, slug):
        # Validation check if the issue already exists
        if (IssueType.objects.filter(
                name=request.data.get('name'),
                workspace__slug=slug
            ).exists()
        ):
            issue_type = IssueType.objects.filter(
                name=request.data.get('name'),
                workspace__slug=slug
            ).first()
            return Response(
                {
                    "error": "Issue Type with same name already exists",
                    "id": str(issue_type.id),
                },
                status=status.HTTP_409_CONFLICT,
            )
        workspace = Workspace.objects.get(slug=slug)
        serializer = IssueTypeSerializer(
            data=request.data, 
            context={'workspace_id': workspace.id}
        )
        if serializer.is_valid():
            serializer.save()
            issue_type = IssueType.objects.get(
                pk=serializer.data.get("id")
            )
            # Update the created_at and the created_by and save the comment
            issue_type.created_at = request.data.get(
                "created_at", timezone.now()
            )
            issue_type.created_by_id = request.data.get(
                "created_by", request.user.id
            )
            issue_type.save(update_fields=["created_at", "created_by"])

            # issue_activity.delay(
            #     type="type.activity.created",
            #     requested_data=json.dumps(
            #         serializer.data, cls=DjangoJSONEncoder
            #     ),
            #     current_instance=None,
            # epoch=int(timezone.now().timestamp()),
            # )
            # No issue_activity.delay here
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, slug, pk):
        try:
            workspace = Workspace.objects.get(slug=slug)
        except Workspace.DoesNotExist:
            return Response({"error": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            issue_type = IssueType.objects.get(workspace__slug=slug, pk=pk)
        except IssueType.DoesNotExist:
            return Response({"error": "IssueType not found"}, status=status.HTTP_404_NOT_FOUND)

        # Validation check if the issue type with the same name already exists
        if 'name' in request.data and IssueType.objects.filter(
            workspace__slug=slug,
            name=request.data.get('name')
        ).exclude(pk=pk).exists():
            conflicting_issue_type = IssueType.objects.filter(workspace__slug=slug, name=request.data.get('name')).first()
            if conflicting_issue_type.pk != issue_type.pk:
                 return Response(
                    {
                        "error": "IssueType with the same name already exists",
                        "id": str(conflicting_issue_type.id)
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        serializer = IssueTypeSerializer(
            issue_type, data=request.data, context={'workspace_id': workspace.id}, partial=True
        )
        if serializer.is_valid():
            try:
                serializer.save()
                # No issue_activity.delay here
                return Response(serializer.data, status=status.HTTP_200_OK)
            except IntegrityError as e:
                return Response({"error": "Database integrity error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug, pk):
        try:
            issue_type = IssueType.objects.get(workspace__slug=slug, pk=pk)
        except IssueType.DoesNotExist:
            return Response({"error": "IssueType not found"}, status=status.HTTP_404_NOT_FOUND)

        # No issue_activity.delay here
        try:
            issue_type.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except IntegrityError as e:
            return Response({"error": "Database integrity error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class IssueTypeCustomPropertyAPIEndpoint(BaseAPIView):
    def get(self, request, slug, issue_type, pk=None):
        workspace = Workspace.objects.get(slug=slug)
        properties = IssueTypeCustomProperty.objects.filter(
            issue_type_id=issue_type
        )
        if pk:
            property = properties.get(pk=pk)
            serializer = IssueTypeCustomPropertySerializer(
                property, many=False
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        serializer = IssueTypeCustomPropertySerializer(properties, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, slug, issue_type):
        try:
            serializer = IssueTypeCustomPropertySerializer(
                data={**request.data}, context={
                    "issue_type_id": issue_type
                }
            )
            print(serializer.is_valid())
            if serializer.is_valid():
                serializer.save()
                return Response(
                    serializer.data, status=status.HTTP_201_CREATED
                )
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError as e:
            if "already exists" in str(e):
                return Response(
                    {"name": "The Property Name is already taken"},
                    status=status.HTTP_410_GONE,
                )
        except ValidationError:
            return Response(
                {"error": "Validation Error", "details": serializer.errors if serializer else "Unknown"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def patch(self, request, slug, issue_type, pk):
        try:
            custom_property = IssueTypeCustomProperty.objects.get(
                issue_type_id=issue_type,
                pk=pk,
                issue_type__workspace__slug=slug
            )
        except IssueTypeCustomProperty.DoesNotExist:
            return Response({"error": "IssueTypeCustomProperty not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = IssueTypeCustomPropertySerializer(
            custom_property, data=request.data, partial=True
        )
        if serializer.is_valid():
            try:
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            except IntegrityError as e:
                if "already exists" in str(e) or "unique constraint" in str(e).lower():
                    return Response(
                        {"name": "The Property Name is already taken for this Issue Type"},
                        status=status.HTTP_409_CONFLICT,
                    )
                else:
                    return Response({"error": "Database integrity error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug, issue_type, pk):
        try:
            custom_property = IssueTypeCustomProperty.objects.get(
                issue_type_id=issue_type,
                pk=pk,
                issue_type__workspace__slug=slug
            )
        except IssueTypeCustomProperty.DoesNotExist:
            return Response({"error": "IssueTypeCustomProperty not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            custom_property.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except IntegrityError as e:
            return Response({"error": "Database integrity error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IssueTypeWithPropertiesAPIEndpoint(BaseAPIView):
    """
    Idempotent, atomic creation of an issue type together with its custom
    properties.

    POST body:
    {
        "name": "Ticket",                       # required
        "description": "...",                   # optional
        "logo_props": {...},                    # optional
        "is_epic": false,                       # optional
        "level": 0,                             # optional
        "custom_properties": [                  # optional, list
            {
                "name": "SLA",                  # required per item
                "value": {...},                 # required per item (JSON)
                "data_type": "text",            # optional
                "is_required": false,           # optional
                "is_active": true               # optional
            },
            ...
        ]
    }

    Semantics:
      * The issue type is looked up by (workspace, name). If it exists, it
        is reused; otherwise it is created.
      * Each custom property is looked up by (issue_type, name). Existing
        ones are returned unchanged; missing ones are created.
      * The issue-type insert and all property inserts run in a single
        transaction. If any property fails, the whole call is rolled back
        — including a freshly-created issue type — so callers never see a
        half-built state inside Plane.
      * Safe to retry. Re-posting the same payload returns the same
        ids without raising 409.

    Response: 200 if nothing new was created, 201 if anything was created.
    Body shape:
    {
        "issue_type": { ...IssueTypeSerializer... },
        "custom_properties": [ {...IssueTypeCustomPropertySerializer...}, ... ],
        "created": { "issue_type": bool, "custom_properties": [<names created>] }
    }
    """

    permission_classes = [ProjectLitePermission]

    def post(self, request, slug):
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response(
                {"error": "`name` is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            workspace = Workspace.objects.get(slug=slug)
        except Workspace.DoesNotExist:
            return Response(
                {"error": "Workspace not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        properties_payload = request.data.get("custom_properties") or []
        if not isinstance(properties_payload, list):
            return Response(
                {"error": "`custom_properties` must be a list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate each property up-front so we don't open a transaction
        # only to bail out mid-way.
        for idx, prop in enumerate(properties_payload):
            if not isinstance(prop, dict):
                return Response(
                    {"error": f"custom_properties[{idx}] must be an object."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not (prop.get("name") or "").strip():
                return Response(
                    {"error": f"custom_properties[{idx}].name is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "value" not in prop:
                return Response(
                    {"error": f"custom_properties[{idx}].value is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        issue_type_fields = {
            k: request.data[k]
            for k in ("description", "logo_props", "is_epic", "level",
                      "is_default", "is_active", "external_source",
                      "external_id")
            if k in request.data
        }

        created_issue_type = False
        created_property_names = []

        try:
            with transaction.atomic():
                # Lock any existing row by (workspace, name) so two concurrent
                # callers can't both think they're the creator. IssueType has
                # no DB-level uniqueness on (workspace, name) — the lock +
                # re-check is what makes get-or-create safe here.
                existing = (
                    IssueType.objects
                    .select_for_update()
                    .filter(workspace=workspace, name=name)
                    .first()
                )
                if existing is not None:
                    issue_type = existing
                else:
                    serializer = IssueTypeSerializer(
                        data={"name": name, **issue_type_fields},
                        context={"workspace_id": workspace.id},
                    )
                    if not serializer.is_valid():
                        return Response(
                            serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    serializer.save()
                    issue_type = IssueType.objects.get(pk=serializer.data["id"])
                    issue_type.created_by_id = request.user.id
                    issue_type.save(update_fields=["created_by"])
                    created_issue_type = True

                # Properties: get-or-create per name. The DB-level unique
                # constraint on (issue_type, name) where deleted_at IS NULL
                # makes this race-safe.
                existing_props = {
                    p.name: p
                    for p in IssueTypeCustomProperty.objects.filter(
                        issue_type=issue_type
                    )
                }
                final_props = []
                for prop in properties_payload:
                    pname = prop["name"].strip()
                    if pname in existing_props:
                        final_props.append(existing_props[pname])
                        continue
                    prop_serializer = IssueTypeCustomPropertySerializer(
                        data={
                            "name": pname,
                            "value": prop["value"],
                            "data_type": prop.get("data_type"),
                            "is_required": prop.get("is_required", False),
                            "is_active": prop.get("is_active", True),
                        },
                        context={"issue_type_id": issue_type.id},
                    )
                    if not prop_serializer.is_valid():
                        # Raising forces rollback of the whole atomic block —
                        # including the freshly-created issue type, if any.
                        raise ValidationError({
                            "custom_property": pname,
                            "errors": prop_serializer.errors,
                        })
                    prop_serializer.save()
                    final_props.append(
                        IssueTypeCustomProperty.objects.get(
                            pk=prop_serializer.data["id"]
                        )
                    )
                    created_property_names.append(pname)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as e:
            return Response(
                {"error": "Database integrity error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_body = {
            "issue_type": IssueTypeSerializer(issue_type).data,
            "custom_properties": IssueTypeCustomPropertySerializer(
                final_props, many=True
            ).data,
            "created": {
                "issue_type": created_issue_type,
                "custom_properties": created_property_names,
            },
        }
        http_status = (
            status.HTTP_201_CREATED
            if created_issue_type or created_property_names
            else status.HTTP_200_OK
        )
        return Response(response_body, status=http_status)